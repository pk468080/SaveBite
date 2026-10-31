"""Customer marketplace and reservation initiation (Milestone 5).

Discovery is ANONYMOUS and read-only: it uses get_anon_client,
which authenticates as Supabase's anon role with the publishable
key only and raises before any insert, update, or RPC. It never
uses the service-role key, and it never carries a user identity.

Eligibility is enforced twice, on purpose:
1. RLS public policies (status active, sale window open,
   available > 0, public store) limit what PostgREST returns
   to anon/authenticated callers at all.
2. This router re-checks every rule in Python (status, windows
   against the current time, available > 0, store active with an
   approved merchant, category active) and projects only public
   fields, so a policy or grant change cannot silently widen
   what customers see, and a fake or permissive upstream cannot
   leak draft/paused/cancelled/sold-out listings.

Reservation is AUTHENTICATED and goes through the existing
user-context RPC create_order_reservation only. The database
is the authority for inventory, windows, store consistency,
expiry (~5 minutes), and idempotency. This router never inserts
or updates orders, order_items, inventory_reservations,
inventory_events, or inventory counters, and it never calls
begin_payment_checkout: a reservation is not a paid order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query

from app.dependencies import (
    get_anon_client,
    get_current_user,
    get_user_client,
)
from app.errors import ApiError, BadGatewayError, NotFoundError
from app.schemas import (
    AuthenticatedUser,
    CategoryResponse,
    DietaryClassification,
    ListingType,
    MarketplaceListingsResponse,
    MarketplaceSort,
    PublicListingImage,
    PublicListingSummary,
    PublicStoreSummary,
    ReservationCreate,
    ReservationResponse,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["marketplace"])

# Explicit PostgREST projection for public listings. created_by,
# created_at, updated_at, template_id and food_safety_notes are
# deliberately NOT selected, so they cannot leak even if a
# response model were widened later. created_at IS selected
# separately for the "newest" sort and stripped before response.
_PUBLIC_LISTING_SELECT = (
    "id,store_id,listing_type,category_id,title,description,"
    "contents_description,reference_value,selling_price,currency,"
    "total_quantity,reserved_quantity,sold_quantity,available_quantity,"
    "sale_starts_at,sale_ends_at,pickup_starts_at,pickup_ends_at,"
    "prepared_at,best_before_at,allergen_codes,dietary_classification,"
    "storage_instructions,status,created_at"
)

_LISTING_MEDIA_BUCKET = "listing-media"


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _is_eligible(
    listing: dict,
    public_store_ids: set[str],
    active_category_ids: set[str],
    now: datetime,
) -> bool:
    if listing.get("status") != "active":
        return False
    sale_starts = _parse_time(listing.get("sale_starts_at"))
    sale_ends = _parse_time(listing.get("sale_ends_at"))
    pickup_ends = _parse_time(listing.get("pickup_ends_at"))
    if sale_starts is None or sale_ends is None or pickup_ends is None:
        return False
    if not (sale_starts <= now < sale_ends):
        return False
    if not pickup_ends > now:
        return False
    available = listing.get("available_quantity")
    if available is None or available <= 0:
        return False
    if str(listing.get("store_id")) not in public_store_ids:
        return False
    category_id = listing.get("category_id")
    if category_id is not None and str(category_id) not in active_category_ids:
        return False
    return True


async def _public_stores_and_categories(
    client: SupabaseRestClient,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (public stores by id, active categories by id).

    A store is public only when status is active AND its merchant
    is approved — the same rule as private.is_store_public. Both
    are fetched through the anon client, so RLS public policies
    apply to these reads too."""
    try:
        stores = await client.query(
            "stores",
            select="id,merchant_id,name,locality,city,state,pincode,timezone,status",
            filters={"status": "eq.active"},
        )
        merchants = await client.query(
            "merchants",
            select="id,status",
            filters={"status": "eq.approved"},
        )
        categories = await client.query(
            "categories",
            select="id,parent_id,name,slug,display_order,is_active",
            filters={"is_active": "eq.true"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    approved_merchant_ids = {str(m["id"]) for m in merchants}
    public_stores = {
        str(s["id"]): s
        for s in stores
        if s.get("status") == "active"
        and str(s.get("merchant_id")) in approved_merchant_ids
    }
    active_categories = {
        str(c["id"]): c for c in categories if c.get("is_active") is not False
    }
    return public_stores, active_categories


async def _listing_images(
    client: SupabaseRestClient, listing_ids: list[str]
) -> dict[str, list[PublicListingImage]]:
    """Images for the given listings, validated to the
    listing-media bucket path rule. A row whose storage_path is
    not <listing_id>/<file> — including any URL — is dropped,
    never returned, because the API does not trust arbitrary
    image references."""
    if not listing_ids:
        return {}
    try:
        rows = await client.query(
            "listing_images",
            select="listing_id,storage_path,alt_text,display_order",
            filters={"listing_id": f"in.({','.join(listing_ids)})"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    by_listing: dict[str, list[PublicListingImage]] = {}
    for row in rows:
        listing_id = str(row.get("listing_id"))
        path = str(row.get("storage_path") or "")
        parts = path.split("/")
        if len(parts) < 2 or parts[0] != listing_id or ".." in parts:
            continue
        by_listing.setdefault(listing_id, []).append(
            PublicListingImage(
                storage_path=path,
                alt_text=row.get("alt_text"),
                display_order=row.get("display_order", 0) or 0,
            )
        )
    for images in by_listing.values():
        images.sort(key=lambda img: img.display_order)
    return by_listing


def _public_listing(
    listing: dict,
    stores: dict[str, dict],
    categories: dict[str, dict],
    images: dict[str, list[PublicListingImage]],
) -> PublicListingSummary:
    store = stores[str(listing["store_id"])]
    category = (
        categories.get(str(listing["category_id"]))
        if listing.get("category_id")
        else None
    )
    return PublicListingSummary(
        id=listing["id"],
        store=PublicStoreSummary(**store),
        listing_type=listing["listing_type"],
        category_id=listing.get("category_id"),
        category_name=category["name"] if category else None,
        title=listing["title"],
        description=listing.get("description"),
        contents_description=listing.get("contents_description"),
        reference_value=Decimal(str(listing["reference_value"])),
        selling_price=Decimal(str(listing["selling_price"])),
        currency=listing.get("currency", "INR"),
        available_quantity=listing.get("available_quantity") or 0,
        dietary_classification=listing.get("dietary_classification", "unknown"),
        allergen_codes=listing.get("allergen_codes") or [],
        storage_instructions=listing.get("storage_instructions"),
        sale_starts_at=_parse_time(listing["sale_starts_at"]),  # type: ignore[arg-type]
        sale_ends_at=_parse_time(listing["sale_ends_at"]),  # type: ignore[arg-type]
        pickup_starts_at=_parse_time(listing["pickup_starts_at"]),  # type: ignore[arg-type]
        pickup_ends_at=_parse_time(listing["pickup_ends_at"]),  # type: ignore[arg-type]
        prepared_at=_parse_time(listing.get("prepared_at")),
        best_before_at=_parse_time(listing.get("best_before_at")),
        images=images.get(str(listing["id"]), []),
    )


@router.get("/v1/marketplace/categories", response_model=list[CategoryResponse])
async def marketplace_categories(
    client: SupabaseRestClient = Depends(get_anon_client),
) -> list[CategoryResponse]:
    """Active categories only. No authentication required."""
    try:
        rows = await client.query(
            "categories",
            select="id,parent_id,name,slug,display_order,is_active",
            filters={"is_active": "eq.true"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    rows = [r for r in rows if r.get("is_active") is not False]
    rows.sort(key=lambda r: (r.get("display_order", 0), r.get("name", "")))
    return [CategoryResponse(**row) for row in rows]


@router.get("/v1/marketplace/listings", response_model=MarketplaceListingsResponse)
async def marketplace_listings(
    city: str | None = Query(default=None, max_length=200),
    pincode: str | None = Query(default=None, pattern=r"^[1-9][0-9]{5}$"),
    category_id: UUID | None = Query(default=None),
    listing_type: ListingType | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    # Price bounds are validated in code (not Query ge=) because
    # FastAPI's Query type stubs do not accept Decimal bounds.
    min_price: Decimal | None = Query(default=None),
    max_price: Decimal | None = Query(default=None),
    dietary: DietaryClassification | None = Query(default=None),
    sort: MarketplaceSort = Query(default=MarketplaceSort.newest),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    client: SupabaseRestClient = Depends(get_anon_client),
) -> MarketplaceListingsResponse:
    """Browse eligible public listings. No authentication required.

    Filters are validated here and eligibility is re-checked in
    Python (see module docstring). Pagination is applied AFTER
    filtering and sorting, with a stable id tiebreak, so pages
    do not randomly reorder. Distance sorting is deliberately
    NOT offered: it would need a PostGIS RPC or schema change,
    which is a documented future enhancement, not a silent
    invention here."""
    if (min_price is not None and min_price < 0) or (
        max_price is not None and max_price < 0
    ):
        raise ApiError(422, "VALIDATION_ERROR", "prices must not be negative")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise ApiError(422, "VALIDATION_ERROR", "min_price must not exceed max_price")
    now = datetime.now(UTC)
    stores, categories = await _public_stores_and_categories(client)
    # City / PIN code filter on stores first: listings carry no
    # city or PIN code of their own.
    store_ids = set(stores)
    if city is not None:
        wanted = city.strip().lower()
        store_ids = {
            sid
            for sid in store_ids
            if str(stores[sid].get("city", "")).strip().lower() == wanted
        }
    if pincode is not None:
        store_ids = {
            sid for sid in store_ids if str(stores[sid].get("pincode")) == pincode
        }
    if not store_ids:
        return MarketplaceListingsResponse(
            items=[], total=0, page=page, page_size=page_size
        )
    try:
        rows = await client.query(
            "listings",
            select=_PUBLIC_LISTING_SELECT,
            filters={
                "status": "eq.active",
                "store_id": f"in.({','.join(sorted(store_ids))})",
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    eligible = [
        row for row in rows if _is_eligible(row, store_ids, set(categories), now)
    ]
    if category_id is not None:
        eligible = [
            r for r in eligible if str(r.get("category_id")) == str(category_id)
        ]
    if listing_type is not None:
        eligible = [r for r in eligible if r.get("listing_type") == listing_type.value]
    if min_price is not None:
        eligible = [
            r for r in eligible if Decimal(str(r["selling_price"])) >= min_price
        ]
    if max_price is not None:
        eligible = [
            r for r in eligible if Decimal(str(r["selling_price"])) <= max_price
        ]
    if dietary is not None:
        eligible = [
            r for r in eligible if r.get("dietary_classification") == dietary.value
        ]
    if search is not None:
        term = search.strip().lower()
        if term:
            eligible = [
                r
                for r in eligible
                if term in str(r.get("title", "")).lower()
                or term in str(r.get("description", "")).lower()
                or term in str(r.get("contents_description", "")).lower()
            ]
    # Stable sort: id ascending first, then a stable sort by the
    # primary key, so the id tiebreak always stays ascending and
    # pages never reorder randomly.
    eligible.sort(key=lambda r: str(r["id"]))
    if sort is MarketplaceSort.lowest_price:
        eligible.sort(key=lambda r: Decimal(str(r["selling_price"])))
    elif sort is MarketplaceSort.highest_price:
        eligible.sort(key=lambda r: Decimal(str(r["selling_price"])), reverse=True)
    elif sort is MarketplaceSort.ending_soon:
        eligible.sort(
            key=lambda r: (
                _parse_time(r.get("sale_ends_at")) or datetime.max.replace(tzinfo=UTC)
            )
        )
    else:  # newest
        eligible.sort(
            key=lambda r: (
                _parse_time(r.get("created_at")) or datetime.min.replace(tzinfo=UTC)
            ),
            reverse=True,
        )
    total = len(eligible)
    start = (page - 1) * page_size
    page_rows = eligible[start : start + page_size]
    images = await _listing_images(client, [str(r["id"]) for r in page_rows])
    items = [_public_listing(row, stores, categories, images) for row in page_rows]
    return MarketplaceListingsResponse(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get(
    "/v1/marketplace/listings/{listing_id}", response_model=PublicListingSummary
)
async def marketplace_listing_detail(
    listing_id: UUID,
    client: SupabaseRestClient = Depends(get_anon_client),
) -> PublicListingSummary:
    """Public listing details. No authentication required. A
    listing that is not eligible for discovery returns 404 —
    its existence is not leaked to anonymous callers."""
    stores, categories = await _public_stores_and_categories(client)
    try:
        rows = await client.query(
            "listings",
            select=_PUBLIC_LISTING_SELECT,
            filters={"id": f"eq.{listing_id}", "status": "eq.active"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    now = datetime.now(UTC)
    for row in rows:
        if _is_eligible(row, set(stores), set(categories), now):
            images = await _listing_images(client, [str(listing_id)])
            return _public_listing(row, stores, categories, images)
    raise NotFoundError("Listing not found")


@router.post(
    "/v1/orders/reservations", response_model=ReservationResponse, status_code=201
)
async def create_reservation(
    payload: ReservationCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ReservationResponse:
    """Create a reservation. Authentication REQUIRED. The
    Idempotency-Key header is validated here (8–128 characters,
    matching the database rule) and passed unchanged to the RPC.
    The RPC is the authority for inventory, windows, store
    consistency, expiry, and replay behaviour. This endpoint
    creates a reservation only — it does not charge, confirm
    payment, or call begin_payment_checkout."""
    if idempotency_key is None:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key header is required")
    key = idempotency_key.strip()
    if len(key) < 8 or len(key) > 128:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Idempotency-Key must be between 8 and 128 characters",
        )
    try:
        result = await client.rpc(
            "create_order_reservation",
            {
                "p_store_id": str(payload.store_id),
                "p_items": [
                    {"listing_id": str(item.listing_id), "quantity": item.quantity}
                    for item in payload.items
                ],
                "p_idempotency_key": key,
                "p_customer_note": payload.customer_note,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not isinstance(result, dict) or not result.get("order_id"):
        raise BadGatewayError("Reservation RPC returned no order")
    return ReservationResponse(
        order_id=result["order_id"],
        order_number=result["order_number"],
        status=result["status"],
        total_amount=Decimal(str(result["total_amount"])),
        currency=result.get("currency", "INR"),
        reservation_expires_at=_parse_time(result.get("reservation_expires_at")),
        pickup_starts_at=_parse_time(result["pickup_starts_at"]),  # type: ignore[arg-type]
        pickup_ends_at=_parse_time(result["pickup_ends_at"]),  # type: ignore[arg-type]
        idempotent_replay=bool(result.get("idempotent_replay", False)),
    )
