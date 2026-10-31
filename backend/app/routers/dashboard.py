"""Merchant dashboard and store analytics (Milestone 10).

Read-only reporting. Every number comes from actual
database records; nothing is fabricated, and no endpoint
mutates an order, listing, payment, or review.

Verified data sources (from the baseline):
- stores: id, merchant_id, name, status (draft/active/
  inactive/suspended), timezone (default Asia/Kolkata),
  plus address/city/pincode. store_hours: weekday,
  opens_at, closes_at (null times = closed/unknown for
  that day).
- listings: status (draft/scheduled/active/paused/
  sold_out/expired/cancelled), selling_price, currency
  INR, total/reserved/sold quantities, and the generated
  stored column available_quantity = total - reserved -
  sold (read-only, never written, never recomputed for
  business decisions). "Published" here means status
  active, the status the publish endpoint sets.
- orders: status (pending_payment/confirmed/
  ready_for_pickup/collected/expired/cancelled/
  refund_pending/refunded), payment_status (created/
  authorized/captured/failed/refund_pending/
  partially_refunded/refunded/reconciliation_required),
  total_amount (numeric), created_at, pickup window,
  collected_at. Currency is INR by contract.
- reviews: rating, moderation_status (visible/hidden/
  under_review), store_id. Dashboard aggregates use
  visible reviews only, the same rule as M9.
- Pickup events live in private.pickup_events and are
  NOT queried (private schema). Pickup categories are
  therefore derived from order rows + the current time,
  using the same windows the verify RPC enforces:
  in-window = pickup_starts_at - 15 minutes to
  pickup_ends_at + 30 minutes; window_expired = past
  pickup_ends_at + 30 minutes without collection. A
  window-expired order is NEVER labelled "missed":
  the database records no no-show event.

Authorization (mirrors M7 order reads, the existing
orders RLS set): a store is authorized when the caller
is a merchant member with role owner/admin (all stores
of that merchant) or a store staff member with role
store_manager, pickup_operator, or finance_viewer.
inventory_manager is NOT in the orders RLS set and is
therefore NOT granted dashboard access here — it keeps
the existing listings APIs. A requested store_id can
only narrow the authorized set; an unauthorized store
returns 404. No client-supplied merchant id or role is
ever trusted, and no service-role client is used.

Money: Decimal arithmetic only, serialized as strings
("390.00"), never floats. "Captured order value" is the
sum of total_amount over orders whose payment_status is
captured — nothing else. Pending, authorized-only,
failed, refunded, partially_refunded, and
reconciliation states never count as sales, and a
captured order is not called collected unless its
order status is collected. Captured order value is NOT
merchant earnings, settlement, or payout revenue:
platform fees, refunds, and payouts are not deducted,
because the order row carries no refund amounts to net
against — so no net revenue figure is reported at all.
Refund-related orders are counted (refund_orders) but
their amounts are never estimated.

Dates: the reporting period is half-open [from, to).
Grouping uses the store's own timezone for a single
store, and Asia/Kolkata when aggregating multiple
stores. Day buckets are calendar days in that timezone;
week buckets start on Monday; month buckets are
calendar months. PostgREST filters carry store_id and
created_at >= from; the upper bound is applied in
Python because the client holds one operator per
column (the same documented limitation as M7).

Performance: orders, listings, and reviews for the
authorized store set are fetched in one query each
(batched by store_id in), then aggregated in Python
over that tightly scoped set. No per-store queries, no
full-table fetches. At large scale these aggregates
belong in database-side grouping or an approved
read-only view — documented, not applied here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, get_user_client
from app.errors import ApiError, NotFoundError
from app.schemas import (
    AuthenticatedUser,
    DashboardInventoryMetrics,
    DashboardOrderMetrics,
    DashboardOverview,
    DashboardPeriod,
    DashboardPickupMetrics,
    DashboardRatingMetrics,
    DashboardStoreContext,
    InventoryDashboard,
    InventoryListingSummary,
    PickupDashboard,
    PickupOrderSummary,
    SalesAnalytics,
    SalesBucket,
    StoreComparison,
    StoreComparisonRow,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["merchant-dashboard"])

_DASHBOARD_ROLES = (
    "owner",
    "admin",
    "store_manager",
    "pickup_operator",
    "finance_viewer",
)
_ORDER_SELECT = (
    "id,order_number,store_id,status,payment_status,total_amount,"
    "created_at,pickup_starts_at,pickup_ends_at,collected_at"
)
_LISTING_SELECT = (
    "id,store_id,title,status,total_quantity,reserved_quantity,"
    "sold_quantity,available_quantity,sale_ends_at"
)
_DEFAULT_TZ = "Asia/Kolkata"


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _dec(value: object) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name) if name else ZoneInfo(_DEFAULT_TZ)
    except Exception:
        return ZoneInfo(_DEFAULT_TZ)


async def _authorized_stores(
    user: AuthenticatedUser, client: SupabaseRestClient
) -> dict[str, dict]:
    """Authorized stores keyed by id, mirroring M7: merchant
    owner/admin memberships grant all of that merchant's
    stores; store staff rows with a dashboard role grant
    that store only. Inactive rows are excluded twice
    (query + Python), as in M7."""
    try:
        memberships = await client.query(
            "merchant_memberships",
            select="merchant_id,user_id,role,is_active",
            filters={"user_id": f"eq.{user.id}", "is_active": "eq.true"},
        )
        staff = await client.query(
            "store_staff_memberships",
            select="store_id,user_id,role,is_active",
            filters={"user_id": f"eq.{user.id}", "is_active": "eq.true"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    merchant_ids = [
        m["merchant_id"]
        for m in memberships
        if m.get("is_active") is not False and m["role"] in ("owner", "admin")
    ]
    store_ids = {
        s["store_id"]
        for s in staff
        if s.get("is_active") is not False and s["role"] in _DASHBOARD_ROLES
    }
    stores: dict[str, dict] = {}
    if merchant_ids:
        try:
            rows = await client.query(
                "stores",
                select="id,merchant_id,name,status,timezone",
                filters={"merchant_id": f"in.({','.join(sorted(set(merchant_ids)))})"},
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        for row in rows:
            stores[str(row["id"])] = row
    if store_ids:
        try:
            rows = await client.query(
                "stores",
                select="id,merchant_id,name,status,timezone",
                filters={"id": f"in.({','.join(sorted(store_ids))})"},
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        for row in rows:
            stores[str(row["id"])] = row
    return stores


def _resolve_stores(stores: dict[str, dict], store_id: UUID | None) -> dict[str, dict]:
    if store_id is None:
        return stores
    if str(store_id) not in stores:
        raise NotFoundError("Store not found")
    return {str(store_id): stores[str(store_id)]}


def _period(from_: datetime | None, to: datetime | None) -> DashboardPeriod:
    if from_ is not None and to is not None and from_ >= to:
        raise ApiError(422, "VALIDATION_ERROR", "from must be before to")
    return DashboardPeriod(**{"from": from_, "to": to})


def _in_period(row: dict, from_: datetime | None, to: datetime | None) -> bool:
    created = _parse_time(row.get("created_at"))
    if created is None:
        return False
    if from_ is not None and created < from_:
        return False
    if to is not None and created >= to:
        return False
    return True


async def _fetch_orders(
    client: SupabaseRestClient,
    store_ids: list[str],
    from_: datetime | None,
    to: datetime | None,
) -> list[dict]:
    if not store_ids:
        return []
    filters: dict[str, str] = {"store_id": f"in.({','.join(sorted(store_ids))})"}
    if from_ is not None:
        filters["created_at"] = f"gte.{from_.isoformat()}"
    try:
        rows = await client.query("orders", select=_ORDER_SELECT, filters=filters)
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if to is not None:
        rows = [r for r in rows if _in_period(r, from_, to)]
    return rows


async def _fetch_listings(
    client: SupabaseRestClient, store_ids: list[str]
) -> list[dict]:
    if not store_ids:
        return []
    try:
        return await client.query(
            "listings",
            select=_LISTING_SELECT,
            filters={"store_id": f"in.({','.join(sorted(store_ids))})"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc


async def _fetch_visible_review_ratings(
    client: SupabaseRestClient, store_ids: list[str]
) -> list[dict]:
    if not store_ids:
        return []
    try:
        return await client.query(
            "reviews",
            select="store_id,rating",
            filters={
                "store_id": f"in.({','.join(sorted(store_ids))})",
                "moderation_status": "eq.visible",
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc


def _order_metrics(orders: list[dict]) -> DashboardOrderMetrics:
    captured = sum(
        (_dec(o["total_amount"]) for o in orders if o["payment_status"] == "captured"),
        Decimal("0"),
    )
    statuses = [o["status"] for o in orders]
    payments = [o["payment_status"] for o in orders]
    return DashboardOrderMetrics(
        total_orders=len(orders),
        paid_orders=sum(1 for p in payments if p == "captured"),
        awaiting_payment_orders=sum(
            1 for o in orders if o["status"] == "pending_payment"
        ),
        collected_orders=sum(1 for s in statuses if s == "collected"),
        cancelled_orders=sum(1 for s in statuses if s == "cancelled"),
        expired_orders=sum(1 for s in statuses if s == "expired"),
        refund_orders=sum(
            1
            for o in orders
            if o["status"] in ("refund_pending", "refunded")
            or o["payment_status"]
            in ("refund_pending", "partially_refunded", "refunded")
        ),
        captured_order_value=_money(captured),
        currency="INR",
    )


def _inventory_metrics(listings: list[dict]) -> DashboardInventoryMetrics:
    statuses = [lst["status"] for lst in listings]
    return DashboardInventoryMetrics(
        total_listings=len(listings),
        published_listings=sum(1 for s in statuses if s == "active"),
        draft_listings=sum(1 for s in statuses if s == "draft"),
        paused_listings=sum(1 for s in statuses if s == "paused"),
        sold_out_listings=sum(1 for s in statuses if s == "sold_out"),
        total_available_units=sum(
            int(lst["available_quantity"] or 0) for lst in listings
        ),
        total_reserved_units=sum(
            int(lst["reserved_quantity"] or 0) for lst in listings
        ),
        total_sold_units=sum(int(lst["sold_quantity"] or 0) for lst in listings),
    )


def _pickup_category(order: dict, now: datetime) -> str:
    """Category for a fulfilment-pending order. Collected
    orders are always 'completed'; anything else outside
    these rules is not a pickup order at all."""
    if order["status"] == "collected":
        return "completed"
    starts = _parse_time(order["pickup_starts_at"])
    ends = _parse_time(order["pickup_ends_at"])
    if starts is None or ends is None:
        return "upcoming"
    if now > ends + timedelta(minutes=30):
        return "window_expired"
    if starts - timedelta(minutes=15) <= now <= ends + timedelta(minutes=30):
        return "in_window"
    return "upcoming"


def _pickup_metrics(orders: list[dict], now: datetime) -> DashboardPickupMetrics:
    categories = [
        _pickup_category(o, now)
        for o in orders
        if o["status"] in ("confirmed", "ready_for_pickup", "collected")
    ]
    return DashboardPickupMetrics(
        upcoming_pickups=sum(1 for c in categories if c == "upcoming"),
        in_window_pickups=sum(1 for c in categories if c == "in_window"),
        completed_collections=sum(1 for c in categories if c == "completed"),
        window_expired_pickups=sum(1 for c in categories if c == "window_expired"),
    )


def _rating_metrics(review_rows: list[dict]) -> DashboardRatingMetrics:
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = Decimal(0)
    for row in review_rows:
        rating = int(row["rating"])
        if rating in counts:
            counts[rating] += 1
            total += Decimal(rating)
    n = len(review_rows)
    average = None
    if n:
        from decimal import ROUND_HALF_UP

        average = float(
            (total / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
    return DashboardRatingMetrics(
        average_rating=average,
        total_visible_reviews=n,
        five_star=counts[5],
        four_star=counts[4],
        three_star=counts[3],
        two_star=counts[2],
        one_star=counts[1],
    )


def _store_context(
    stores: dict[str, dict], open_now: bool | None = None
) -> DashboardStoreContext:
    if len(stores) == 1:
        store = next(iter(stores.values()))
        return DashboardStoreContext(
            store_id=UUID(str(store["id"])),
            store_name=store["name"],
            store_status=store["status"],
            timezone=store.get("timezone") or _DEFAULT_TZ,
            open_now=open_now,
            store_count=1,
        )
    return DashboardStoreContext(
        store_id=None,
        store_name=None,
        store_status=None,
        timezone=_DEFAULT_TZ,
        open_now=None,
        store_count=len(stores),
    )


def _open_now() -> bool | None:
    """Operating status is deliberately NOT computed: the
    database stores weekday as 0-6 but no code or
    document in the repository states whether 0 is Monday
    or Sunday, so "open now" cannot be determined
    reliably from stored hours + actual time. Returning
    None (unknown) is honest; guessing the convention
    would report a closed store as open or vice versa.
    Enabling this field requires first verifying the
    weekday convention against a real store's hours —
    documented as a proposed verification, not applied
    here."""
    return None


@router.get("/v1/merchant/dashboard", response_model=DashboardOverview)
async def dashboard_overview(
    store_id: UUID | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> DashboardOverview:
    period = _period(from_, to)
    stores = _resolve_stores(await _authorized_stores(user, client), store_id)
    store_ids = sorted(stores)
    orders = await _fetch_orders(client, store_ids, from_, to)
    listings = await _fetch_listings(client, store_ids)
    reviews = await _fetch_visible_review_ratings(client, store_ids)
    now = datetime.now(UTC)
    open_now = _open_now()
    return DashboardOverview(
        period=period,
        store=_store_context(stores, open_now),
        orders=_order_metrics(orders),
        inventory=_inventory_metrics(listings),
        pickups=_pickup_metrics(orders, now),
        ratings=_rating_metrics(reviews),
    )


def _bucket_key(created: datetime, tz: ZoneInfo, group_by: str) -> str:
    local = created.astimezone(tz)
    if group_by == "week":
        monday = local.date() - timedelta(days=local.weekday())
        return monday.isoformat()
    if group_by == "month":
        return local.strftime("%Y-%m-01")
    return local.date().isoformat()


@router.get("/v1/merchant/dashboard/sales", response_model=SalesAnalytics)
async def dashboard_sales(
    store_id: UUID | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    group_by: str = Query(default="day"),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> SalesAnalytics:
    if group_by not in ("day", "week", "month"):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid group_by")
    period = _period(from_, to)
    stores = _resolve_stores(await _authorized_stores(user, client), store_id)
    store_ids = sorted(stores)
    orders = await _fetch_orders(client, store_ids, from_, to)
    tz_name = (
        next(iter(stores.values())).get("timezone") or _DEFAULT_TZ
        if len(stores) == 1
        else _DEFAULT_TZ
    )
    tz = _tz(tz_name)
    buckets: dict[str, dict] = {}
    for order in orders:
        created = _parse_time(order["created_at"])
        if created is None:
            continue
        key = _bucket_key(created, tz, group_by)
        bucket = buckets.setdefault(
            key,
            {
                "total": 0,
                "captured": 0,
                "pending": 0,
                "failed": 0,
                "collected": 0,
                "cancelled_expired": 0,
                "value": Decimal("0"),
            },
        )
        bucket["total"] += 1
        if order["payment_status"] == "captured":
            bucket["captured"] += 1
            bucket["value"] += _dec(order["total_amount"])
        if order["status"] == "pending_payment":
            bucket["pending"] += 1
        if order["payment_status"] == "failed":
            bucket["failed"] += 1
        if order["status"] == "collected":
            bucket["collected"] += 1
        if order["status"] in ("cancelled", "expired"):
            bucket["cancelled_expired"] += 1
    bucket_list = [
        SalesBucket(
            period_start=key,
            total_orders=b["total"],
            captured_orders=b["captured"],
            pending_payment_orders=b["pending"],
            failed_payment_orders=b["failed"],
            collected_orders=b["collected"],
            cancelled_or_expired_orders=b["cancelled_expired"],
            captured_order_value=_money(b["value"]),
        )
        for key, b in sorted(buckets.items())
    ]
    totals = SalesBucket(
        period_start="total",
        total_orders=sum(b.total_orders for b in bucket_list),
        captured_orders=sum(b.captured_orders for b in bucket_list),
        pending_payment_orders=sum(b.pending_payment_orders for b in bucket_list),
        failed_payment_orders=sum(b.failed_payment_orders for b in bucket_list),
        collected_orders=sum(b.collected_orders for b in bucket_list),
        cancelled_or_expired_orders=sum(
            b.cancelled_or_expired_orders for b in bucket_list
        ),
        captured_order_value=_money(
            sum((Decimal(b.captured_order_value) for b in bucket_list), Decimal("0"))
        ),
    )
    return SalesAnalytics(
        period=period,
        store=_store_context(stores),
        group_by=group_by,
        reporting_timezone=tz_name,
        buckets=bucket_list,
        totals=totals,
    )


@router.get("/v1/merchant/dashboard/inventory", response_model=InventoryDashboard)
async def dashboard_inventory(
    store_id: UUID | None = Query(default=None),
    low_stock_threshold: int | None = Query(default=None, ge=0),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> InventoryDashboard:
    stores = _resolve_stores(await _authorized_stores(user, client), store_id)
    listings = await _fetch_listings(client, sorted(stores))
    low_stock: list[InventoryListingSummary] = []
    if low_stock_threshold is not None:
        low_stock = [
            InventoryListingSummary(
                listing_id=UUID(str(lst["id"])),
                title=lst["title"],
                status=lst["status"],
                available_quantity=int(lst["available_quantity"] or 0),
                reserved_quantity=int(lst["reserved_quantity"] or 0),
                sold_quantity=int(lst["sold_quantity"] or 0),
                sale_ends_at=_parse_time(lst.get("sale_ends_at")),
            )
            for lst in listings
            if int(lst["available_quantity"] or 0) <= low_stock_threshold
        ]
    return InventoryDashboard(
        period=DashboardPeriod(**{"from": None, "to": None}),
        store=_store_context(stores),
        summary=_inventory_metrics(listings),
        low_stock_listings=low_stock,
    )


@router.get("/v1/merchant/dashboard/pickups", response_model=PickupDashboard)
async def dashboard_pickups(
    store_id: UUID | None = Query(default=None),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    category: str | None = Query(default=None),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> PickupDashboard:
    if category is not None and category not in (
        "upcoming",
        "in_window",
        "completed",
        "window_expired",
    ):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid category")
    period = _period(from_, to)
    stores = _resolve_stores(await _authorized_stores(user, client), store_id)
    orders = await _fetch_orders(client, sorted(stores), from_, to)
    now = datetime.now(UTC)
    items_by_order: dict[str, int] = {}
    relevant = [
        o
        for o in orders
        if o["status"] in ("confirmed", "ready_for_pickup", "collected")
    ]
    if relevant:
        try:
            item_rows = await client.query(
                "order_items",
                select="order_id,quantity",
                filters={
                    "order_id": f"in.({','.join(sorted({o['id'] for o in relevant}))})"
                },
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        for row in item_rows:
            items_by_order[row["order_id"]] = items_by_order.get(
                row["order_id"], 0
            ) + int(row["quantity"])
    summaries = [
        PickupOrderSummary(
            order_number=o["order_number"],
            status=o["status"],
            pickup_starts_at=_parse_time(o["pickup_starts_at"]),  # type: ignore[arg-type]
            pickup_ends_at=_parse_time(o["pickup_ends_at"]),  # type: ignore[arg-type]
            category=_pickup_category(o, now),
            total_quantity=items_by_order.get(o["id"], 0),
        )
        for o in relevant
    ]
    if category is not None:
        summaries = [s for s in summaries if s.category == category]
    return PickupDashboard(
        period=period,
        store=_store_context(stores),
        counts=_pickup_metrics(orders, now),
        orders=summaries,
    )


@router.get("/v1/merchant/dashboard/stores", response_model=StoreComparison)
async def dashboard_stores(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None, alias="to"),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> StoreComparison:
    period = _period(from_, to)
    stores = await _authorized_stores(user, client)
    store_ids = sorted(stores)
    orders = await _fetch_orders(client, store_ids, from_, to)
    listings = await _fetch_listings(client, store_ids)
    reviews = await _fetch_visible_review_ratings(client, store_ids)
    orders_by_store: dict[str, list[dict]] = {sid: [] for sid in store_ids}
    for order in orders:
        orders_by_store.setdefault(order["store_id"], []).append(order)
    listings_by_store: dict[str, list[dict]] = {sid: [] for sid in store_ids}
    for listing in listings:
        listings_by_store.setdefault(listing["store_id"], []).append(listing)
    reviews_by_store: dict[str, list[dict]] = {sid: [] for sid in store_ids}
    for review in reviews:
        reviews_by_store.setdefault(review["store_id"], []).append(review)
    rows = []
    for sid in store_ids:
        store = stores[sid]
        store_orders = orders_by_store.get(sid, [])
        store_listings = listings_by_store.get(sid, [])
        rating = _rating_metrics(reviews_by_store.get(sid, []))
        captured = sum(
            (
                _dec(o["total_amount"])
                for o in store_orders
                if o["payment_status"] == "captured"
            ),
            Decimal("0"),
        )
        rows.append(
            StoreComparisonRow(
                store_id=UUID(sid),
                store_name=store["name"],
                store_status=store["status"],
                total_orders=len(store_orders),
                captured_order_value=_money(captured),
                collected_orders=sum(
                    1 for o in store_orders if o["status"] == "collected"
                ),
                active_listings=sum(
                    1 for lst in store_listings if lst["status"] == "active"
                ),
                available_units=sum(
                    int(lst["available_quantity"] or 0) for lst in store_listings
                ),
                average_rating=rating.average_rating,
                review_count=rating.total_visible_reviews,
            )
        )
    return StoreComparison(period=period, stores=rows)
