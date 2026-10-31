"""Payment-webhook security primitives and idempotency helpers.

Milestone 2 does NOT integrate Razorpay, does NOT trigger payments,
and does NOT call any payment RPC. This module implements the one
primitive the Milestone 6 webhook handler must use FIRST, before
recording or acting on any webhook event:

1. Verify the Razorpay signature against the RAW request body with
   HMAC-SHA256 and a constant-time comparison.
2. Only if the signature verifies, call
   backend_record_payment_webhook_event with p_signature_verified=True.
3. Never trust a client success screen, an unverified webhook, or a
   frontend payment status as payment confirmation.

Fail-closed: if RAZORPAY_WEBHOOK_SECRET is not configured, verification
is impossible and must be treated as a failure, never as a pass.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from app.config import Settings
from app.errors import ServiceUnavailableError

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def verify_razorpay_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    """Return True only if `signature` is the HMAC-SHA256 hex digest of
    `raw_body` under `secret`. Razorpay sends the signature as a hex
    string in the X-Razorpay-Signature header."""
    if not raw_body or not signature or not secret:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def verify_razorpay_webhook(
    raw_body: bytes, signature: str, settings: Settings
) -> bool:
    """Verify a webhook using the configured secret. Raises if no
    secret is configured — an unconfigured webhook endpoint must
    reject, not accept, events."""
    secret_obj = settings.razorpay_webhook_secret
    if secret_obj is None or not secret_obj.get_secret_value():
        raise ServiceUnavailableError("Razorpay webhook secret is not configured")
    return verify_razorpay_signature(raw_body, signature, secret_obj.get_secret_value())


def verify_checkout_signature(
    razorpay_order_id: str, razorpay_payment_id: str, signature: str, secret: str
) -> bool:
    """Verify a Razorpay Checkout callback signature.

    Canonical format, per Razorpay's Standard Checkout docs:
    HMAC-SHA256 over ``razorpay_order_id + "|" + razorpay_payment_id``
    keyed with the API key secret, hex-encoded, compared in
    constant time. The caller must pass the order id confirmed
    from Razorpay's own API, never an order id that only the
    frontend supplied — a valid signature proves Razorpay
    processed that payment for that Razorpay order, but it does
    not by itself prove the payment belongs to a SaveBite order
    or that it was captured (see the payments router, which
    fetches the payment from Razorpay and checks status and
    amount before confirming anything)."""
    if not razorpay_order_id or not razorpay_payment_id or not signature or not secret:
        return False
    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode()
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def validate_idempotency_key(key: str) -> bool:
    """Idempotency keys must be caller-supplied, opaque, and bounded.
    A duplicate key with a different payload must be rejected by the
    handler (database idempotency_records, Milestone 5/6); this helper
    only validates the key's shape."""
    return bool(_IDEMPOTENCY_KEY_RE.match(key))
