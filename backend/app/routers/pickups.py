"""Secure pickup verification (Milestone 8).

The database is the authority for every collection. Both
endpoints use the caller's user-context client and the
approved RPCs only; no service-role client, no private
table access, no client-side status change.

Verified database contract (from the baseline):
- pickup_tokens: id, order_id, token_hash (SHA256 hex,
  never plaintext), expires_at, used_at, invalidated_at,
  failed_attempts (present in schema but NOT incremented
  by the current verify function — there is no lockout
  after failed attempts, so the token's 64-hex-char
  randomness is the brute-force protection), created_at.
  token_hash is UNIQUE.
- issue_pickup_token(p_order_id): auth required; order
  must belong to the caller and be confirmed or
  ready_for_pickup (so unpaid, failed, pending, cancelled,
  expired, and already-collected orders are all rejected
  with pickup_not_available); issuance is refused after
  pickup_ends_at + 30 minutes; previous unused tokens for
  the order are invalidated; the new token is 32 random
  bytes hex-encoded (64 hex chars), stored only as its
  SHA256 hash, expiring at pickup_ends_at + 30 minutes;
  returns pickup_token_id, pickup_token (plaintext, once
  only), expires_at.
- verify_pickup_token(p_store_id, p_pickup_token): auth
  required; token must be at least 32 chars; caller must
  satisfy can_manage_store(store, [store_manager,
  pickup_operator]) — which, by that function's definition,
  ALSO passes merchant owner/admin members, but NOT
  finance_viewer or inventory_manager; the token row is
  locked FOR UPDATE and must be unused, uninvalidated,
  and unexpired; the order is locked FOR UPDATE and must
  belong to the store, be confirmed/ready_for_pickup, and
  have payment_status captured; the current time must be
  within pickup_starts_at - 15 minutes to pickup_ends_at
  + 30 minutes. Atomically it then marks the token used,
  sets the order collected with collected_at, writes an
  order_status_event (actor: the verifying user, type
  merchant, reason pickup_token_verified) and a
  pickup_events row. A second verification of the same
  token fails because used_at is set, and concurrent
  verifications are serialised by the FOR UPDATE locks —
  they cannot produce two collections. Returns order_id,
  order_number, status collected, collected_at.

QR payload format: "SB1:<64-hex-token>". SB1 is a
version prefix only. The payload contains nothing else:
no customer name, phone, email, payment data, order id,
or store id. The frontend renders this string as a QR
code; the backend strips the prefix (or accepts the raw
token) and validates the token through the RPC. A QR
payload alone never marks anything collected — only a
successful RPC verification does.

Failure privacy: verify failures are mapped to generic
messages. pickup_token_invalid_or_used covers invalid,
expired, and already-used tokens indistinguishably (the
RPC itself does not distinguish them), and
order_not_collectable covers unpaid, cancelled, expired,
and wrong-store orders indistinguishably. No failure
reveals whether another store has an order for a token.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_user_client
from app.errors import ApiError, NotFoundError
from app.schemas import (
    AuthenticatedUser,
    OrderItemPreview,
    OrderStatus,
    PickupTokenResponse,
    PickupVerifyRequest,
    PickupVerifyResponse,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["pickups"])

_QR_PREFIX = "SB1:"
_TOKEN_RE = re.compile(r"^[0-9a-f]{64}$")

_ORDER_SELECT = (
    "id,order_number,store_id,status,payment_status,pickup_starts_at,pickup_ends_at"
)
_STORE_SELECT = "id,name,pickup_instructions"


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _strip_qr_prefix(raw: str) -> str:
    token = raw.strip()
    if token.startswith(_QR_PREFIX):
        token = token[len(_QR_PREFIX) :]
    return token.strip().lower()


def _validate_token_format(token: str) -> str:
    """Issued tokens are 64 lowercase hex chars. Anything
    else cannot be a token from this database version, so
    it is rejected before any RPC call (which would also
    reject it, but with a less specific error)."""
    cleaned = _strip_qr_prefix(token)
    if not _TOKEN_RE.match(cleaned):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Pickup token format is invalid",
        )
    return cleaned


@router.post("/v1/orders/{order_id}/pickup-token", response_model=PickupTokenResponse)
async def issue_pickup_token(
    order_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> PickupTokenResponse:
    """Issue a one-time pickup token for the caller's own
    eligible order. Ownership and eligibility are the
    database's checks (issue_pickup_token); the order fetch
    here only supplies response fields and a clean 404 for
    orders that are not the caller's."""
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
    try:
        result = await client.rpc("issue_pickup_token", {"p_order_id": str(order_id)})
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not isinstance(result, dict) or not result.get("pickup_token"):
        from app.errors import BadGatewayError

        raise BadGatewayError("Pickup token could not be issued")
    try:
        store_rows = await client.query(
            "stores",
            select=_STORE_SELECT,
            filters={"id": f"eq.{order['store_id']}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    store = store_rows[0] if store_rows else {}
    token = str(result["pickup_token"])
    return PickupTokenResponse(
        order_id=order_id,
        order_number=order["order_number"],
        pickup_token=token,
        qr_payload=f"{_QR_PREFIX}{token}",
        expires_at=_parse_time(result["expires_at"]),  # type: ignore[arg-type]
        pickup_starts_at=_parse_time(order["pickup_starts_at"]),  # type: ignore[arg-type]
        pickup_ends_at=_parse_time(order["pickup_ends_at"]),  # type: ignore[arg-type]
        store_name=store.get("name", ""),
        pickup_instructions=store.get("pickup_instructions"),
    )


@router.post("/v1/merchant/pickups/verify", response_model=PickupVerifyResponse)
async def verify_pickup(
    payload: PickupVerifyRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> PickupVerifyResponse:
    """Verify a pickup token and collect the order. The
    store_id in the request is the store where the customer
    is standing; the database checks the caller's
    authorization for that store AND that the token's order
    belongs to it. No client-supplied identity, role, or
    status is trusted, and no status can be set directly —
    only a successful RPC verification collects the order."""
    token = _validate_token_format(payload.pickup_token)
    try:
        result = await client.rpc(
            "verify_pickup_token",
            {
                "p_store_id": str(payload.store_id),
                "p_pickup_token": token,
            },
        )
    except Exception as exc:
        translated = translate_upstream_error(exc)
        # Collapse the RPC's distinct P0001 reasons into
        # privacy-safe messages: do not reveal whether the
        # token was invalid, expired, used, or for another
        # store's order, beyond what the caller already
        # holds (a token they scanned at their own store).
        message = translated.message
        if message == "pickup_token_invalid_or_used":
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "Pickup token is invalid, expired, or already used",
            ) from exc
        if message == "order_not_collectable":
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "Order cannot be collected",
            ) from exc
        if message == "outside_pickup_window":
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                "Outside the pickup window",
            ) from exc
        raise translated from exc
    if not isinstance(result, dict) or not result.get("order_id"):
        from app.errors import BadGatewayError

        raise BadGatewayError("Pickup verification did not return an order")
    # Response enrichment only: the collection already
    # happened atomically in the RPC. If these reads fail,
    # the collection is NOT rolled back — return the RPC
    # fields with an empty item list instead.
    store_name = ""
    items: list[OrderItemPreview] = []
    try:
        store_rows = await client.query(
            "stores",
            select=_STORE_SELECT,
            filters={"id": f"eq.{payload.store_id}"},
        )
        if store_rows:
            store_name = store_rows[0].get("name", "")
        item_rows = await client.query(
            "order_items",
            select="listing_title_snapshot,quantity",
            filters={"order_id": f"eq.{result['order_id']}"},
        )
        items = [
            OrderItemPreview(
                title=row["listing_title_snapshot"], quantity=row["quantity"]
            )
            for row in item_rows
        ]
    except Exception:
        pass
    return PickupVerifyResponse(
        order_id=UUID(str(result["order_id"])),
        order_number=result["order_number"],
        store_name=store_name,
        status=OrderStatus(result["status"]),
        collected_at=_parse_time(result["collected_at"]),  # type: ignore[arg-type]
        items=items,
    )
