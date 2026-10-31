"""Platform admin dashboard and operations (Milestone 11).

AUTHORIZATION — READ THIS FIRST, because it is the
whole security story of this milestone:

Platform roles exist in the database: platform_role
enum (support_agent, finance_admin, compliance_admin,
operations_admin, super_admin) on
public.platform_user_roles, with revoked_at null
meaning active, enforced by the SECURITY DEFINER
function has_platform_role(). Roles are NEVER taken
from the request: they are read from the database
through the existing RBAC helper, which also filters
revoked rows again in Python.

BUT there is a verified gap in the existing model:
the ONLY SELECT policy on platform_user_roles is
"platform_roles_admin_read", which permits reading
only when has_platform_role([super_admin,
operations_admin]) holds. A support_agent,
finance_admin, or compliance_admin therefore CANNOT
read their own platform_user_roles row through the
user-context client — the RBAC query returns no rows
for them, even though their role is real and RLS
grants them data visibility elsewhere (merchants,
orders, listings, stores). The API gate below is
therefore FAIL-CLOSED: admin endpoints accept ONLY
operations_admin and super_admin, the two roles whose
authorization IS verifiable through the user-context
query. Support, finance, and compliance admins get
403 from the API until a verification capability is
approved (see "Proposed change" in architecture.md:
an own-row read policy, or a dedicated verification
RPC). Merchant owners, store managers, and finance
viewers are never platform admins: merchant membership
is a different table and grants nothing here, and a
frontend-supplied role flag is never read.

Second layer: the review RPCs re-check the reviewer
themselves (SECURITY DEFINER, reading
platform_user_roles directly, bypassing that SELECT
policy): backend_review_merchant and
backend_review_store accept compliance_admin,
operations_admin, and super_admin, and raise
reviewer_not_authorized (42501) otherwise. The API
passes reviewer_id = the authenticated user's id,
never a client-supplied id.

DATA ACCESS LIMITS (all verified, none bypassed):
- Merchants: SELECT policy allows approved merchants,
  members, or ANY platform role — so an ops/super
  admin sees all merchants including pending ones.
- Stores: public, member, or ops/compliance/super.
- Listings: public-or-member, or ops/compliance/super.
- Orders: customer, store operator, or
  support/finance/ops/super (NOT compliance).
- Order items/events: can_view_order, which includes
  ALL five platform roles.
- Reviews: visible-or-own — hidden and under_review
  reviews are NOT visible to platform admins through
  the user-context client. The admin review list
  therefore shows visible reviews in practice.
- Profiles: own-only — total registered customers
  CANNOT be counted safely and is omitted, not
  estimated.
- private.payment_transactions, private.payment_
  webhook_events, private.pickup_events,
  private.audit_logs: NOT accessible through PostgREST
  (private schema) and the service client may not
  query tables. Payment/refund visibility therefore
  comes from ORDERS (payment_status, amounts,
  timestamps) only — no gateway ids, signatures, or
  provider payloads, ever. Activity comes from
  order_status_events only; merchant/store review
  actions live in private.audit_logs and are NOT
  readable here, so they are not fabricated.
- The service client is used ONLY for the two approved
  backend_* RPCs (review_merchant, review_store),
  never for table queries, and only after the API gate
  has passed.

Money: Decimal only, serialized as strings. Captured
order value = sum of order total_amount where
payment_status is captured, nothing else. It is NOT
earnings, settlement, or net revenue. Refund-pending
is not refunded; only status refunded counts as a
completed refund, and no refund amounts are estimated.

Pagination is database-side: the client passes
order/limit/offset through to PostgREST, and totals
come from a separate id-only query with the same
filters — never a full-table fetch into Python.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_service_client, get_user_client
from app.errors import ApiError, NotFoundError
from app.rbac import require_platform_role, reviewer_id_for
from app.schemas import (
    AdminActivityEvent,
    AdminDashboard,
    AdminListingSummary,
    AdminMerchantDetail,
    AdminMerchantReviewRequest,
    AdminMerchantReviewResponse,
    AdminMerchantSummary,
    AdminOrderDetail,
    AdminOrderEventSummary,
    AdminOrderItemSummary,
    AdminOrderSummary,
    AdminPaymentException,
    AdminReviewRow,
    AdminStoreDetail,
    AdminStoreReviewRequest,
    AdminStoreReviewResponse,
    AdminStoreSummary,
    AuthenticatedUser,
    PlatformRole,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["admin"])

# Fail-closed gate: only the two platform roles whose
# authorization is verifiable through the user-context
# query (see module docstring). Every route uses it.
AdminGate = require_platform_role(
    PlatformRole.operations_admin, PlatformRole.super_admin
)

_MERCHANT_SELECT = (
    "id,legal_name,display_name,business_type,business_email,business_phone,"
    "status,verification_status,onboarding_notes,created_by,approved_at,"
    "approved_by,created_at,updated_at"
)
_STORE_SELECT = (
    "id,merchant_id,name,status,city,state,pincode,address_line_1,locality,"
    "timezone,created_at"
)
_LISTING_SELECT = (
    "id,store_id,title,selling_price,currency,total_quantity,reserved_quantity,"
    "sold_quantity,available_quantity,status,sale_starts_at,sale_ends_at,"
    "created_at,updated_at,category_id"
)
_ORDER_SELECT = (
    "id,order_number,store_id,status,payment_status,total_amount,currency,"
    "pickup_starts_at,pickup_ends_at,collected_at,customer_note,created_at,updated_at"
)


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _money(value: object) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def _page_params(page: int, page_size: int) -> dict[str, str]:
    return {
        "order": "created_at.desc,id.desc",
        "limit": str(page_size),
        "offset": str((page - 1) * page_size),
    }


async def _count(
    client: SupabaseRestClient, table: str, filters: dict[str, str]
) -> int:
    rows = await client.query(table, select="id", filters=filters)
    return len(rows)


async def _stores_by_id(
    client: SupabaseRestClient, store_ids: list[str]
) -> dict[str, dict]:
    if not store_ids:
        return {}
    rows = await client.query(
        "stores",
        select="id,merchant_id,name,status,city",
        filters={"id": f"in.({','.join(sorted(set(store_ids)))})"},
    )
    return {str(r["id"]): r for r in rows}


async def _merchants_by_id(
    client: SupabaseRestClient, merchant_ids: list[str]
) -> dict[str, dict]:
    if not merchant_ids:
        return {}
    rows = await client.query(
        "merchants",
        select="id,display_name",
        filters={"id": f"in.({','.join(sorted(set(merchant_ids)))})"},
    )
    return {str(r["id"]): r for r in rows}


def _merchant_summary(row: dict, store_count: int) -> AdminMerchantSummary:
    return AdminMerchantSummary(
        id=UUID(str(row["id"])),
        legal_name=row["legal_name"],
        display_name=row["display_name"],
        business_type=row["business_type"],
        status=row["status"],
        verification_status=row["verification_status"],
        store_count=store_count,
        created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
        approved_at=_parse_time(row.get("approved_at")),
    )


def _store_summary(
    row: dict, merchant_name: str, listing_count: int = 0, order_count: int = 0
) -> AdminStoreSummary:
    return AdminStoreSummary(
        id=UUID(str(row["id"])),
        merchant_id=UUID(str(row["merchant_id"])),
        merchant_name=merchant_name,
        name=row["name"],
        status=row["status"],
        city=row["city"],
        pincode=row["pincode"],
        listing_count=listing_count,
        order_count=order_count,
        created_at=_parse_time(row.get("created_at")),
    )


def _order_summary(
    row: dict, stores: dict[str, dict], merchants: dict[str, dict]
) -> AdminOrderSummary:
    store = stores.get(row["store_id"], {})
    merchant = merchants.get(store.get("merchant_id", ""), {})
    return AdminOrderSummary(
        id=UUID(str(row["id"])),
        order_number=row["order_number"],
        store_id=UUID(str(row["store_id"])),
        store_name=store.get("name", ""),
        merchant_name=merchant.get("display_name", ""),
        status=row["status"],
        payment_status=row["payment_status"],
        total_amount=_money(row["total_amount"]),
        currency=row["currency"],
        created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
    )


def _rpc_error_message(exc: Exception) -> str:
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                return str(body.get("message", ""))
        except ValueError:
            return ""
    return ""


@router.get("/v1/admin/dashboard", response_model=AdminDashboard)
async def admin_dashboard(
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> AdminDashboard:
    # Defence in depth: the gate already verified the
    # platform role; these reads are additionally
    # constrained by RLS to what the role may see.
    _ = user
    try:
        merchants = await client.query("merchants", select="id,status")
        stores = await client.query("stores", select="id,status")
        listings = await client.query("listings", select="id,status")
        orders = await client.query(
            "orders",
            select="id,order_number,store_id,status,payment_status,total_amount,currency,created_at",
        )
        reviews = await client.query(
            "reviews",
            select="rating",
            filters={"moderation_status": "eq.visible"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    m_status = [m["status"] for m in merchants]
    s_status = [s["status"] for s in stores]
    l_status = [lst["status"] for lst in listings]
    o_status = [o["status"] for o in orders]
    o_pay = [o["payment_status"] for o in orders]
    captured = sum(
        (
            Decimal(str(o["total_amount"]))
            for o in orders
            if o["payment_status"] == "captured"
        ),
        Decimal("0"),
    )
    ratings = [int(r["rating"]) for r in reviews]
    average = None
    if ratings:
        from decimal import ROUND_HALF_UP

        average = float(
            (Decimal(sum(ratings)) / Decimal(len(ratings))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
    recent = sorted(
        orders,
        key=lambda o: (o["created_at"], str(o["id"])),
        reverse=True,
    )[:5]
    stores_by_id = await _stores_by_id(client, [o["store_id"] for o in recent])
    merchants_by_id = await _merchants_by_id(
        client, [s["merchant_id"] for s in stores_by_id.values()]
    )
    return AdminDashboard(
        merchants_total=len(merchants),
        merchants_approved=sum(1 for s in m_status if s == "approved"),
        merchants_pending_review=sum(1 for s in m_status if s == "pending_review"),
        stores_total=len(stores),
        stores_active=sum(1 for s in s_status if s == "active"),
        stores_draft=sum(1 for s in s_status if s == "draft"),
        stores_inactive=sum(1 for s in s_status if s == "inactive"),
        stores_suspended=sum(1 for s in s_status if s == "suspended"),
        listings_total=len(listings),
        listings_published=sum(1 for s in l_status if s == "active"),
        listings_draft=sum(1 for s in l_status if s == "draft"),
        listings_paused=sum(1 for s in l_status if s == "paused"),
        listings_sold_out=sum(1 for s in l_status if s == "sold_out"),
        listings_expired=sum(1 for s in l_status if s == "expired"),
        orders_total=len(orders),
        orders_pending_payment=sum(1 for s in o_status if s == "pending_payment"),
        orders_confirmed=sum(1 for s in o_status if s == "confirmed"),
        orders_ready_for_pickup=sum(1 for s in o_status if s == "ready_for_pickup"),
        orders_collected=sum(1 for s in o_status if s == "collected"),
        orders_cancelled_or_expired=sum(
            1 for s in o_status if s in ("cancelled", "expired")
        ),
        captured_payment_count=sum(1 for p in o_pay if p == "captured"),
        captured_order_value=_money(captured),
        failed_payment_count=sum(1 for p in o_pay if p == "failed"),
        pending_payment_count=sum(1 for p in o_pay if p == "created"),
        reconciliation_required_count=sum(
            1 for p in o_pay if p == "reconciliation_required"
        ),
        refund_pending_count=sum(
            1
            for o in orders
            if o["status"] == "refund_pending"
            or o["payment_status"] == "refund_pending"
        ),
        visible_reviews_total=len(reviews),
        average_visible_rating=average,
        recent_orders=[
            _order_summary(o, stores_by_id, merchants_by_id) for o in recent
        ],
    )


@router.get("/v1/admin/merchants")
async def admin_merchants(
    status: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    _ = user
    filters: dict[str, str] = {}
    if status is not None:
        filters["status"] = f"eq.{status}"
    if verification_status is not None:
        filters["verification_status"] = f"eq.{verification_status}"
    # Search covers display_name via a database-side
    # ilike filter. legal_name search would need an OR
    # filter the client does not support — documented,
    # not faked with a local filter.
    if search:
        filters["display_name"] = f"ilike.*{search}*"
    try:
        total = await _count(client, "merchants", filters)
        rows = await client.query(
            "merchants",
            select=_MERCHANT_SELECT,
            filters={**filters, **_page_params(page, page_size)},
        )
        store_rows = await client.query("stores", select="id,merchant_id")
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    counts: dict[str, int] = {}
    for store in store_rows:
        counts[store["merchant_id"]] = counts.get(store["merchant_id"], 0) + 1
    return {
        "items": [
            _merchant_summary(r, counts.get(str(r["id"]), 0)).model_dump(mode="json")
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/v1/admin/merchants/{merchant_id}", response_model=AdminMerchantDetail)
async def admin_merchant_detail(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> AdminMerchantDetail:
    _ = user
    try:
        rows = await client.query(
            "merchants", select=_MERCHANT_SELECT, filters={"id": f"eq.{merchant_id}"}
        )
        if not rows:
            raise NotFoundError("Merchant not found")
        store_rows = await client.query(
            "stores", select=_STORE_SELECT, filters={"merchant_id": f"eq.{merchant_id}"}
        )
    except ApiError:
        raise
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    merchant = rows[0]
    return AdminMerchantDetail(
        id=merchant_id,
        legal_name=merchant["legal_name"],
        display_name=merchant["display_name"],
        business_type=merchant["business_type"],
        business_email=merchant.get("business_email"),
        business_phone=merchant.get("business_phone"),
        status=merchant["status"],
        verification_status=merchant["verification_status"],
        onboarding_notes=merchant.get("onboarding_notes"),
        created_at=_parse_time(merchant["created_at"]),  # type: ignore[arg-type]
        approved_at=_parse_time(merchant.get("approved_at")),
        stores=[_store_summary(s, merchant["display_name"]) for s in store_rows],
    )


@router.post(
    "/v1/admin/merchants/{merchant_id}/review",
    response_model=AdminMerchantReviewResponse,
)
async def admin_merchant_review(
    merchant_id: UUID,
    payload: AdminMerchantReviewRequest,
    user: AuthenticatedUser = Depends(AdminGate),
    service: SupabaseRestClient = Depends(get_service_client),
) -> AdminMerchantReviewResponse:
    """Approve or reject a merchant application through
    the approved server-only RPC only. The RPC itself
    re-checks the reviewer (compliance/ops/super) and
    records the action in private.audit_logs with the
    authenticated reviewer id. Approve requires
    verification_status verified AND a verified, current
    FSSAI document — both enforced by the RPC, not here."""
    new_status = "approved" if payload.action == "approve" else "rejected"
    verification_status = "verified" if payload.action == "approve" else "rejected"
    try:
        await service.rpc(
            "backend_review_merchant",
            {
                "p_merchant_id": str(merchant_id),
                "p_new_status": new_status,
                "p_verification_status": verification_status,
                "p_review_notes": payload.review_notes,
                "p_reviewer_id": reviewer_id_for(user),
            },
        )
    except Exception as exc:
        message = _rpc_error_message(exc)
        if message == "merchant_not_found":
            raise NotFoundError("Merchant not found") from exc
        if message == "reviewer_not_authorized":
            from app.errors import AuthorizationError

            raise AuthorizationError("Reviewer not authorized") from exc
        if message in (
            "merchant_documents_must_be_verified",
            "verified_fssai_document_required",
        ):
            raise ApiError(422, "VALIDATION_ERROR", message) from exc
        raise translate_upstream_error(exc) from exc
    return AdminMerchantReviewResponse(
        merchant_id=merchant_id,
        status=new_status,
        verification_status=verification_status,
    )


@router.get("/v1/admin/stores")
async def admin_stores(
    merchant_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    city: str | None = Query(default=None),
    pincode: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    _ = user
    filters: dict[str, str] = {}
    if merchant_id is not None:
        filters["merchant_id"] = f"eq.{merchant_id}"
    if status is not None:
        filters["status"] = f"eq.{status}"
    if city is not None:
        filters["city"] = f"eq.{city}"
    if pincode is not None:
        filters["pincode"] = f"eq.{pincode}"
    if search:
        filters["name"] = f"ilike.*{search}*"
    try:
        total = await _count(client, "stores", filters)
        rows = await client.query(
            "stores",
            select=_STORE_SELECT,
            filters={**filters, **_page_params(page, page_size)},
        )
        merchants = await _merchants_by_id(client, [r["merchant_id"] for r in rows])
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return {
        "items": [
            _store_summary(
                r, merchants.get(r["merchant_id"], {}).get("display_name", "")
            ).model_dump(mode="json")
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/v1/admin/stores/{store_id}", response_model=AdminStoreDetail)
async def admin_store_detail(
    store_id: UUID,
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> AdminStoreDetail:
    _ = user
    try:
        rows = await client.query(
            "stores", select=_STORE_SELECT, filters={"id": f"eq.{store_id}"}
        )
        if not rows:
            raise NotFoundError("Store not found")
        store = rows[0]
        merchants = await _merchants_by_id(client, [store["merchant_id"]])
        hours = await client.query(
            "store_hours",
            select="weekday,opens_at,closes_at",
            filters={"store_id": f"eq.{store_id}"},
        )
        listings = await client.query(
            "listings", select="id", filters={"store_id": f"eq.{store_id}"}
        )
        orders = await client.query(
            "orders", select="id", filters={"store_id": f"eq.{store_id}"}
        )
    except ApiError:
        raise
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return AdminStoreDetail(
        id=store_id,
        merchant_id=UUID(str(store["merchant_id"])),
        merchant_name=merchants.get(store["merchant_id"], {}).get("display_name", ""),
        name=store["name"],
        status=store["status"],
        city=store["city"],
        state=store["state"],
        pincode=store["pincode"],
        address_line_1=store["address_line_1"],
        locality=store.get("locality"),
        timezone=store.get("timezone") or "Asia/Kolkata",
        hours=hours,
        listing_count=len(listings),
        order_count=len(orders),
        created_at=_parse_time(store.get("created_at")),
    )


@router.post(
    "/v1/admin/stores/{store_id}/review",
    response_model=AdminStoreReviewResponse,
)
async def admin_store_review(
    store_id: UUID,
    payload: AdminStoreReviewRequest,
    user: AuthenticatedUser = Depends(AdminGate),
    service: SupabaseRestClient = Depends(get_service_client),
) -> AdminStoreReviewResponse:
    """Activate or deactivate a store through the approved
    server-only RPC only. Activation requires an approved
    + verified merchant, a store location, and store
    hours — all enforced by the RPC. The RPC records the
    action in private.audit_logs with the authenticated
    reviewer id."""
    try:
        await service.rpc(
            "backend_review_store",
            {
                "p_store_id": str(store_id),
                "p_activate": payload.activate,
                "p_reviewer_id": reviewer_id_for(user),
                "p_reason": payload.reason,
            },
        )
    except Exception as exc:
        message = _rpc_error_message(exc)
        if message == "store_not_found":
            raise NotFoundError("Store not found") from exc
        if message == "reviewer_not_authorized":
            from app.errors import AuthorizationError

            raise AuthorizationError("Reviewer not authorized") from exc
        if message in (
            "merchant_not_approved_and_verified",
            "store_location_required",
            "store_hours_required",
        ):
            raise ApiError(422, "VALIDATION_ERROR", message) from exc
        raise translate_upstream_error(exc) from exc
    return AdminStoreReviewResponse(store_id=store_id, activated=payload.activate)


@router.get("/v1/admin/listings")
async def admin_listings(
    merchant_id: UUID | None = Query(default=None),
    store_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    category_id: UUID | None = Query(default=None),
    city: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    _ = user
    filters: dict[str, str] = {}
    if store_id is not None:
        filters["store_id"] = f"eq.{store_id}"
    if status is not None:
        filters["status"] = f"eq.{status}"
    if category_id is not None:
        filters["category_id"] = f"eq.{category_id}"
    if search:
        filters["title"] = f"ilike.*{search}*"
    try:
        if merchant_id is not None:
            merchant_stores = await client.query(
                "stores", select="id", filters={"merchant_id": f"eq.{merchant_id}"}
            )
            store_ids = [s["id"] for s in merchant_stores]
            if not store_ids:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            filters["store_id"] = f"in.({','.join(sorted(store_ids))})"
        if city is not None:
            city_stores = await client.query(
                "stores", select="id", filters={"city": f"eq.{city}"}
            )
            city_ids = {s["id"] for s in city_stores}
            if "store_id" in filters and filters["store_id"].startswith("in.("):
                wanted = set(filters["store_id"][4:-1].split(","))
                city_ids &= wanted
            if not city_ids:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            filters["store_id"] = f"in.({','.join(sorted(city_ids))})"
        total = await _count(client, "listings", filters)
        rows = await client.query(
            "listings",
            select=_LISTING_SELECT,
            filters={**filters, **_page_params(page, page_size)},
        )
        stores = await _stores_by_id(client, [r["store_id"] for r in rows])
        merchants = await _merchants_by_id(
            client, [s["merchant_id"] for s in stores.values()]
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    items = []
    for row in rows:
        store = stores.get(row["store_id"], {})
        merchant = merchants.get(store.get("merchant_id", ""), {})
        items.append(
            AdminListingSummary(
                id=UUID(str(row["id"])),
                title=row["title"],
                store_id=UUID(str(row["store_id"])),
                store_name=store.get("name", ""),
                merchant_name=merchant.get("display_name", ""),
                selling_price=_money(row["selling_price"]),
                currency=row["currency"],
                total_quantity=row["total_quantity"],
                reserved_quantity=row["reserved_quantity"],
                sold_quantity=row["sold_quantity"],
                available_quantity=row["available_quantity"],
                status=row["status"],
                sale_starts_at=_parse_time(row["sale_starts_at"]),  # type: ignore[arg-type]
                sale_ends_at=_parse_time(row["sale_ends_at"]),  # type: ignore[arg-type]
                created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
                updated_at=_parse_time(row["updated_at"]),  # type: ignore[arg-type]
            ).model_dump(mode="json")
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/v1/admin/orders")
async def admin_orders(
    order_number: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None),
    payment_status: str | None = Query(default=None),
    store_id: UUID | None = Query(default=None),
    merchant_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    _ = user
    filters: dict[str, str] = {}
    if order_number is not None:
        filters["order_number"] = f"ilike.*{order_number}*"
    if status is not None:
        filters["status"] = f"eq.{status}"
    if payment_status is not None:
        filters["payment_status"] = f"eq.{payment_status}"
    if store_id is not None:
        filters["store_id"] = f"eq.{store_id}"
    try:
        if merchant_id is not None:
            merchant_stores = await client.query(
                "stores", select="id", filters={"merchant_id": f"eq.{merchant_id}"}
            )
            store_ids = [s["id"] for s in merchant_stores]
            if not store_ids:
                return {"items": [], "total": 0, "page": page, "page_size": page_size}
            filters["store_id"] = f"in.({','.join(sorted(store_ids))})"
        total = await _count(client, "orders", filters)
        rows = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={**filters, **_page_params(page, page_size)},
        )
        stores = await _stores_by_id(client, [r["store_id"] for r in rows])
        merchants = await _merchants_by_id(
            client, [s["merchant_id"] for s in stores.values()]
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return {
        "items": [
            _order_summary(r, stores, merchants).model_dump(mode="json") for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/v1/admin/orders/{order_id}", response_model=AdminOrderDetail)
async def admin_order_detail(
    order_id: UUID,
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> AdminOrderDetail:
    _ = user
    try:
        rows = await client.query(
            "orders", select=_ORDER_SELECT, filters={"id": f"eq.{order_id}"}
        )
        if not rows:
            raise NotFoundError("Order not found")
        order = rows[0]
        stores = await _stores_by_id(client, [order["store_id"]])
        merchants = await _merchants_by_id(
            client, [s["merchant_id"] for s in stores.values()]
        )
        items = await client.query(
            "order_items",
            select="listing_title_snapshot,quantity,unit_price,line_total",
            filters={"order_id": f"eq.{order_id}"},
        )
        events = await client.query(
            "order_status_events",
            select="from_status,to_status,actor_type,reason,created_at",
            filters={"order_id": f"eq.{order_id}"},
        )
    except ApiError:
        raise
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    store = stores.get(order["store_id"], {})
    merchant = merchants.get(store.get("merchant_id", ""), {})
    return AdminOrderDetail(
        id=order_id,
        order_number=order["order_number"],
        store_id=UUID(str(order["store_id"])),
        store_name=store.get("name", ""),
        merchant_name=merchant.get("display_name", ""),
        status=order["status"],
        payment_status=order["payment_status"],
        total_amount=_money(order["total_amount"]),
        currency=order["currency"],
        pickup_starts_at=_parse_time(order["pickup_starts_at"]),  # type: ignore[arg-type]
        pickup_ends_at=_parse_time(order["pickup_ends_at"]),  # type: ignore[arg-type]
        collected_at=_parse_time(order.get("collected_at")),
        customer_note=order.get("customer_note"),
        items=[
            AdminOrderItemSummary(
                title=i["listing_title_snapshot"],
                quantity=i["quantity"],
                unit_price=_money(i["unit_price"]),
                line_total=_money(i["line_total"]),
            )
            for i in items
        ],
        events=[
            AdminOrderEventSummary(
                from_status=e.get("from_status"),
                to_status=e["to_status"],
                actor_type=e["actor_type"],
                reason=e.get("reason"),
                created_at=_parse_time(e["created_at"]),  # type: ignore[arg-type]
            )
            for e in sorted(events, key=lambda ev: ev["created_at"])
        ],
        created_at=_parse_time(order["created_at"]),  # type: ignore[arg-type]
    )


@router.get("/v1/admin/payments")
async def admin_payments(
    payment_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    """Payment exception visibility from ORDERS only.
    private.payment_transactions is inaccessible by
    design, so no gateway ids, signatures, or provider
    payloads exist here — only order-level payment state
    and amounts."""
    _ = user
    filters: dict[str, str] = {}
    if payment_status is not None:
        filters["payment_status"] = f"eq.{payment_status}"
    try:
        total = await _count(client, "orders", filters)
        rows = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={**filters, **_page_params(page, page_size)},
        )
        stores = await _stores_by_id(client, [r["store_id"] for r in rows])
        merchants = await _merchants_by_id(
            client, [s["merchant_id"] for s in stores.values()]
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    items = []
    for row in rows:
        store = stores.get(row["store_id"], {})
        merchant = merchants.get(store.get("merchant_id", ""), {})
        items.append(
            AdminPaymentException(
                order_id=UUID(str(row["id"])),
                order_number=row["order_number"],
                store_name=store.get("name", ""),
                merchant_name=merchant.get("display_name", ""),
                amount=_money(row["total_amount"]),
                currency=row["currency"],
                payment_status=row["payment_status"],
                order_status=row["status"],
                created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
                updated_at=_parse_time(row["updated_at"]),  # type: ignore[arg-type]
            ).model_dump(mode="json")
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/v1/admin/refunds")
async def admin_refunds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    """Refund visibility from ORDERS only: an order is
    listed when its order status OR payment status is
    refund-related. Refund-pending is NOT refunded;
    only status refunded counts as completed, and no
    refund amounts are estimated (the order row carries
    none). No refund execution exists in this milestone."""
    _ = user
    try:
        # Two database-side queries (order status OR payment
        # status is refund-related); the client cannot express
        # an OR across columns, so the union is merged here.
        # No full-table fetch: each query is filtered.
        by_status = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={"status": "in.(refund_pending,refunded)"},
        )
        by_payment = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={
                "payment_status": "in.(refund_pending,partially_refunded,refunded)"
            },
        )
        merged = {r["id"]: r for r in by_status}
        merged.update({r["id"]: r for r in by_payment})
        all_rows = list(merged.values())
        stores = await _stores_by_id(client, [r["store_id"] for r in all_rows])
        merchants = await _merchants_by_id(
            client, [s["merchant_id"] for s in stores.values()]
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    refund_rows = all_rows
    refund_rows.sort(key=lambda r: (r["created_at"], str(r["id"])), reverse=True)
    page_rows = refund_rows[(page - 1) * page_size : page * page_size]
    items = []
    for row in page_rows:
        store = stores.get(row["store_id"], {})
        merchant = merchants.get(store.get("merchant_id", ""), {})
        items.append(
            AdminPaymentException(
                order_id=UUID(str(row["id"])),
                order_number=row["order_number"],
                store_name=store.get("name", ""),
                merchant_name=merchant.get("display_name", ""),
                amount=_money(row["total_amount"]),
                currency=row["currency"],
                payment_status=row["payment_status"],
                order_status=row["status"],
                created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
                updated_at=_parse_time(row["updated_at"]),  # type: ignore[arg-type]
            ).model_dump(mode="json")
        )
    return {
        "items": items,
        "total": len(refund_rows),
        "page": page,
        "page_size": page_size,
    }


@router.get("/v1/admin/reviews")
async def admin_reviews(
    store_id: UUID | None = Query(default=None),
    rating: int | None = Query(default=None, ge=1, le=5),
    moderation_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    _ = user
    filters: dict[str, str] = {}
    if store_id is not None:
        filters["store_id"] = f"eq.{store_id}"
    if rating is not None:
        filters["rating"] = f"eq.{rating}"
    if moderation_status is not None:
        filters["moderation_status"] = f"eq.{moderation_status}"
    try:
        total = await _count(
            client,
            "reviews",
            filters,
        )
        rows = await client.query(
            "reviews",
            select="id,store_id,rating,comment,moderation_status,created_at",
            filters={**filters, **_page_params(page, page_size)},
        )
        stores = await _stores_by_id(client, [r["store_id"] for r in rows])
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return {
        "items": [
            AdminReviewRow(
                id=UUID(str(r["id"])),
                store_id=UUID(str(r["store_id"])),
                store_name=stores.get(r["store_id"], {}).get("name", ""),
                rating=r["rating"],
                comment=r.get("comment"),
                moderation_status=r["moderation_status"],
                created_at=_parse_time(r["created_at"]),  # type: ignore[arg-type]
            ).model_dump(mode="json")
            for r in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/v1/admin/activity")
async def admin_activity(
    order_number: str | None = Query(default=None, max_length=100),
    store_id: UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(AdminGate),
    client: SupabaseRestClient = Depends(get_user_client),
) -> dict:
    """Activity = recorded order_status_events only.
    private.audit_logs, private.pickup_events, and
    private payment webhook events are not readable
    through the API by design and are not fabricated."""
    _ = user
    try:
        order_filters: dict[str, str] = {}
        if order_number is not None:
            order_filters["order_number"] = f"ilike.*{order_number}*"
        if store_id is not None:
            order_filters["store_id"] = f"eq.{store_id}"
        orders = await client.query(
            "orders", select="id,order_number", filters=order_filters
        )
        if not orders:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
        order_ids = [o["id"] for o in orders]
        order_numbers = {o["id"]: o["order_number"] for o in orders}
        total = await _count(
            client,
            "order_status_events",
            {"order_id": f"in.({','.join(sorted(order_ids))})"},
        )
        events = await client.query(
            "order_status_events",
            select="order_id,from_status,to_status,actor_type,reason,created_at",
            filters={
                "order_id": f"in.({','.join(sorted(order_ids))})",
                **_page_params(page, page_size),
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return {
        "items": [
            AdminActivityEvent(
                order_number=order_numbers.get(e["order_id"], ""),
                from_status=e.get("from_status"),
                to_status=e["to_status"],
                actor_type=e["actor_type"],
                reason=e.get("reason"),
                created_at=_parse_time(e["created_at"]),  # type: ignore[arg-type]
            ).model_dump(mode="json")
            for e in events
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
