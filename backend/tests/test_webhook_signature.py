import hashlib
import hmac

import pytest

from app.config import Settings
from app.errors import ServiceUnavailableError
from app.security import (
    validate_idempotency_key,
    verify_razorpay_signature,
    verify_razorpay_webhook,
)

SECRET = "test-webhook-secret"
BODY = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_123"}}}}'


def _sig(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_verifies():
    assert verify_razorpay_signature(BODY, _sig(BODY, SECRET), SECRET) is True


def test_tampered_body_fails():
    assert (
        verify_razorpay_signature(b'{"event":"tampered"}', _sig(BODY, SECRET), SECRET)
        is False
    )


def test_tampered_signature_fails():
    assert verify_razorpay_signature(BODY, "0" * 64, SECRET) is False


def test_empty_inputs_fail_closed():
    assert verify_razorpay_signature(b"", _sig(BODY, SECRET), SECRET) is False
    assert verify_razorpay_signature(BODY, "", SECRET) is False
    assert verify_razorpay_signature(BODY, _sig(BODY, SECRET), "") is False


def test_webhook_without_configured_secret_raises():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="k",
        razorpay_webhook_secret=None,
    )
    with pytest.raises(ServiceUnavailableError):
        verify_razorpay_webhook(BODY, _sig(BODY, SECRET), settings)


def test_webhook_with_configured_secret_verifies():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="k",
        razorpay_webhook_secret=SECRET,
    )
    assert verify_razorpay_webhook(BODY, _sig(BODY, SECRET), settings) is True


def test_idempotency_key_shape():
    assert validate_idempotency_key("order-123_abc") is True
    assert validate_idempotency_key("") is False
    assert validate_idempotency_key("has space") is False
    assert validate_idempotency_key("x" * 129) is False
