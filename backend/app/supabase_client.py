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


class RPCNotAllowedError(ValueError):
    """Raised when a client tries to call an RPC it is not allowed to
    call. This is a programmer error, not a user error: it must be
    caught in development and tests, never silently downgraded to a
    different client type."""


# Explicit allowlists, mirroring the Milestone 1 database contract.
# Anything not listed here is rejected by both client types.
USER_CONTEXT_RPCS = frozenset(
    {
        "apply_merchant_application",
        "create_merchant_store",
        "upsert_store_hours",
        "create_order_reservation",
        "begin_payment_checkout",
        "issue_pickup_token",
        "verify_pickup_token",
        "request_refund",
    }
)

BACKEND_RPCS = frozenset(
    {
        "backend_attach_gateway_order",
        "backend_mark_payment_failed",
        "backend_confirm_payment_capture",
        "backend_record_payment_webhook_event",
        "backend_release_expired_reservations",
        "backend_review_merchant",
        "backend_review_store",
        "backend_update_refund_status",
        "backend_post_ledger_transaction",
        "backend_reverse_ledger_transaction",
    }
)


class SupabaseRestClient:
    def __init__(
        self,
        settings: Settings,
        *,
        token: str | None = None,
        service_role: bool = False,
        anonymous: bool = False,
    ) -> None:
        self._settings = settings
        self._token = token
        self._service_role = service_role
        # Anonymous, read-only client (Milestone 5, customer
        # discovery). It uses the publishable key as the anon
        # credential, exactly as Supabase's anon role does, and it
        # can NEVER write or call an RPC — insert/update/rpc raise
        # before any HTTP call. It must never be given a
        # service-role key, and it never carries a user identity.
        self._anonymous = anonymous

    def _headers(self) -> dict[str, str]:
        if self._service_role:
            key = self._settings.supabase_service_role_key
            if key is None:
                raise ServiceUnavailableError("Service-role key is not configured")
            secret = key.get_secret_value()
            return {"apikey": secret, "Authorization": f"Bearer {secret}"}
        if self._anonymous:
            publishable = self._settings.supabase_publishable_key
            if not publishable:
                raise ServiceUnavailableError(
                    "Supabase publishable key is not configured"
                )
            return {"apikey": publishable, "Authorization": f"Bearer {publishable}"}
        return {
            "apikey": self._settings.supabase_publishable_key,
            "Authorization": f"Bearer {self._token or ''}",
        }

    def _rest_url(self, path: str) -> str:
        return f"{self._settings.supabase_url}/rest/v1/{path}"

    def validate_rpc(self, name: str) -> None:
        """Enforce the RPC allowlists before any HTTP call is made.
        Service-role clients may ONLY call backend_* RPCs. User-context
        clients may ONLY call user-context RPCs. Unknown RPC names are
        rejected by both, so a typo cannot silently become a privilege
        escalation."""
        if self._service_role:
            if name not in BACKEND_RPCS:
                raise RPCNotAllowedError(
                    f"Service-role client may only call backend_* RPCs, not {name!r}"
                )
        else:
            if name in BACKEND_RPCS or name.startswith("backend_"):
                raise RPCNotAllowedError(
                    f"User-context client may not call server-only RPC {name!r}"
                )
            if name not in USER_CONTEXT_RPCS:
                raise RPCNotAllowedError(
                    f"User-context client may only call approved user RPCs, not {name!r}"
                )

    def _require_not_anonymous(self, operation: str) -> None:
        if self._anonymous:
            raise RPCNotAllowedError(
                f"Anonymous client is read-only and may not {operation}"
            )

    async def query(
        self,
        table: str,
        *,
        select: str = "*",
        filters: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Query a public table through PostgREST with a user-context
        client only. Service-role clients must NOT query tables
        directly — they may only call approved backend_* RPCs, so that
        every privileged operation goes through a reviewed function
        with its own authorisation checks. Private tables are
        rejected outright — use a backend_* RPC instead."""
        if self._service_role:
            raise RPCNotAllowedError(
                "Service-role client may not query tables directly; "
                "use an approved backend_* RPC instead"
            )
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

    async def insert(self, table: str, row: dict[str, Any]) -> list[dict[str, Any]]:
        """Insert one row through PostgREST with a user-context
        client only. Service-role clients must NOT write tables
        directly — see query(). RLS policies and column grants are
        the enforcement point: a column the caller has no INSERT
        grant on (for listings: id, status, published_at,
        available_quantity, reserved_quantity, sold_quantity) must
        never appear in `row`, or PostgREST rejects the whole
        insert. Returns the inserted rows (Prefer:
        return=representation)."""
        self._require_not_anonymous("insert rows")
        if self._service_role:
            raise RPCNotAllowedError(
                "Service-role client may not write tables directly; "
                "use an approved backend_* RPC instead"
            )
        if table.startswith("private."):
            raise ValueError("Private schema tables must not be written via PostgREST")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                self._rest_url(table),
                headers={**self._headers(), "Prefer": "return=representation"},
                json=row,
            )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    async def update(
        self, table: str, row: dict[str, Any], filters: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Update rows through PostgREST with a user-context client
        only. Same service-role and private-schema guards as
        insert(). `row` must contain only columns the caller has an
        UPDATE grant on — for listings that excludes store_id,
        listing_type, template_id, currency, created_by, and all
        inventory counters."""
        self._require_not_anonymous("update rows")
        if self._service_role:
            raise RPCNotAllowedError(
                "Service-role client may not write tables directly; "
                "use an approved backend_* RPC instead"
            )
        if table.startswith("private."):
            raise ValueError("Private schema tables must not be written via PostgREST")
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                self._rest_url(table),
                headers={**self._headers(), "Prefer": "return=representation"},
                params=filters,
                json=row,
            )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    async def rpc(self, name: str, params: dict[str, Any]) -> Any:
        """Call a public RPC function, after validate_rpc() enforces
        which client type may call it. For user-context RPCs the
        caller must pass a user-context client; for backend_* RPCs
        the caller must pass a service-role client after its own
        authentication, authorisation, validation and (for payments)
        gateway-verification checks."""
        self._require_not_anonymous("call RPCs")
        self.validate_rpc(name)
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


def anon_client(settings: Settings) -> SupabaseRestClient:
    """Build the anonymous, read-only client for customer
    discovery. It authenticates as Supabase's anon role with the
    publishable key only — never a service-role key, never a user
    token — and its insert/update/rpc methods raise before any
    HTTP call. RLS public policies are the enforcement point for
    what it can read; the API additionally filters to eligible
    listings and projects only public fields."""
    return SupabaseRestClient(settings, anonymous=True)


def service_client(settings: Settings) -> SupabaseRestClient:
    """Build a service-role client. Fails closed if the key is missing.
    Callers must be server-only code that has already authenticated
    and authorised the request; this function does not do that."""
    if not settings.service_role_configured:
        raise ServiceUnavailableError("Service-role key is not configured")
    return SupabaseRestClient(settings, service_role=True)
