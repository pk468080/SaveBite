"""Supabase HTTP clients — user-context and service-role, kept apart.

All database access in Milestone 2 goes through Supabase's HTTP APIs
(Auth + PostgREST / RPC), so RLS and the Milestone 1 function contracts
remain the enforcement point. There is no direct PostgreSQL connection.

Boundaries enforced here:
- A user-context client forwards the caller's Bearer token unchanged
  and may only query the `public` schema. It is the ONLY client for
  user-context RPCs, where auth.uid() must identify the caller.
- A service-role client is built only from SUPABASE_SERVICE_ROLE_KEY,
  only for public `backend_*` RPC wrappers, and only after the calling
  handler has done authentication, authorisation, validation and (for
  payments) gateway verification. It bypasses RLS and carries no user
  identity, so it must never be used for a user-context RPC.
- The `private` schema is never queried through PostgREST from either
  client. Private data is reached only through `backend_*` RPCs.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.errors import ServiceUnavailableError

_PUBLIC_TABLES_ONLY = "public"


class SupabaseRestClient:
    def __init__(
        self,
        settings: Settings,
        *,
        token: str | None = None,
        service_role: bool = False,
    ) -> None:
        self._settings = settings
        self._token = token
        self._service_role = service_role

    def _headers(self) -> dict[str, str]:
        if self._service_role:
            key = self._settings.supabase_service_role_key
            if key is None:
                raise ServiceUnavailableError("Service-role key is not configured")
            secret = key.get_secret_value()
            return {"apikey": secret, "Authorization": f"Bearer {secret}"}
        return {
            "apikey": self._settings.supabase_publishable_key,
            "Authorization": f"Bearer {self._token or ''}",
        }

    def _rest_url(self, path: str) -> str:
        return f"{self._settings.supabase_url}/rest/v1/{path}"

    async def query(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query a public table through PostgREST. Private tables are
        rejected outright — use a backend_* RPC instead."""
        if table.startswith("private."):
            raise ValueError("Private schema tables must not be queried via PostgREST")
        params: dict[str, str] = {"select": select}
        if filters:
            params.update(filters)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                self._rest_url(table), headers=self._headers(), params=params
            )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    async def rpc(self, name: str, params: dict[str, Any]) -> Any:
        """Call a public RPC function. For user-context RPCs the caller
        must pass a user-context client; for backend_* RPCs the caller
        must pass a service-role client after its own checks. This
        method does not decide which — the handler does, and the
        distinction is documented at every call site in later
        milestones."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self._rest_url(f"rpc/{name}"),
                headers={**self._headers(), "Content-Type": "application/json"},
                json=params,
            )
        response.raise_for_status()
        return response.json()


def user_client(settings: Settings, token: str) -> SupabaseRestClient:
    """Build a user-context client. Token is forwarded unchanged."""
    return SupabaseRestClient(settings, token=token, service_role=False)


def service_client(settings: Settings) -> SupabaseRestClient:
    """Build a service-role client. Fails closed if the key is missing.
    Callers must be server-only code that has already authenticated
    and authorised the request; this function does not do that."""
    if not settings.service_role_configured:
        raise ServiceUnavailableError("Service-role key is not configured")
    return SupabaseRestClient(settings, service_role=True)
