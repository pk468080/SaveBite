"""Order management (Milestone 7): customer history/detail and
merchant queue, backed by the existing reservation and
Razorpay flows. No new state transitions are introduced:
this milestone only READS orders, items, events, and
reservations. Pickup-token, cancellation, refund, payout,
and notification workflows are explicitly out of scope.

Authorisation, in two layers, on purpose:
1. RLS: orders/items/events/reservations are selectable
   only by the owning customer or by a store operator
   (can_manage_store for orders), and membership rows only
   by the member or a merchant owner/admin. The user-context
   client therefore cannot see another customer's or
   merchant's rows even if the API forgot to filter.
2. API: customer endpoints filter by customer_id = the
   authenticated user, never by a request parameter; merchant
   endpoints compute the caller's authorized stores from
   their own membership rows (active merchant owner/admin
   membership, or active store-staff membership in
   owner/admin/store_manager/pickup_operator/finance_viewer
   — the same set as the orders RLS policy) and filter
   orders to those stores. A store_id the caller is not
   authorized for yields an empty result for lists and a
   404 for details, never another merchant's data.

Privacy: no customer email, phone, or address is returned
anywhere here. Profiles are own-only by RLS, so a merchant
cannot read a customer's profile through this API, and
neither view returns customer_id, request_idempotency_key,
request_hash, gateway ids, signatures, or private payment
records. Payment information comes only from the order row
itself (payment_status, amounts, confirmed_at); the private
payment_transactions table is never queried.

Timeline honesty: the timeline is exactly the
order_status_events rows for the order, sorted by time,
with a customer-friendly label mapped from the recorded
to_status/reason. No event is invented, no missing history
is guessed from the current status, and payment status is
never conflated with fulfilment: pending_payment is not
paid, captured is not collected, and confirmed is not
ready_for_pickup.

Pagination: filters are sent to PostgREST (customer_id,
status, payment_status, created_at range, store_id,
order_number search, pickup range), so the whole orders
table is never fetched into Python. Sorting is created_at
descending with id descending as tiebreak, applied in
Python over the filtered set, then paginated. At very large
scale the limit/offset should move into PostgREST with a
count header; that is documented in architecture.md, not
hidden, and it is not needed for the filtered sets here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, get_user_client
from app.errors import ApiError, NotFoundError
from app.schemas import (
    AuthenticatedUser,
    MerchantMemberRole,
    MerchantOrderListResponse,
    MerchantOrderQueueSummary,
    MerchantOrderSummary,
    OrderDetail,
    OrderItemPreview,
    OrderItemResponse,
    OrderListResponse,
    OrderPaymentSummary,
    OrderStatus,
    OrderStoreDetail,
    OrderStoreSummary,
    OrderSummary,
    OrderTimelineEvent,
    PaymentStatus,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["orders"])

_ORDER_SELECT = (
    "id,order_number,customer_id,merchant_id,store_id,status,"
    "payment_status,currency,subtotal_amount,discount_amount,"
    "platform_fee_amount,tax_amount,total_amount,pickup_starts_at,"
    "pickup_ends_at,customer_note,cancellation_reason,confirmed_at,"
    "collected_at,cancelled_at,created_at,updated_at"
)
_STORE_SELECT = (
    "id,name,address_line_1,address_line_2,locality,city,state,"
    "pincode,contact_phone,pickup_instructions"
)
_ITEM_SELECT = (
    "id,order_id,listing_id,listing_type,listing_title_snapshot,"
    "listing_description_snapshot,allergen_codes_snapshot,"
    "dietary_classification_snapshot,quantity,unit_price,"
    "reference_value_snapshot,line_total,created_at"
)

# Roles that grant order visibility for a store, matching the
# orders RLS policy (can_manage_store with this role set).
_ORDER_VIEW_ROLES = (
    MerchantMemberRole.owner,
    MerchantMemberRole.admin,
    MerchantMemberRole.store_manager,
    MerchantMemberRole.pickup_operator,
    MerchantMemberRole.finance_viewer,
)

_TIMELINE_LABELS = {
    ("pending_payment", "reservation_created"): "Reservation created",
    ("pending_payment", None): "Awaiting payment",
    ("confirmed", "payment_captured"): "Payment confirmed",
    ("ready_for_pickup", None): "Ready for pickup",
    ("collected", None): "Order collected",
    ("expired", None): "Reservation expired",
    ("cancelled", None): "Order cancelled",
    ("refund_pending", None): "Refund pending",
    ("refunded", None): "Order refunded",
}


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


def _store_summary(row: dict) -> OrderStoreSummary:
    return OrderStoreSummary(
        id=row["id"],
        name=row["name"],
        locality=row.get("locality"),
        city=row["city"],
        state=row["state"],
        pincode=row["pincode"],
    )


def _store_detail(row: dict) -> OrderStoreDetail:
    return OrderStoreDetail(
        id=row["id"],
        name=row["name"],
        address_line_1=row["address_line_1"],
        address_line_2=row.get("address_line_2"),
        locality=row.get("locality"),
        city=row["city"],
        state=row["state"],
        pincode=row["pincode"],
        contact_phone=row.get("contact_phone"),
        pickup_instructions=row.get("pickup_instructions"),
    )


async def _stores_by_id(
    client: SupabaseRestClient, store_ids: list[str]
) -> dict[str, dict]:
    if not store_ids:
        return {}
    try:
        rows = await client.query(
            "stores",
            select=_STORE_SELECT,
            filters={"id": f"in.({','.join(sorted(set(store_ids)))})"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return {str(row["id"]): row for row in rows}


async def _items_by_order(
    client: SupabaseRestClient, order_ids: list[str]
) -> dict[str, list[dict]]:
    if not order_ids:
        return {}
    try:
        rows = await client.query(
            "order_items",
            select=_ITEM_SELECT,
            filters={"order_id": f"in.({','.join(sorted(set(order_ids)))})"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    by_order: dict[str, list[dict]] = {}
    for row in rows:
        by_order.setdefault(str(row["order_id"]), []).append(row)
    for items in by_order.values():
        items.sort(key=lambda r: str(r.get("created_at", "")))
    return by_order


async def _images_by_listing(
    client: SupabaseRestClient, listing_ids: list[str]
) -> dict[str, str]:
    """First valid listing-media image per listing. A path that
    is not <listing_id>/<file> is dropped, as in Milestone 5."""
    if not listing_ids:
        return {}
    try:
        rows = await client.query(
            "listing_images",
            select="listing_id,storage_path,display_order",
            filters={"listing_id": f"in.({','.join(sorted(set(listing_ids)))})"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    first: dict[str, str] = {}
    for row in sorted(rows, key=lambda r: r.get("display_order", 0)):
        listing_id = str(row["listing_id"])
        path = str(row.get("storage_path") or "")
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == listing_id and ".." not in parts:
            first.setdefault(listing_id, path)
    return first


def _item_response(row: dict, images: dict[str, str]) -> OrderItemResponse:
    return OrderItemResponse(
        listing_id=row["listing_id"],
        listing_type=row["listing_type"],
        title=row["listing_title_snapshot"],
        description=row.get("listing_description_snapshot"),
        quantity=row["quantity"],
        unit_price=_dec(row["unit_price"]),
        line_total=_dec(row["line_total"]),
        reference_value=_dec(row["reference_value_snapshot"]),
        dietary_classification=row.get("dietary_classification_snapshot", "unknown"),
        allergen_codes=row.get("allergen_codes_snapshot") or [],
        image_path=images.get(str(row["listing_id"])),
    )


def _payment_summary(order: dict) -> OrderPaymentSummary:
    status = PaymentStatus(order["payment_status"])
    captured = status is PaymentStatus.captured
    return OrderPaymentSummary(
        status=status,
        # Razorpay is the only gateway implemented in this
        # codebase (M6 checkout hardcodes it); this label is
        # shown only once a payment exists, never for a
        # never-attempted order, and it is not a per-
        # transaction lookup (private transactions are never
        # queried).
        gateway_label="Razorpay" if status is not PaymentStatus.created else None,
        amount_paid=_dec(order["total_amount"]) if captured else Decimal("0"),
        paid_at=_parse_time(order.get("confirmed_at")) if captured else None,
    )


def _timeline(events: list[dict]) -> list[OrderTimelineEvent]:
    timeline = []
    for event in sorted(events, key=lambda e: str(e.get("created_at", ""))):
        to_status = str(event["to_status"])
        reason = event.get("reason")
        label = _TIMELINE_LABELS.get(
            (to_status, reason),
            _TIMELINE_LABELS.get(
                (to_status, None), to_status.replace("_", " ").title()
            ),
        )
        try:
            status = OrderStatus(to_status)
        except ValueError:
            continue
        timeline.append(
            OrderTimelineEvent(
                status=status,
                label=label,
                occurred_at=_parse_time(event["created_at"]),  # type: ignore[arg-type]
                actor_type=str(event.get("actor_type", "system")),
            )
        )
    return timeline


def _sorted_page(rows: list[dict], page: int, page_size: int) -> tuple[list[dict], int]:
    rows.sort(
        key=lambda r: (str(r.get("created_at", "")), str(r["id"])),
        reverse=True,
    )
    total = len(rows)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total


async def _detail_for_order(client: SupabaseRestClient, order: dict) -> OrderDetail:
    order_id = str(order["id"])
    try:
        items_rows = await client.query(
            "order_items",
            select=_ITEM_SELECT,
            filters={"order_id": f"eq.{order_id}"},
        )
        events = await client.query(
            "order_status_events",
            select="id,order_id,from_status,to_status,actor_type,reason,created_at",
            filters={"order_id": f"eq.{order_id}"},
        )
        reservations = await client.query(
            "inventory_reservations",
            select="id,order_id,status,expires_at",
            filters={"order_id": f"eq.{order_id}", "status": "eq.active"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    images = await _images_by_listing(
        client, [str(r["listing_id"]) for r in items_rows]
    )
    items_rows.sort(key=lambda r: str(r.get("created_at", "")))
    items = [_item_response(row, images) for row in items_rows]
    expires: list[datetime] = []
    for reservation in reservations:
        parsed = _parse_time(reservation.get("expires_at"))
        if parsed is not None:
            expires.append(parsed)
    stores = await _stores_by_id(client, [str(order["store_id"])])
    store_row = stores.get(str(order["store_id"]))
    if store_row is None:
        raise NotFoundError("Order not found")
    return OrderDetail(
        id=order["id"],
        order_number=order["order_number"],
        status=OrderStatus(order["status"]),
        payment=_payment_summary(order),
        subtotal_amount=_dec(order["subtotal_amount"]),
        discount_amount=_dec(order["discount_amount"]),
        platform_fee_amount=_dec(order["platform_fee_amount"]),
        tax_amount=_dec(order["tax_amount"]),
        total_amount=_dec(order["total_amount"]),
        currency=order.get("currency", "INR"),
        created_at=_parse_time(order["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_time(order["updated_at"]),  # type: ignore[arg-type]
        confirmed_at=_parse_time(order.get("confirmed_at")),
        collected_at=_parse_time(order.get("collected_at")),
        cancelled_at=_parse_time(order.get("cancelled_at")),
        customer_note=order.get("customer_note"),
        cancellation_reason=order.get("cancellation_reason"),
        store=_store_detail(store_row),
        pickup_starts_at=_parse_time(order["pickup_starts_at"]),  # type: ignore[arg-type]
        pickup_ends_at=_parse_time(order["pickup_ends_at"]),  # type: ignore[arg-type]
        reservation_expires_at=max(expires) if expires else None,
        items=items,
        timeline=_timeline(events),
    )


# --- customer -----------------------------------------------------------


@router.get("/v1/orders", response_model=OrderListResponse)
async def customer_orders(
    status: OrderStatus | None = Query(default=None),
    payment_status: PaymentStatus | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> OrderListResponse:
    """The authenticated customer's own orders only. The
    customer_id filter comes from the Auth dependency, never
    from a request parameter, so changing a parameter cannot
    reveal another customer's orders."""
    if (
        created_from is not None
        and created_to is not None
        and created_from > created_to
    ):
        raise ApiError(
            422, "VALIDATION_ERROR", "created_from must not be after created_to"
        )
    filters: dict[str, str] = {"customer_id": f"eq.{user.id}"}
    if status is not None:
        filters["status"] = f"eq.{status.value}"
    if payment_status is not None:
        filters["payment_status"] = f"eq.{payment_status.value}"
    # A plain filter dict holds one operator per column, so
    # the lower bound is enforced database-side and the upper
    # bound is applied in Python below. Both bounds are still
    # honoured; only the enforcement point differs.
    if created_from is not None:
        filters["created_at"] = f"gte.{created_from.isoformat()}"
    try:
        rows = await client.query("orders", select=_ORDER_SELECT, filters=filters)
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if created_to is not None:
        rows = [
            r
            for r in rows
            if (_parse_time(r.get("created_at")) or datetime.min.replace(tzinfo=UTC))
            <= created_to
        ]
    page_rows, total = _sorted_page(rows, page, page_size)
    stores = await _stores_by_id(client, [str(r["store_id"]) for r in page_rows])
    items_by_order = await _items_by_order(client, [str(r["id"]) for r in page_rows])
    summaries = []
    for row in page_rows:
        store_row = stores.get(str(row["store_id"]))
        if store_row is None:
            continue
        items = items_by_order.get(str(row["id"]), [])
        summaries.append(
            OrderSummary(
                id=row["id"],
                order_number=row["order_number"],
                status=OrderStatus(row["status"]),
                payment_status=PaymentStatus(row["payment_status"]),
                total_amount=_dec(row["total_amount"]),
                currency=row.get("currency", "INR"),
                created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
                updated_at=_parse_time(row["updated_at"]),  # type: ignore[arg-type]
                store=_store_summary(store_row),
                pickup_starts_at=_parse_time(row["pickup_starts_at"]),  # type: ignore[arg-type]
                pickup_ends_at=_parse_time(row["pickup_ends_at"]),  # type: ignore[arg-type]
                item_count=len(items),
                items_preview=[
                    OrderItemPreview(
                        title=item["listing_title_snapshot"],
                        quantity=item["quantity"],
                    )
                    for item in items[:2]
                ],
            )
        )
    return OrderListResponse(
        items=summaries, total=total, page=page, page_size=page_size
    )


