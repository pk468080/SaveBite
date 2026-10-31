"""Razorpay payments (Milestone 6): checkout, verification, webhook.

Payment lifecycle, from the verified database contracts:
1. Reservation (Milestone 5) leaves the order pending_payment
   with live inventory reservations (~5 minute expiry).
2. Checkout (user-context RPC begin_payment_checkout) verifies
   ownership and eligibility, and creates or reuses a private
   payment_transactions row (gateway razorpay, amount and
   currency copied from the order, status created). Its
   idempotency key is unique across payment transactions: the
   same key for the same order reuses the transaction; the
   same key for another order is a conflict.
3. The backend creates a Razorpay order for exactly that
   amount (rupees -> paise, Decimal, never float) and attaches
   the Razorpay order id with the server-only RPC
   backend_attach_gateway_order (requires status created;
   re-attaching the SAME gateway order id is allowed, a
   different one is a conflict).
4. Confirmation happens ONLY after independent verification:
   checkout signature verified against the order id fetched
   from Razorpay's own API, provider payment fetched
   server-side and found captured, amount and currency from
   the provider — then backend_confirm_payment_capture, which
   itself re-checks amount equality and live reservations,
   routes mismatches to reconciliation_required, and is
   idempotent when already captured. p_signature_verified is
   set True only at that point, never merely because the
   frontend supplied a signature.
5. Webhooks are verified against the RAW body with the
   webhook secret before anything is recorded or acted on,
   recorded with backend_record_payment_webhook_event (unique
   on gateway + event id, so a redelivery creates no second
   row), and then acted on through the same confirm / mark-
   failed RPCs. A failed event never overwrites a capture:
   backend_mark_payment_failed itself refuses a captured
   payment, and the webhook handler treats that refusal as
   "already captured", not as an error to retry forever.

MISSING CAPABILITY, documented not worked around: there is
no approved RPC that maps a Razorpay gateway order id back
to a payment transaction id, and the service-role client may
not query tables (private tables are rejected outright).
So the gateway-order -> transaction mapping is resolved
through Razorpay's own records: the Razorpay order is
created with notes savebite_payment_transaction_id and
savebite_order_id, and verification/webhook fetch the
Razorpay order server-side and read those notes. If the
notes are absent, the handler does NOT confirm — it
fail-closes and reports the mapping as missing. The clean
fix is a proposed lookup RPC (see docs/architecture.md);
it is NOT applied here, and no private table is queried
directly to work around it.

Also a genuine limitation from the same gap: if a checkout
response is lost after a successful attach, a repeat checkout
with the same idempotency key creates a new Razorpay order
and the attach conflicts (different gateway order id), so
the API returns 422 instead of re-issuing the original
gateway order id. The customer is not charged by the
orphaned Razorpay order (it is unpaid), but recovery of the
original checkout needs the proposed lookup RPC. This is
documented, not hidden.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from app.config import Settings, get_settings
from app.dependencies import (
    get_current_user,
    get_razorpay_client,
    get_service_client,
    get_user_client,
)
from app.errors import (
    ApiError,
    BadGatewayError,
    ServiceUnavailableError,
)
from app.razorpay_client import RazorpayClient
from app.schemas import (
    AuthenticatedUser,
    CheckoutResponse,
    VerifyPaymentRequest,
    VerifyPaymentResponse,
    WebhookResponse,
)
from app.security import (
    validate_idempotency_key,
    verify_checkout_signature,
    verify_razorpay_webhook,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["payments"])

_TXN_NOTE_KEY = "savebite_payment_transaction_id"
_ORDER_NOTE_KEY = "savebite_order_id"


def rupees_to_paise(amount: Decimal) -> int:
    """Convert a Decimal rupee amount to integer paise. The
    database amount is numeric(12,2), so amount * 100 must be
    integral; anything else is a mismatch, not something to
    round away silently."""
    paise = amount * Decimal(100)
    if paise != paise.to_integral_value():
        raise ApiError(
            422, "VALIDATION_ERROR", "Payment amount cannot be represented in paise"
        )
    return int(paise)


def paise_to_rupees(amount_paise: int) -> Decimal:
    return (Decimal(amount_paise) / Decimal(100)).quantize(Decimal("0.01"))


def _validate_checkout_key(key: str | None) -> str:
    if key is None:
        raise ApiError(422, "VALIDATION_ERROR", "Idempotency-Key header is required")
    stripped = key.strip()
    if (
        len(stripped) < 8
        or len(stripped) > 128
        or not validate_idempotency_key(stripped)
    ):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Idempotency-Key must be 8-128 characters of letters, digits, - or _",
        )
    return stripped


def _transaction_id_from_order_notes(order: dict) -> UUID | None:
    notes = order.get("notes") or {}
    raw = notes.get(_TXN_NOTE_KEY)
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except ValueError:
        return None


@router.post(
    "/v1/orders/{order_id}/checkout",
    response_model=CheckoutResponse,
    status_code=201,
)
async def create_checkout(
    order_id: UUID,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: AuthenticatedUser = Depends(get_current_user),
    user_client: SupabaseRestClient = Depends(get_user_client),
    service_client: SupabaseRestClient = Depends(get_service_client),
    razorpay: RazorpayClient = Depends(get_razorpay_client),
    settings: Settings = Depends(get_settings),
) -> CheckoutResponse:
    """Start Razorpay checkout for a pending_payment order.

    Uses the caller's user-context client for
    begin_payment_checkout (ownership and eligibility are the
    database's checks) and the service-role client ONLY for
    backend_attach_gateway_order. The amount comes from the
    database, never from the request body — the frontend
    cannot choose or modify it."""
    key = _validate_checkout_key(idempotency_key)
    try:
        checkout = await user_client.rpc(
            "begin_payment_checkout",
            {"p_order_id": str(order_id), "p_idempotency_key": key},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not isinstance(checkout, dict) or not checkout.get("payment_transaction_id"):
        raise BadGatewayError("Checkout could not be started")
    currency = str(checkout.get("currency", "INR"))
    if currency != "INR":
        raise ApiError(422, "VALIDATION_ERROR", "Only INR payments are supported")
    try:
        amount = Decimal(str(checkout["amount"]))
    except (InvalidOperation, KeyError) as exc:
        raise BadGatewayError("Checkout returned an invalid amount") from exc
    amount_paise = rupees_to_paise(amount)
    transaction_id = str(checkout["payment_transaction_id"])
    # Razorpay order creation. A timeout here is ambiguous: the
    # order may or may not have been created at Razorpay. This
    # endpoint does NOT retry automatically, because a retry
    # would create a second Razorpay order. The client retries
    # with the same idempotency key; begin_payment_checkout
    # returns the same transaction, and the new Razorpay order
    # is attached instead. An orphaned, unpaid Razorpay order
    # charges nobody.
    razorpay_order = await razorpay.create_order(
        amount_paise,
        currency,
        notes={
            _TXN_NOTE_KEY: transaction_id,
            _ORDER_NOTE_KEY: str(order_id),
        },
    )
    gateway_order_id = razorpay_order.get("id")
    if not gateway_order_id:
        raise BadGatewayError("Payment provider did not return an order id")
    if (
        razorpay_order.get("amount") != amount_paise
        or razorpay_order.get("currency") != currency
    ):
        # Provider created an order for the wrong amount: do not
        # attach it, do not hand it to the frontend.
        raise BadGatewayError("Payment provider order amount does not match")
    try:
        await service_client.rpc(
            "backend_attach_gateway_order",
            {
                "p_payment_transaction_id": transaction_id,
                "p_gateway_order_id": gateway_order_id,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return CheckoutResponse(
        order_id=order_id,
        payment_transaction_id=UUID(transaction_id),
        key_id=settings.razorpay_key_id,
        razorpay_order_id=gateway_order_id,
        amount_paise=amount_paise,
        currency=currency,
        prefill_email=user.email,
    )


async def _resolve_captured_payment(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay: RazorpayClient,
) -> tuple[UUID, int, str]:
    """Resolve a payment through Razorpay's own API.

    Returns (payment_transaction_id, amount_paise, currency).
    Raises 422 for an order-id mismatch, a non-captured
    status, a non-INR currency, an invalid amount, or a
    missing transaction mapping. This does NOT check a
    checkout signature — callers that have one check it
    separately (verify endpoint); the webhook caller relies
    on the already-verified webhook signature instead."""
    payment = await razorpay.get_payment(razorpay_payment_id)
    provider_order_id = payment.get("order_id")
    if provider_order_id != razorpay_order_id:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Payment does not belong to the given Razorpay order",
        )
    if payment.get("status") != "captured":
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Payment is not captured; only captured payments can be confirmed",
        )
    if payment.get("currency") != "INR":
        raise ApiError(422, "VALIDATION_ERROR", "Only INR payments are supported")
    amount_paise = payment.get("amount")
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise ApiError(422, "VALIDATION_ERROR", "Provider payment amount is invalid")
    order = await razorpay.get_order(provider_order_id)
    transaction_id = _transaction_id_from_order_notes(order)
    if transaction_id is None:
        # Notes may also be on the payment itself; accept them
        # only from the provider-fetched payment, never from
        # the frontend.
        payment_notes = payment.get("notes") or {}
        raw = payment_notes.get(_TXN_NOTE_KEY)
        if raw:
            try:
                transaction_id = UUID(str(raw))
            except ValueError:
                transaction_id = None
    if transaction_id is None:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Payment cannot be tied to a SaveBite transaction",
        )
    return transaction_id, amount_paise, "INR"


@router.post("/v1/payments/verify", response_model=VerifyPaymentResponse)
async def verify_payment(
    payload: VerifyPaymentRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    service_client: SupabaseRestClient = Depends(get_service_client),
    razorpay: RazorpayClient = Depends(get_razorpay_client),
    settings: Settings = Depends(get_settings),
) -> VerifyPaymentResponse:
    """Verify a Razorpay Checkout result and, only if every
    check passes, confirm the capture. Authentication is
    required, but ownership and amount are NOT taken from the
    caller: they come from Razorpay's API and from the
    confirm RPC's own amount check. A replayed verification
    is safe: backend_confirm_payment_capture returns the
    order id without side effects when already captured."""
    transaction_id, amount_paise, currency = await _resolve_captured_payment(
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        razorpay,
    )
    # Signature is checked AFTER resolving through Razorpay's
    # API, and over the provider-confirmed order id — never
    # over an order id that only the frontend supplied.
    if not settings.razorpay_configured:
        raise ServiceUnavailableError("Razorpay is not configured")
    secret = settings.razorpay_key_secret
    assert secret is not None
    if not verify_checkout_signature(
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature,
        secret.get_secret_value(),
    ):
        raise ApiError(422, "VALIDATION_ERROR", "Invalid payment signature")
    try:
        order_id = await service_client.rpc(
            "backend_confirm_payment_capture",
            {
                "p_payment_transaction_id": str(transaction_id),
                "p_gateway_payment_id": payload.razorpay_payment_id,
                "p_amount": str(paise_to_rupees(amount_paise)),
                "p_signature_verified": True,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not order_id:
        raise BadGatewayError("Payment confirmation did not return an order")
    return VerifyPaymentResponse(
        order_id=UUID(str(order_id)),
        payment_transaction_id=transaction_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        verified=True,
        amount_paise=amount_paise,
        currency=currency,
    )


@router.post("/v1/webhooks/razorpay", response_model=WebhookResponse)
async def razorpay_webhook(
    request: Request,
    service_client: SupabaseRestClient = Depends(get_service_client),
    razorpay: RazorpayClient = Depends(get_razorpay_client),
    settings: Settings = Depends(get_settings),
) -> WebhookResponse:
    """Razorpay webhook. No Supabase Auth: the webhook
    signature IS the authentication, and it is verified
    against the RAW body before anything is parsed, recorded,
    or acted on. Missing or invalid signatures are rejected
    with 401 and nothing is processed.

    Recording happens before acting, so a crash between the
    two is recovered by Razorpay's retry: the redelivery
    records the same event id (no second row) and then acts.
    Confirm and mark-failed are themselves idempotent /
    capture-protecting, so a duplicate delivery cannot double
    capture or overwrite a capture with a failure."""
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_razorpay_webhook(raw_body, signature, settings):
        raise ApiError(401, "UNAUTHORIZED", "Invalid webhook signature")
    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError(
            422, "VALIDATION_ERROR", "Webhook body is not valid JSON"
        ) from exc
    if not isinstance(body, dict):
        raise ApiError(422, "VALIDATION_ERROR", "Webhook body must be an object")
    event = str(body.get("event", ""))
    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    payload = body.get("payload") or {}
    entity = {}
    if isinstance(payload, dict):
        for section in ("payment", "order"):
            section_value = payload.get(section) or {}
            if isinstance(section_value, dict) and isinstance(
                section_value.get("entity"), dict
            ):
                entity = section_value["entity"]
                break
    if not event_id:
        fallback_id = entity.get("id") or entity.get("order_id") or ""
        event_id = f"{event}:{fallback_id}" if fallback_id else event
    try:
        await service_client.rpc(
            "backend_record_payment_webhook_event",
            {
                "p_gateway": "razorpay",
                "p_gateway_event_id": event_id,
                "p_event_type": event,
                "p_payload": body,
                "p_signature_verified": True,
            },
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc

    if event == "payment.captured":
        # The webhook signature was verified above, so capture
        # is verified here by fetching the payment from
        # Razorpay (not by trusting the webhook payload's
        # status field alone) and confirming through the RPC.
        # A webhook that arrives before checkout verification
        # confirms first; the later verification is then a
        # no-op. A late webhook after capture is likewise a
        # no-op. Both orders are safe because confirm is
        # idempotent.
        payment_id = entity.get("id")
        gateway_order_id = entity.get("order_id")
        if not payment_id or not gateway_order_id:
            return WebhookResponse(processed=False, reason="missing_payment_reference")
        try:
            transaction_id, amount_paise, _currency = await _resolve_captured_payment(
                gateway_order_id, payment_id, razorpay
            )
        except ApiError as exc:
            # Unresolvable (e.g. missing transaction mapping):
            # recorded, but not confirmed — fail-closed. A
            # retry will not fix a missing mapping, so this
            # returns 200 with the reason for operations to
            # pick up, rather than retrying forever.
            return WebhookResponse(processed=False, reason=exc.message)
        try:
            await service_client.rpc(
                "backend_confirm_payment_capture",
                {
                    "p_payment_transaction_id": str(transaction_id),
                    "p_gateway_payment_id": payment_id,
                    "p_amount": str(paise_to_rupees(amount_paise)),
                    "p_signature_verified": True,
                },
            )
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        return WebhookResponse(processed=True, reason="payment_captured")

    if event == "payment.failed":
        payment_id = entity.get("id")
        gateway_order_id = entity.get("order_id")
        if not payment_id or not gateway_order_id:
            return WebhookResponse(processed=False, reason="missing_payment_reference")
        # Resolve the transaction through Razorpay's order
        # notes, the same way as for capture. A frontend-
        # reported failure is never trusted; only this
        # provider-verified webhook justifies mark_failed.
        try:
            order = await razorpay.get_order(gateway_order_id)
            failed_txn_id = _transaction_id_from_order_notes(order)
        except Exception as exc:
            raise translate_upstream_error(exc) from exc
        if failed_txn_id is None:
            return WebhookResponse(
                processed=False, reason="missing_payment_transaction_mapping"
            )
        error = entity.get("error") or {}
        failure_code = str(error.get("code") or "PAYMENT_FAILED")
        failure_description = str(error.get("description") or "")[:500]
        try:
            await service_client.rpc(
                "backend_mark_payment_failed",
                {
                    "p_payment_transaction_id": str(failed_txn_id),
                    "p_failure_code": failure_code,
                    "p_failure_description": failure_description or None,
                },
            )
        except Exception as exc:
            translated = translate_upstream_error(exc)
            # Already captured: the failure event must never
            # overwrite a capture. Treat as handled, not as a
            # failure to retry.
            if "captured_payment_cannot_be_failed" in translated.message:
                return WebhookResponse(processed=False, reason="already_captured")
            raise translated from exc
        return WebhookResponse(processed=True, reason="payment_failed")

    # order.paid and every other event type: recorded, not
    # acted on. Subscribing to payment.captured is sufficient;
    # order.paid is intentionally ignored here to avoid a
    # second, parallel confirmation path for the same payment
    # (confirm is idempotent, so handling it would still be
    # safe — it is simply not needed).
    return WebhookResponse(processed=False, reason=f"ignored_event:{event}")
