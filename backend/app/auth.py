"""JWT authentication and user identity resolution.

Identity is resolved by calling Supabase Auth with the caller's Bearer
token. The JWT is NOT decoded locally, and no header or request field
(X-User-Id, X-Role, a body-supplied user id) is ever trusted as
identity. A missing token is a 401; an Auth 401/403 is a 401; a
missing Supabase configuration is a 503 — never a fallback anonymous
identity.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.errors import AuthenticationError, BadGatewayError, ServiceUnavailableError
from app.schemas import AuthenticatedUser


async def fetch_supabase_user(token: str, settings: Settings) -> AuthenticatedUser:
    """Call Supabase Auth /auth/v1/user and return the identity it
    confirms. This function is the single place Auth is contacted, so
    tests can replace it without touching the rest of the app."""
    if not settings.supabase_configured:
        raise ServiceUnavailableError("Supabase is not configured")
    url = f"{settings.supabase_url}/auth/v1/user"
    headers = {
        "apikey": settings.supabase_publishable_key,
        "Authorization": f"Bearer {token}",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise BadGatewayError("Supabase Auth is unreachable") from exc
    if response.status_code in (401, 403):
        raise AuthenticationError("Invalid or expired token")
    if response.status_code != 200:
        raise BadGatewayError("Supabase Auth returned an unexpected status")
    data = response.json()
    user_id = data.get("id")
    if not user_id:
        raise AuthenticationError("Supabase Auth did not return a user id")
    return AuthenticatedUser(id=user_id, email=data.get("email"), token=token)