@router.get("/v1/orders/{order_id}", response_model=OrderDetail)
async def customer_order_detail(
    order_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> OrderDetail:
    """One order, only if it belongs to the authenticated
    customer. Any other order — nonexistent or someone
    else's — returns the same 404, so the response never
    reveals whether another customer's order exists."""
    try:
        rows = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={"id": f"eq.{order_id}", "customer_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Order not found")
    return await _detail_for_order(client, rows[0])


# --- merchant -----------------------------------------------------------


async def _authorized_store_ids(
    user: AuthenticatedUser, client: SupabaseRestClient
) -> set[str]:
    """Stores the caller may view orders for, from their own
    membership rows only. Merchant owner/admin membership
    grants every store of that merchant; store-staff
    membership in an order-view role grants that store."""
    try:
        memberships = await client.query(
            "merchant_memberships",
            select="merchant_id,role,is_active",
            filters={"user_id": f"eq.{user.id}", "is_active": "eq.true"},
        )
        staff = await client.query(
            "store_staff_memberships",
            select="store_id,role,is_active",
            filters={"user_id": f"eq.{user.id}", "is_active": "eq.true"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    store_ids = {
        str(row["store_id"])
        for row in staff
        if row.get("is_active") is not False
        and row.get("role") in {role.value for role in _ORDER_VIEW_ROLES}
    }
    owner_admin_merchants = {
        str(row["merchant_id"])
        for row in memberships
        if row.get("is_active") is not False and row.get("role") in ("owner", "admin")
    }
    if owner_admin_merchants:
        try:
            stores = await client.query(
                "stores",
                select="id,merchant_id",
                filters={
                    "merchant_id": f"in.({','.join(sorted(owner_admin_merchants))})"
                },
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        store_ids.update(str(row["id"]) for row in stores)
    return store_ids


@router.get("/v1/merchant/orders/summary", response_model=MerchantOrderQueueSummary)
async def merchant_order_summary(
    store_id: UUID | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MerchantOrderQueueSummary:
    """Queue counts over the caller's authorized stores only.
    Counts come from real order rows, never from hardcoded
    values. A store_id the caller is not authorized for is
    treated as no stores (all counts zero), never as access
    to that store."""
    authorized = await _authorized_store_ids(user, client)
    if store_id is not None:
        authorized = authorized & {str(store_id)}
    if not authorized:
        return MerchantOrderQueueSummary(
            total=0,
            awaiting_payment=0,
            paid=0,
            upcoming_pickups=0,
            completed=0,
            cancelled_or_expired=0,
        )
    filters: dict[str, str] = {"store_id": f"in.({','.join(sorted(authorized))})"}
    if created_from is not None:
        filters["created_at"] = f"gte.{created_from.isoformat()}"
    try:
        rows = await client.query(
            "orders",
            select="id,status,payment_status,pickup_starts_at,created_at",
            filters=filters,
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if created_to is not None:
        rows = [
            r
            for r in rows
            if (_parse_time(r.get("created_at")) or datetime.min.replace(tzinfo=UTC))
            <= created_to
        ]
    now = datetime.now(UTC)
    upcoming = 0
    for row in rows:
        pickup = _parse_time(row.get("pickup_starts_at"))
        if (
            row["status"] in ("confirmed", "ready_for_pickup")
            and pickup is not None
            and pickup >= now
        ):
            upcoming += 1
    return MerchantOrderQueueSummary(
        total=len(rows),
        awaiting_payment=sum(1 for r in rows if r["status"] == "pending_payment"),
        paid=sum(1 for r in rows if r["payment_status"] == "captured"),
        upcoming_pickups=upcoming,
        completed=sum(1 for r in rows if r["status"] == "collected"),
        cancelled_or_expired=sum(
            1 for r in rows if r["status"] in ("cancelled", "expired")
        ),
    )


@router.get("/v1/merchant/orders", response_model=MerchantOrderListResponse)
async def merchant_orders(
    store_id: UUID | None = Query(default=None),
    status: OrderStatus | None = Query(default=None),
    payment_status: PaymentStatus | None = Query(default=None),
    pickup_from: datetime | None = Query(default=None),
    pickup_to: datetime | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MerchantOrderListResponse:
    """Orders for the caller's authorized stores only. The
    store_id parameter can only NARROW the authorized set —
    it can never widen it to another merchant's store."""
    authorized = await _authorized_store_ids(user, client)
    if store_id is not None:
        authorized = authorized & {str(store_id)}
    if not authorized:
        return MerchantOrderListResponse(
            items=[], total=0, page=page, page_size=page_size
        )
    filters: dict[str, str] = {"store_id": f"in.({','.join(sorted(authorized))})"}
    if status is not None:
        filters["status"] = f"eq.{status.value}"
    if payment_status is not None:
        filters["payment_status"] = f"eq.{payment_status.value}"
    if pickup_from is not None:
        filters["pickup_starts_at"] = f"gte.{pickup_from.isoformat()}"
    if search is not None and search.strip():
        filters["order_number"] = f"ilike.*{search.strip()}*"
    try:
        rows = await client.query("orders", select=_ORDER_SELECT, filters=filters)
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if pickup_to is not None:
        rows = [
            r
            for r in rows
            if (
                _parse_time(r.get("pickup_starts_at"))
                or datetime.max.replace(tzinfo=UTC)
            )
            <= pickup_to
        ]
    page_rows, total = _sorted_page(rows, page, page_size)
    stores = await _stores_by_id(client, [str(r["store_id"]) for r in page_rows])
    items_by_order = await _items_by_order(client, [str(r["id"]) for r in page_rows])
    summaries = []
    for row in page_rows:
        store_row = stores.get(str(row["store_id"]))
        if store_row is None:
            continue
        items = items_by_order.get(str(row["id"]), [])
        summaries.append(
            MerchantOrderSummary(
                id=row["id"],
                order_number=row["order_number"],
                status=OrderStatus(row["status"]),
                payment_status=PaymentStatus(row["payment_status"]),
                total_amount=_dec(row["total_amount"]),
                currency=row.get("currency", "INR"),
                created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
                store=_store_summary(store_row),
                pickup_starts_at=_parse_time(row["pickup_starts_at"]),  # type: ignore[arg-type]
                pickup_ends_at=_parse_time(row["pickup_ends_at"]),  # type: ignore[arg-type]
                item_count=len(items),
                items_preview=[
                    OrderItemPreview(
                        title=item["listing_title_snapshot"],
                        quantity=item["quantity"],
                    )
                    for item in items[:2]
                ],
            )
        )
    return MerchantOrderListResponse(
        items=summaries, total=total, page=page, page_size=page_size
    )


@router.get("/v1/merchant/orders/{order_id}", response_model=OrderDetail)
async def merchant_order_detail(
    order_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> OrderDetail:
    """One order, only if its store is authorized for the
    caller. Any other order returns the same 404, so the
    response never reveals whether another merchant's order
    exists. The detail shape is the same as the customer
    view, minus nothing the merchant may not see — and it
    still contains no customer personal information, because
    the order row carries none and profiles are own-only."""
    authorized = await _authorized_store_ids(user, client)
    if not authorized:
        raise NotFoundError("Order not found")
    try:
        rows = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={
                "id": f"eq.{order_id}",
                "store_id": f"in.({','.join(sorted(authorized))})",
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Order not found")
    return await _detail_for_order(client, rows[0])
