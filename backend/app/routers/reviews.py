"""Customer reviews and ratings (Milestone 9).

Verified database contract (from the baseline):
- public.reviews: id, order_id (FK orders ON DELETE
  RESTRICT), customer_id (FK auth.users), store_id (FK
  stores), merchant_id (FK merchants), rating smallint
  CHECK 1-5, comment text nullable, moderation_status
  text CHECK ('visible','hidden','under_review') DEFAULT
  'visible', created_at, updated_at (set_updated_at
  trigger). UNIQUE(order_id) — one review per order,
  enforced by the database, including under concurrent
  submissions: two racing inserts cannot both succeed.
- Reviews are per STORE and per ORDER. There is no
  listing_id, no rating dimensions, no merchant-response
  column, no report table, and no aggregate view or
  function. None is invented here.
- RLS, the only policies on the table:
  - INSERT to authenticated WITH CHECK: customer_id =
    auth.uid() AND an order exists with id = order_id,
    customer_id = auth.uid(), store_id = reviews.store_id,
    merchant_id = reviews.merchant_id, status =
    'collected'. Eligibility is therefore a database
    rule, not an API claim: pending_payment, confirmed,
    ready_for_pickup, expired, cancelled, and
    refund_pending orders can never produce a review,
    and neither can another customer's order.
  - SELECT to anon + authenticated USING:
    moderation_status = 'visible' OR customer_id =
    auth.uid(). Public readers see visible reviews only;
    a customer also sees their own hidden/under_review
    reviews in their own history.
  - NO UPDATE and NO DELETE policy: reviews are
    immutable after submission through this API. There
    is no edit or delete endpoint in this milestone, and
    no moderation endpoint (moderation_status can only
    change outside the API, e.g. by a platform admin
    acting directly on the database — a future change
    would need its own policy/RPC and approval).
- Column grants for reviews are NOT reproduced in the
  consolidated baseline, so the insert path's grant
  surface is unverified from the baseline alone and must
  be confirmed against live before production use. The
  RLS policies above are verified; grants are the one
  open verification item, documented, not assumed.

API design consequences:
- Store and merchant ids are ALWAYS taken from the
  order row, never from the request body. The request
  carries only rating + comment.
- The API pre-checks order ownership and collected
  status for a clean 404/422, but the RLS INSERT check
  remains the final authority: if the order's status
  changes between the pre-check and the insert, the
  insert fails and the API reports ineligibility.
- Rating summary: there is no database aggregate, so
  the summary fetches ONLY the rating column of visible
  reviews for one store and aggregates in Python. That
  is a pilot-scale approach, documented honestly: at
  large scale it must be replaced by the proposed
  store_rating_summary view (documented in architecture,
  NOT applied). No full review rows are fetched for the
  summary, and the summary and the public list use the
  same visibility rule (moderation_status = 'visible').
- Marketplace responses are NOT changed: adding a store
  rating to every listing would need the same aggregate
  source plus a batched lookup, and inventing one here
  would risk N+1 queries. The rating-summary endpoint is
  the integration point until the proposed view exists.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query

from app.dependencies import (
    get_anon_client,
    get_current_user,
    get_user_client,
)
from app.errors import ApiError, NotFoundError
from app.schemas import (
    AuthenticatedUser,
    PublicReviewListResponse,
    PublicReviewResponse,
    ReviewCreateRequest,
    ReviewListResponse,
    ReviewResponse,
    StoreRatingSummary,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["reviews"])

_REVIEW_SELECT = (
    "id,order_id,customer_id,store_id,rating,comment,moderation_status,created_at"
)
_ORDER_SELECT = "id,order_number,store_id,merchant_id,status"
_STORE_SELECT = "id,name"
_MODERATION_STATUSES = ("visible", "hidden", "under_review")


def _parse_time(value: object):
    from datetime import datetime

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _pg_code(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                return str(body.get("code", ""))
        except ValueError:
            return ""
    return ""


async def _store_name(client: SupabaseRestClient, store_id: str) -> str:
    rows = await client.query(
        "stores", select=_STORE_SELECT, filters={"id": f"eq.{store_id}"}
    )
    return rows[0]["name"] if rows else ""


async def _orders_by_id(
    client: SupabaseRestClient, order_ids: list[str]
) -> dict[str, dict]:
    if not order_ids:
        return {}
    rows = await client.query(
        "orders",
        select="id,order_number",
        filters={"id": f"in.({','.join(sorted(set(order_ids)))})"},
    )
    return {str(r["id"]): r for r in rows}


async def _stores_by_id(
    client: SupabaseRestClient, store_ids: list[str]
) -> dict[str, dict]:
    if not store_ids:
        return {}
    rows = await client.query(
        "stores",
        select=_STORE_SELECT,
        filters={"id": f"in.({','.join(sorted(set(store_ids)))})"},
    )
    return {str(r["id"]): r for r in rows}


def _paginate(rows: list, page: int, page_size: int) -> list:
    return rows[(page - 1) * page_size : page * page_size]


@router.post("/v1/orders/{order_id}/review", response_model=ReviewResponse)
async def create_review(
    order_id: UUID,
    payload: ReviewCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ReviewResponse:
    """Submit one review for the caller's own collected
    order. Store and merchant come from the order row;
    the customer id comes from Auth. Duplicate reviews
    are rejected by the UNIQUE(order_id) constraint."""
    try:
        order_rows = await client.query(
            "orders",
            select=_ORDER_SELECT,
            filters={"id": f"eq.{order_id}", "customer_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not order_rows:
        raise NotFoundError("Order not found")
    order = order_rows[0]
    if order["status"] != "collected":
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Only collected orders can be reviewed",
        )
    comment = payload.comment.strip() if payload.comment else None
    if comment == "":
        comment = None
    try:
        inserted = await client.insert(
            "reviews",
            {
                "order_id": str(order_id),
                "customer_id": str(user.id),
                "store_id": order["store_id"],
                "merchant_id": order["merchant_id"],
                "rating": payload.rating,
                "comment": comment,
            },
        )
    except Exception as exc:
        if _pg_code(exc) == "23505":
            raise ApiError(
                409, "CONFLICT", "This order has already been reviewed"
            ) from exc
        if _pg_code(exc) == "42501":
            # RLS disagreed with the pre-check (e.g. the
            # order's status changed concurrently): report
            # ineligibility, not a permission error.
            raise ApiError(
                422, "VALIDATION_ERROR", "Order is not eligible for review"
            ) from exc
        raise translate_upstream_error(exc) from exc
    if not inserted:
        from app.errors import BadGatewayError

        raise BadGatewayError("Review could not be created")
    review = inserted[0]
    try:
        store_name = await _store_name(client, order["store_id"])
    except Exception:
        store_name = ""
    return ReviewResponse(
        id=UUID(str(review["id"])),
        order_number=order["order_number"],
        store_name=store_name,
        rating=review["rating"],
        comment=review.get("comment"),
        moderation_status=review.get("moderation_status", "visible"),
        created_at=_parse_time(review["created_at"]),  # type: ignore[arg-type]
    )


@router.get("/v1/my/reviews", response_model=ReviewListResponse)
async def my_reviews(
    rating: int | None = Query(default=None, ge=1, le=5),
    moderation_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ReviewListResponse:
    """The caller's own reviews, newest first. The SELECT
    policy already restricts to the caller's rows, and the
    customer_id filter is applied again here so another
    customer's rows can never appear even if a policy
    were widened. Own hidden/under_review reviews are
    visible here (policy allows them to the owner)."""
    if moderation_status is not None and moderation_status not in _MODERATION_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "Invalid moderation_status")
    filters: dict[str, str] = {"customer_id": f"eq.{user.id}"}
    if rating is not None:
        filters["rating"] = f"eq.{rating}"
    if moderation_status is not None:
        filters["moderation_status"] = f"eq.{moderation_status}"
    try:
        rows = await client.query("reviews", select=_REVIEW_SELECT, filters=filters)
        orders = await _orders_by_id(client, [r["order_id"] for r in rows])
        stores = await _stores_by_id(client, [r["store_id"] for r in rows])
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    rows.sort(key=lambda r: (r["created_at"], str(r["id"])), reverse=True)
    page_rows = _paginate(rows, page, page_size)
    items = [
        ReviewResponse(
            id=UUID(str(r["id"])),
            order_number=orders.get(r["order_id"], {}).get("order_number", ""),
            store_name=stores.get(r["store_id"], {}).get("name", ""),
            rating=r["rating"],
            comment=r.get("comment"),
            moderation_status=r["moderation_status"],
            created_at=_parse_time(r["created_at"]),  # type: ignore[arg-type]
        )
        for r in page_rows
    ]
    return ReviewListResponse(
        items=items, total=len(rows), page=page, page_size=page_size
    )


@router.get("/v1/stores/{store_id}/reviews", response_model=PublicReviewListResponse)
async def public_store_reviews(
    store_id: UUID,
    sort: str = Query(default="newest"),
    rating: int | None = Query(default=None, ge=1, le=5),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    client: SupabaseRestClient = Depends(get_anon_client),
) -> PublicReviewListResponse:
    """Public, anonymous-readable store reviews: visible
    reviews only (the SELECT policy enforces this for
    anon readers, and the filter is applied explicitly
    too). No customer data of any kind is returned."""
    if sort not in ("newest", "highest", "lowest"):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid sort")
    filters: dict[str, str] = {
        "store_id": f"eq.{store_id}",
        "moderation_status": "eq.visible",
    }
    if rating is not None:
        filters["rating"] = f"eq.{rating}"
    try:
        store_rows = await client.query(
            "stores", select=_STORE_SELECT, filters={"id": f"eq.{store_id}"}
        )
        if not store_rows:
            raise NotFoundError("Store not found")
        rows = await client.query("reviews", select=_REVIEW_SELECT, filters=filters)
    except ApiError:
        raise
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if sort == "newest":
        rows.sort(key=lambda r: (r["created_at"], str(r["id"])), reverse=True)
    elif sort == "highest":
        rows.sort(
            key=lambda r: (r["rating"], r["created_at"], str(r["id"])), reverse=True
        )
    else:
        rows.sort(key=lambda r: (r["rating"], r["created_at"], str(r["id"])))
    page_rows = _paginate(rows, page, page_size)
    items = [
        PublicReviewResponse(
            id=UUID(str(r["id"])),
            rating=r["rating"],
            comment=r.get("comment"),
            created_at=_parse_time(r["created_at"]),  # type: ignore[arg-type]
        )
        for r in page_rows
    ]
    return PublicReviewListResponse(
        items=items,
        total=len(rows),
        page=page,
        page_size=page_size,
        store_name=store_rows[0]["name"],
    )


@router.get("/v1/stores/{store_id}/rating-summary", response_model=StoreRatingSummary)
async def store_rating_summary(
    store_id: UUID,
    client: SupabaseRestClient = Depends(get_anon_client),
) -> StoreRatingSummary:
    """Aggregate over visible reviews only, so it always
    agrees with the public list. Only the rating column
    is fetched (no review text, no customer data); the
    average is the mean of those ratings, rounded
    half-up to 2 decimal places. Pilot-scale approach:
    at large scale replace with a database view (see
    architecture docs — proposed, NOT applied)."""
    try:
        store_rows = await client.query(
            "stores", select=_STORE_SELECT, filters={"id": f"eq.{store_id}"}
        )
        if not store_rows:
            raise NotFoundError("Store not found")
        rows = await client.query(
            "reviews",
            select="rating",
            filters={
                "store_id": f"eq.{store_id}",
                "moderation_status": "eq.visible",
            },
        )
    except ApiError:
        raise
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    total = Decimal(0)
    for row in rows:
        rating = int(row["rating"])
        if rating in counts:
            counts[rating] += 1
            total += Decimal(rating)
    total_count = len(rows)
    average = None
    if total_count:
        average = float(
            (total / Decimal(total_count)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        )
    return StoreRatingSummary(
        store_id=store_id,
        store_name=store_rows[0]["name"],
        average_rating=average,
        total_reviews=total_count,
        five_star=counts[5],
        four_star=counts[4],
        three_star=counts[3],
        two_star=counts[2],
        one_star=counts[1],
    )
