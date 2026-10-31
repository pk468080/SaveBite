"""Listings and inventory (Milestone 4).

Writes go through PostgREST with the user-context client, under
the listings RLS policies and column grants audited in Stage 1
(see docs/architecture.md for the full audit). The important
consequences, enforced here rather than assumed:

- A listing is ALWAYS created as draft: the authenticated role
  has no INSERT grant on status, so status is never sent on
  create and the database default applies.
- Inventory counters (reserved, sold, available) are never sent:
  the role has SELECT-only on them. available_quantity in
  responses is COMPUTED as total - reserved - sold, because the
  database never maintains the stored column (no trigger, no
  generated column, and create_order_reservation only increments
  reserved_quantity). Reservation and order logic stays in the
  database functions — this router never recreates it, and never
  writes inventory_events or inventory_reservations.
- published_at is SELECT-only, so activation cannot stamp it;
  it stays NULL until a future migration adds a trigger/RPC.
- Status transitions are updates, not deletes: there is no
  DELETE policy on listings, and cancel means status='cancelled'.
- Images: listing_images has INSERT/SELECT only — no UPDATE or
  DELETE policy — so images can be registered and listed, but
  not edited or removed through this API. Removal is deferred
  pending a policy (see the proposed migration in architecture.md).
  Storage objects in listing-media require the path
  <listing_id>/<file> and a store-operator caller; the API
  validates that path shape and never accepts a URL.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_user_client
from app.errors import (
    ApiError,
    AuthorizationError,
    BadGatewayError,
    NotFoundError,
)
from app.rbac import can_manage_store_for_listings, get_merchant_roles
from app.schemas import (
    AuthenticatedUser,
    CategoryResponse,
    InventoryAvailabilityResponse,
    ListingCreate,
    ListingImageCreate,
    ListingImageResponse,
    ListingResponse,
    ListingStatus,
    ListingUpdate,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["listings"])

# Allowed status transitions through this API. sold_out and
# expired are system-set statuses in the enum: no database code
# in this milestone moves a listing into them, and this API does
# not invent a way to set them.
_TRANSITIONS: dict[ListingStatus, set[ListingStatus]] = {
    ListingStatus.draft: {ListingStatus.active, ListingStatus.cancelled},
    ListingStatus.scheduled: {ListingStatus.active, ListingStatus.cancelled},
    ListingStatus.active: {ListingStatus.paused, ListingStatus.cancelled},
    ListingStatus.paused: {ListingStatus.active, ListingStatus.cancelled},
    ListingStatus.sold_out: {ListingStatus.cancelled},
    ListingStatus.expired: {ListingStatus.cancelled},
    ListingStatus.cancelled: set(),
}

# Columns the authenticated role may UPDATE on listings, and
# therefore the only columns this router ever sends on update.
_UPDATEABLE_COLUMNS = {
    "category_id",
    "title",
    "description",
    "contents_description",
    "reference_value",
    "selling_price",
    "total_quantity",
    "sale_starts_at",
    "sale_ends_at",
    "pickup_starts_at",
    "pickup_ends_at",
    "prepared_at",
    "best_before_at",
    "allergen_codes",
    "dietary_classification",
    "storage_instructions",
    "food_safety_notes",
}


def _listing_from_row(row: dict) -> ListingResponse:
    total = row.get("total_quantity", 0)
    reserved = row.get("reserved_quantity", 0) or 0
    sold = row.get("sold_quantity", 0) or 0
    data = dict(row)
    # Computed available, not the stored column (see module docstring).
    data["available_quantity"] = total - reserved - sold
    return ListingResponse(**data)


async def _require_listing_manager(
    user: AuthenticatedUser, client: SupabaseRestClient, store_id: UUID
) -> UUID:
    allowed, merchant_id = await can_manage_store_for_listings(user, client, store_id)
    if merchant_id is None:
        raise NotFoundError("Store not found")
    if not allowed:
        raise AuthorizationError(
            "Merchant owner, admin, store manager or inventory manager required"
        )
    return merchant_id


async def _load_listing(
    user: AuthenticatedUser, client: SupabaseRestClient, listing_id: UUID
) -> dict:
    try:
        rows = await client.query("listings", filters={"id": f"eq.{listing_id}"})
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Listing not found")
    return rows[0]


async def _require_listing_access(
    user: AuthenticatedUser, client: SupabaseRestClient, listing: dict
) -> dict:
    """Any active merchant member may read a store's listings
    (matching the RLS select rule can_manage_store(NULL)); writes
    use the stricter _require_listing_manager."""
    store_id = UUID(listing["store_id"])
    stores = await client.query(
        "stores", select="merchant_id", filters={"id": f"eq.{store_id}"}
    )
    if not stores:
        raise NotFoundError("Listing not found")
    roles = await get_merchant_roles(user, client, UUID(stores[0]["merchant_id"]))
    if not roles:
        raise AuthorizationError("Merchant membership required")
    return listing


def _to_db_value(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[attr-defined]
    if hasattr(value, "value"):
        return value.value  # type: ignore[attr-defined]
    return value


def _listing_insert_row(
    user: AuthenticatedUser, store_id: UUID, payload: ListingCreate
) -> dict:
    # Deliberately NO status, published_at, or inventory counters:
    # no INSERT grant on any of them (see module docstring).
    row: dict[str, object] = {
        "store_id": str(store_id),
        "listing_type": payload.listing_type.value,
        "category_id": str(payload.category_id) if payload.category_id else None,
        "template_id": str(payload.template_id) if payload.template_id else None,
        "title": payload.title,
        "description": payload.description,
        "contents_description": payload.contents_description,
        "reference_value": str(payload.reference_value),
        "selling_price": str(payload.selling_price),
        "currency": "INR",
        "total_quantity": payload.total_quantity,
        "sale_ends_at": payload.sale_ends_at.isoformat(),
        "pickup_starts_at": payload.pickup_starts_at.isoformat(),
        "pickup_ends_at": payload.pickup_ends_at.isoformat(),
        "prepared_at": payload.prepared_at.isoformat() if payload.prepared_at else None,
        "best_before_at": payload.best_before_at.isoformat()
        if payload.best_before_at
        else None,
        "allergen_codes": payload.allergen_codes,
        "dietary_classification": payload.dietary_classification.value,
        "storage_instructions": payload.storage_instructions,
        "food_safety_notes": payload.food_safety_notes,
        "created_by": str(user.id),
    }
    if payload.sale_starts_at is not None:
        row["sale_starts_at"] = payload.sale_starts_at.isoformat()
    return row


@router.get("/v1/categories", response_model=list[CategoryResponse])
async def list_active_categories(
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> list[CategoryResponse]:
    """Active categories only, matching the categories_select_active
    RLS policy (is_active). Inactive categories are never offered
    for new listings."""
    try:
        rows = await client.query("categories", filters={"is_active": "eq.true"})
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return [
        CategoryResponse(**row) for row in rows if row.get("is_active") is not False
    ]


@router.post(
    "/v1/stores/{store_id}/listings", response_model=ListingResponse, status_code=201
)
async def create_listing(
    store_id: UUID,
    payload: ListingCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    await _require_listing_manager(user, client, store_id)
    # Category, when given, must be an active category: the FK
    # alone would accept an inactive one.
    if payload.category_id is not None:
        try:
            cats = await client.query(
                "categories",
                filters={"id": f"eq.{payload.category_id}", "is_active": "eq.true"},
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        if not cats:
            raise NotFoundError("Category not found or not active")
    # Template, when given, must belong to this store.
    if payload.template_id is not None:
        try:
            templates = await client.query(
                "listing_templates",
                filters={
                    "id": f"eq.{payload.template_id}",
                    "store_id": f"eq.{store_id}",
                },
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        if not templates:
            raise NotFoundError("Template not found for this store")
    try:
        rows = await client.insert(
            "listings", _listing_insert_row(user, store_id, payload)
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise BadGatewayError("Listing creation returned no row")
    return _listing_from_row(rows[0])


@router.get("/v1/stores/{store_id}/listings", response_model=list[ListingResponse])
async def list_store_listings(
    store_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> list[ListingResponse]:
    allowed, merchant_id = await can_manage_store_for_listings(user, client, store_id)
    if merchant_id is None:
        raise NotFoundError("Store not found")
    # Read access is any merchant member, not just managers.
    roles = await get_merchant_roles(user, client, merchant_id)
    if not roles:
        raise AuthorizationError("Merchant membership required")
    try:
        rows = await client.query("listings", filters={"store_id": f"eq.{store_id}"})
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return [_listing_from_row(row) for row in rows]


@router.get("/v1/listings/{listing_id}", response_model=ListingResponse)
async def get_listing(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    listing = await _load_listing(user, client, listing_id)
    await _require_listing_access(user, client, listing)
    return _listing_from_row(listing)


@router.patch("/v1/listings/{listing_id}", response_model=ListingResponse)
async def update_listing(
    listing_id: UUID,
    payload: ListingUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    listing = await _load_listing(user, client, listing_id)
    await _require_listing_manager(user, client, UUID(listing["store_id"]))
    current_status = ListingStatus(listing["status"])
    if current_status in (ListingStatus.cancelled, ListingStatus.expired):
        raise AuthorizationError(
            f"Listing in status {current_status.value} cannot be edited"
        )
    # Merge payload over current values, then validate the whole
    # result: a partial update must not create an invalid window
    # or price combination.
    merged = dict(listing)
    updates = payload.model_dump(exclude_unset=True, mode="json")
    for key, value in updates.items():
        if key in _UPDATEABLE_COLUMNS:
            merged[key] = value
    # Full-window validation on the merged result. Values here
    # are ISO strings (database rows and mode="json" payload), so
    # parse them to datetimes first — string comparison would be
    # format-sensitive and could pass or fail wrongly.
    from datetime import datetime as _dt

    from app.schemas import _validate_listing_windows

    def _parse(value: object) -> _dt | None:
        if value is None:
            return None
        if isinstance(value, _dt):
            return value
        return _dt.fromisoformat(str(value).replace("Z", "+00:00"))

    try:
        _validate_listing_windows(
            _parse(merged.get("sale_starts_at")),
            _parse(merged["sale_ends_at"]),  # type: ignore[arg-type]
            _parse(merged["pickup_starts_at"]),  # type: ignore[arg-type]
            _parse(merged["pickup_ends_at"]),  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    prepared = _parse(merged.get("prepared_at"))
    best_before = _parse(merged.get("best_before_at"))
    if prepared is not None and best_before is not None and not best_before >= prepared:
        raise ApiError(
            422, "VALIDATION_ERROR", "best_before_at must not be before prepared_at"
        )
    new_total = merged.get("total_quantity")
    reserved = listing.get("reserved_quantity", 0) or 0
    sold = listing.get("sold_quantity", 0) or 0
    if new_total is not None and new_total < reserved + sold:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "total_quantity cannot be below already reserved or sold quantities",
        )
    if payload.category_id is not None:
        try:
            cats = await client.query(
                "categories",
                filters={"id": f"eq.{payload.category_id}", "is_active": "eq.true"},
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        if not cats:
            raise NotFoundError("Category not found or not active")
    db_updates = {
        key: value for key, value in updates.items() if key in _UPDATEABLE_COLUMNS
    }
    if not db_updates:
        return _listing_from_row(listing)
    try:
        rows = await client.update("listings", db_updates, {"id": f"eq.{listing_id}"})
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise BadGatewayError("Listing update returned no row")
    return _listing_from_row(rows[0])


async def _transition_listing(
    listing_id: UUID,
    target: ListingStatus,
    user: AuthenticatedUser,
    client: SupabaseRestClient,
) -> ListingResponse:
    listing = await _load_listing(user, client, listing_id)
    await _require_listing_manager(user, client, UUID(listing["store_id"]))
    current = ListingStatus(listing["status"])
    if target not in _TRANSITIONS.get(current, set()):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Listing cannot move from {current.value} to {target.value}",
        )
    if target is ListingStatus.active:
        # The database UPDATE policy also requires available > 0
        # and a public store; check the computed figure first so
        # the caller gets a clear 422 instead of a raw upstream
        # rejection. Note: the stored available_quantity column is
        # unmaintained, so activation through the DB policy will
        # still fail until the proposed migration lands — see
        # architecture.md. That failure surfaces as a 403/422
        # upstream error, not a silent success.
        total = listing.get("total_quantity", 0)
        reserved = listing.get("reserved_quantity", 0) or 0
        sold = listing.get("sold_quantity", 0) or 0
        if total - reserved - sold <= 0:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "Listing cannot be activated with no available quantity",
            )
    try:
        rows = await client.update(
            "listings", {"status": target.value}, {"id": f"eq.{listing_id}"}
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise BadGatewayError("Listing transition returned no row")
    return _listing_from_row(rows[0])


@router.post("/v1/listings/{listing_id}/publish", response_model=ListingResponse)
async def publish_listing(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    return await _transition_listing(listing_id, ListingStatus.active, user, client)


@router.post("/v1/listings/{listing_id}/pause", response_model=ListingResponse)
async def pause_listing(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    return await _transition_listing(listing_id, ListingStatus.paused, user, client)


@router.post("/v1/listings/{listing_id}/resume", response_model=ListingResponse)
async def resume_listing(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    return await _transition_listing(listing_id, ListingStatus.active, user, client)


@router.post("/v1/listings/{listing_id}/cancel", response_model=ListingResponse)
async def cancel_listing(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingResponse:
    return await _transition_listing(listing_id, ListingStatus.cancelled, user, client)


@router.get(
    "/v1/listings/{listing_id}/inventory", response_model=InventoryAvailabilityResponse
)
async def get_inventory_availability(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> InventoryAvailabilityResponse:
    """Read-only inventory view. Counts come from the listing row;
    available is computed (total - reserved - sold). Active
    reservations are read through the reservation function
    authority only in a later milestone — this endpoint never
    creates, edits, or releases reservations, and never writes
    inventory_events."""
    listing = await _load_listing(user, client, listing_id)
    await _require_listing_access(user, client, listing)
    total = listing.get("total_quantity", 0)
    reserved = listing.get("reserved_quantity", 0) or 0
    sold = listing.get("sold_quantity", 0) or 0
    return InventoryAvailabilityResponse(
        listing_id=listing["id"],
        store_id=listing["store_id"],
        status=ListingStatus(listing["status"]),
        total_quantity=total,
        reserved_quantity=reserved,
        sold_quantity=sold,
        available_quantity=total - reserved - sold,
        sale_ends_at=listing["sale_ends_at"],
        pickup_ends_at=listing["pickup_ends_at"],
    )


@router.get(
    "/v1/listings/{listing_id}/images", response_model=list[ListingImageResponse]
)
async def list_listing_images(
    listing_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> list[ListingImageResponse]:
    listing = await _load_listing(user, client, listing_id)
    await _require_listing_access(user, client, listing)
    try:
        rows = await client.query(
            "listing_images", filters={"listing_id": f"eq.{listing_id}"}
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    rows.sort(key=lambda r: (r.get("display_order", 0), r.get("created_at", "")))
    return [ListingImageResponse(**row) for row in rows]


@router.post(
    "/v1/listings/{listing_id}/images",
    response_model=ListingImageResponse,
    status_code=201,
)
async def add_listing_image(
    listing_id: UUID,
    payload: ListingImageCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> ListingImageResponse:
    listing = await _load_listing(user, client, listing_id)
    await _require_listing_manager(user, client, UUID(listing["store_id"]))
    # The bucket policy requires the first path segment to be the
    # listing id. A path for another listing, or any other shape,
    # is rejected here before it reaches the database, and the API
    # never accepts a URL — only a listing-media storage path.
    first = payload.storage_path.split("/")[0]
    if first != str(listing_id) or len(payload.storage_path.split("/")) < 2:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "storage_path must start with this listing id",
        )
    try:
        rows = await client.insert(
            "listing_images",
            {
                "listing_id": str(listing_id),
                "storage_path": payload.storage_path,
                "alt_text": payload.alt_text,
                "display_order": payload.display_order,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise BadGatewayError("Image registration returned no row")
    return ListingImageResponse(**rows[0])
