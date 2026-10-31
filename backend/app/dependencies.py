"""FastAPI dependencies: settings, authenticated user, Supabase clients."""

from __future__ import annotations

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import fetch_supabase_user
from app.config import Settings, get_settings
from app.errors import AuthenticationError
from app.schemas import AuthenticatedUser
from app.supabase_client import (
    SupabaseRestClient,
    anon_client,
    service_client,
    user_client,
)

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedUser:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token")
    return await fetch_supabase_user(credentials.credentials, settings)


def get_user_client(
    user: AuthenticatedUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> SupabaseRestClient:
    return user_client(settings, user.token)


def get_anon_client(
    settings: Settings = Depends(get_settings),
) -> SupabaseRestClient:
    """Anonymous discovery client. Deliberately NOT depending on
    get_current_user, so marketplace browsing works without a
    bearer token. Read-only by construction (see anon_client);
    it must never be used for a write, an RPC, or a
    merchant-only record."""
    return anon_client(settings)


def get_service_client(
    settings: Settings = Depends(get_settings),
) -> SupabaseRestClient:
    """Service-role client dependency. Use ONLY in server-only handlers
    that have already authenticated and authorised the request. Never
    expose this dependency on a route that forwards a user token, and
    never use it for a user-context RPC."""
    return service_client(settings)
