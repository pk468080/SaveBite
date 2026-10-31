"""Authenticated identity proof (Milestone 2 only).

GET /v1/me returns the authenticated user's id/email and their
platform roles. It exists to prove the auth + RBAC boundaries end to
end in tests. It is not a profile endpoint and must not be expanded
into profile editing without a later milestone.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_user_client
from app.rbac import get_platform_roles
from app.schemas import AuthenticatedUser, MeResponse
from app.supabase_client import SupabaseRestClient

router = APIRouter()


@router.get("/v1/me", response_model=MeResponse, tags=["auth"])
async def me(
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MeResponse:
    roles = await get_platform_roles(user, client)
    return MeResponse(id=user.id, email=user.email, platform_roles=roles)
