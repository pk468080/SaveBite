"""Role-based access control.

Roles are never accepted from the request. They are read from the
database through the user-context client, so RLS still applies:
- platform roles: public.platform_user_roles, revoked_at IS NULL
- merchant roles: public.merchant_memberships, is_active = true
- store roles: public.store_staff_memberships, is_active = true

Reviewer identity rule: backend_review_* and backend_update_refund_*
RPCs take a reviewer/actor id. That id must ALWAYS be the
authenticated user's id. Use reviewer_id_for(user) and never forward
a client-supplied reviewer id — strip_caller_supplied_reviewer()
removes p_reviewer_id / p_actor_user_id from caller payloads before
the server injects its own.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from app.dependencies import get_current_user, get_user_client
from app.errors import AuthorizationError
from app.schemas import AuthenticatedUser, MerchantMemberRole, PlatformRole
from app.supabase_client import SupabaseRestClient


async def get_platform_roles(
    user: AuthenticatedUser, client: SupabaseRestClient
) -> list[PlatformRole]:
    rows = await client.query(
        "platform_user_roles",
        select="role,revoked_at",
        filters={"user_id": f"eq.{user.id}", "revoked_at": "is.null"},
    )
    roles: list[PlatformRole] = []
    for row in rows:
        # Defence in depth: the PostgREST filter above asks for
        # revoked_at IS NULL, but a revoked record must never grant a
        # role even if the filter is bypassed, mis-typed, or faked in
        # a test double. Filter again here.
        if row.get("revoked_at") is not None:
            continue
        try:
            roles.append(PlatformRole(row["role"]))
        except (KeyError, ValueError):
            continue
    return roles


async def get_merchant_roles(
    user: AuthenticatedUser, client: SupabaseRestClient, merchant_id: UUID
) -> list[MerchantMemberRole]:
    rows = await client.query(
        "merchant_memberships",
        # is_active must be selected, not just filtered on: the
        # Python-side inactive check below reads row["is_active"],
        # and a PostgREST response only contains selected columns.
        # Requesting "role" alone would make that check see None
        # for every row and never filter anything.
        select="role,is_active",
        filters={
            "merchant_id": f"eq.{merchant_id}",
            "user_id": f"eq.{user.id}",
            "is_active": "eq.true",
        },
    )
    roles: list[MerchantMemberRole] = []
    for row in rows:
        # Defence in depth: inactive memberships grant nothing, even
        # if the PostgREST is_active filter is bypassed.
        if row.get("is_active") is False:
            continue
        try:
            roles.append(MerchantMemberRole(row["role"]))
        except (KeyError, ValueError):
            continue
    return roles


async def get_store_roles(
    user: AuthenticatedUser, client: SupabaseRestClient, store_id: UUID
) -> list[MerchantMemberRole]:
    rows = await client.query(
        "store_staff_memberships",
        # Same as get_merchant_roles: is_active must be selected
        # for the Python-side inactive check to see it.
        select="role,is_active",
        filters={
            "store_id": f"eq.{store_id}",
            "user_id": f"eq.{user.id}",
            "is_active": "eq.true",
        },
    )
    roles: list[MerchantMemberRole] = []
    for row in rows:
        if row.get("is_active") is False:
            continue
        try:
            roles.append(MerchantMemberRole(row["role"]))
        except (KeyError, ValueError):
            continue
    return roles


def require_platform_role(*roles: PlatformRole):  # type: ignore[no-untyped-def]
    async def checker(
        user: AuthenticatedUser = Depends(get_current_user),
        client: SupabaseRestClient = Depends(get_user_client),
    ) -> AuthenticatedUser:
        granted = await get_platform_roles(user, client)
        if not any(role in granted for role in roles):
            raise AuthorizationError("Platform role required")
        return user

    return checker


def require_merchant_role(*roles: MerchantMemberRole):  # type: ignore[no-untyped-def]
    async def checker(
        merchant_id: UUID,
        user: AuthenticatedUser = Depends(get_current_user),
        client: SupabaseRestClient = Depends(get_user_client),
    ) -> AuthenticatedUser:
        granted = await get_merchant_roles(user, client, merchant_id)
        if not any(role in granted for role in roles):
            raise AuthorizationError("Merchant role required")
        return user

    return checker


def require_store_role(*roles: MerchantMemberRole):  # type: ignore[no-untyped-def]
    async def checker(
        store_id: UUID,
        user: AuthenticatedUser = Depends(get_current_user),
        client: SupabaseRestClient = Depends(get_user_client),
    ) -> AuthenticatedUser:
        granted = await get_store_roles(user, client, store_id)
        if not any(role in granted for role in roles):
            raise AuthorizationError("Store role required")
        return user

    return checker


async def can_manage_store_hours(
    user: AuthenticatedUser,
    client: SupabaseRestClient,
    store_id: UUID,
) -> tuple[bool, UUID | None]:
    """Mirror private.can_manage_store(store_id, ['store_manager'])
    exactly, without blocking merchant owners/admins.

    Returns (allowed, merchant_id). Owners/admins of the store's
    merchant are always allowed, even with no store-staff row.
    A store_manager is allowed only when they also hold an active
    merchant membership — the DB's can_manage_store joins
    merchant_memberships first, so a staff row alone is not enough.
    Any other role, or no merchant membership at all, is denied.
    merchant_id is None when the store is not visible to the caller
    (RLS returns no row), which the caller turns into 404."""
    stores = await client.query(
        "stores",
        select="merchant_id",
        filters={"id": f"eq.{store_id}"},
    )
    if not stores:
        return False, None
    merchant_id = UUID(stores[0]["merchant_id"])
    merchant_roles = await get_merchant_roles(user, client, merchant_id)
    if MerchantMemberRole.owner in merchant_roles or (
        MerchantMemberRole.admin in merchant_roles
    ):
        return True, merchant_id
    if not merchant_roles:
        return False, merchant_id
    store_roles = await get_store_roles(user, client, store_id)
    if MerchantMemberRole.store_manager in store_roles:
        return True, merchant_id
    return False, merchant_id


def reviewer_id_for(user: AuthenticatedUser) -> str:
    """The only reviewer/actor id a handler may pass to a backend_* RPC."""
    return str(user.id)


def strip_caller_supplied_reviewer(payload: dict) -> dict:
    """Remove any reviewer/actor id a caller tried to supply, so a
    handler cannot accidentally forward it to a backend RPC."""
    cleaned = dict(payload)
    cleaned.pop("p_reviewer_id", None)
    cleaned.pop("p_actor_user_id", None)
    cleaned.pop("reviewer_id", None)
    cleaned.pop("actor_user_id", None)
    return cleaned
