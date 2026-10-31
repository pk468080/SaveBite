"""Merchant onboarding and store management (Milestone 3).

All operations use the user-context Supabase client and the
user-context RPCs from the Milestone 1 contract. The service-role
client is never used here: RLS and the RPCs' own authorisation are
the authoritative boundary, and this router only adds an API-level
membership check so a caller cannot even reach an RPC they are not
a member for.

No user id, owner id, role, approval status, or reviewer id is
accepted from the request body — identity comes only from the
Supabase Auth dependency, and roles come only from the membership
tables.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_user_client
from app.errors import AuthorizationError, BadGatewayError, NotFoundError
from app.rbac import get_merchant_roles
from app.schemas import (
    AuthenticatedUser,
    MerchantApplicationCreate,
    MerchantMemberRole,
    MerchantResponse,
    StoreCreate,
    StoreResponse,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(prefix="/v1/merchants", tags=["merchants"])


async def _require_merchant_roles(
    user: AuthenticatedUser,
    client: SupabaseRestClient,
    merchant_id: UUID,
) -> list[MerchantMemberRole]:
    roles = await get_merchant_roles(user, client, merchant_id)
    if not roles:
        raise AuthorizationError("Merchant membership required")
    return roles


def _merchant_from_row(row: dict) -> MerchantResponse:
    return MerchantResponse(**row)


def _store_from_row(row: dict) -> StoreResponse:
    return StoreResponse(**row)


@router.post(
    "/applications",
    response_model=MerchantResponse,
    status_code=201,
)
async def submit_merchant_application(
    payload: MerchantApplicationCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MerchantResponse:
    """Submit a merchant application. The RPC creates the merchant
    and an owner membership for the authenticated user, and returns
    the merchant UUID; the created row is then read back so the
    response contains the stored values, not invented ones."""
    try:
        result = await client.rpc(
            "apply_merchant_application",
            {
                "p_legal_name": payload.legal_name,
                "p_display_name": payload.display_name,
                "p_business_type": payload.business_type.value,
                "p_business_email": payload.business_email,
                "p_business_phone": payload.business_phone,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    merchant_id = (
        result
        if isinstance(result, str)
        else (result.get("id") if isinstance(result, dict) else None)
    )
    if not merchant_id:
        raise BadGatewayError("Merchant application returned no id")
    try:
        rows = await client.query(
            "merchants",
            filters={"id": f"eq.{merchant_id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Merchant not found after application")
    return _merchant_from_row(rows[0])


@router.get("", response_model=list[MerchantResponse])
async def list_my_merchants(
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> list[MerchantResponse]:
    """List only merchants the authenticated user is an active
    member of. Memberships are read first; merchants are then read
    by id, so another user's merchants can never appear here."""
    try:
        memberships = await client.query(
            "merchant_memberships",
            select="merchant_id,role,is_active",
            filters={"user_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    merchant_ids = [
        row["merchant_id"] for row in memberships if row.get("is_active") is not False
    ]
    if not merchant_ids:
        return []
    try:
        rows = await client.query(
            "merchants",
            filters={"id": f"in.({','.join(merchant_ids)})"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return [_merchant_from_row(row) for row in rows]


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MerchantResponse:
    await _require_merchant_roles(user, client, merchant_id)
    try:
        rows = await client.query(
            "merchants",
            filters={"id": f"eq.{merchant_id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Merchant not found")
    return _merchant_from_row(rows[0])


@router.post(
    "/{merchant_id}/stores",
    response_model=StoreResponse,
    status_code=201,
)
async def create_store(
    merchant_id: UUID,
    payload: StoreCreate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> StoreResponse:
    """Create a store. Requires merchant owner or admin — the same
    rule the RPC enforces, checked here first so a non-owner gets a
    clean 403 instead of a raw upstream error."""
    roles = await _require_merchant_roles(user, client, merchant_id)
    if MerchantMemberRole.owner not in roles and (
        MerchantMemberRole.admin not in roles
    ):
        raise AuthorizationError("Merchant owner or admin required")
    try:
        result = await client.rpc(
            "create_merchant_store",
            {
                "p_merchant_id": str(merchant_id),
                "p_name": payload.name,
                "p_slug": payload.slug,
                "p_address_line_1": payload.address_line_1,
                "p_address_line_2": payload.address_line_2,
                "p_locality": payload.locality,
                "p_city": payload.city,
                "p_state": payload.state,
                "p_pincode": payload.pincode,
                "p_latitude": payload.latitude,
                "p_longitude": payload.longitude,
                "p_contact_phone": payload.contact_phone,
                "p_pickup_instructions": payload.pickup_instructions,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    store_id = (
        result
        if isinstance(result, str)
        else (result.get("id") if isinstance(result, dict) else None)
    )
    if not store_id:
        raise BadGatewayError("Store creation returned no id")
    try:
        rows = await client.query(
            "stores",
            filters={"id": f"eq.{store_id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Store not found after creation")
    return _store_from_row(rows[0])


@router.get("/{merchant_id}/stores", response_model=list[StoreResponse])
async def list_merchant_stores(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> list[StoreResponse]:
    await _require_merchant_roles(user, client, merchant_id)
    try:
        rows = await client.query(
            "stores",
            filters={"merchant_id": f"eq.{merchant_id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return [_store_from_row(row) for row in rows]
