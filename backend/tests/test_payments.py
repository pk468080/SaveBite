"""Milestone 6 tests: Razorpay checkout, verification, webhooks.

All Supabase and Razorpay calls are faked. No test makes a
real payment request, uses a real secret, or touches live
Supabase. The fake service client enforces the real
allowlist (backend_* RPCs only); the fake user client refuses
backend_* RPCs; neither fake exposes a query method for
private tables, so any private-table access in the router
would fail loudly.
"""

import hashlib
import hmac
import json
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_current_user,
    get_razorpay_client,
    get_service_client,
    get_user_client,
)
from app.errors import BadGatewayError
from app.main import create_app
from app.razorpay_client import RazorpayClient
from app.schemas import AuthenticatedUser
from app.supabase_client import BACKEND_RPCS
from tests.conftest import test_settings as make_test_settings

USER = AuthenticatedUser(
    id=UUID("11111111-1111-4111-8111-111111111111"),
    email="customer@example.com",
    token="tok",
)
ORDER_ID = UUID("22222222-2222-4222-8222-222222222222")
TXN_ID = UUID("33333333-3333-4333-8333-333333333333")
KEY_ID = "rzp_test_abcdefgh"
KEY_SECRET = "test-key-secret-123456"
WEBHOOK_SECRET = "test-webhook-secret-123456"
RZP_ORDER_ID = "order_TestOrder123"
RZP_PAYMENT_ID = "pay_TestPayment123"


def checkout_signature(order_id=RZP_ORDER_ID, payment_id=RZP_PAYMENT_ID):
    message = f"{order_id}|{payment_id}".encode()
    return hmac.new(KEY_SECRET.encode(), message, hashlib.sha256).hexdigest()


def webhook_signature(raw: bytes):
    return hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


class FakeUserClient:
    def __init__(self, rpc_result=None, rpc_error=None, rpc_result_fn=None):
        self.rpc_result = rpc_result
        self.rpc_error = rpc_error
        self.rpc_result_fn = rpc_result_fn
        self.rpc_calls = []

    async def rpc(self, name, params):
        assert not name.startswith("backend_"), "user client must not call backend RPCs"
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        if self.rpc_result_fn is not None:
            return self.rpc_result_fn(name, params)
        return self.rpc_result


class FakeServiceClient:
    """Enforces the backend_* allowlist and the confirm /
    mark-failed state rules from the real RPCs (captured is
    idempotent; a captured payment cannot be failed). It also
    models the real attach / lookup state rules (B1): attach
    requires the row to be unattached or attached to the SAME
    gateway order id, a different id is a
    gateway_order_id_conflict, and the lookup RPC returns the
    currently attached order id (if any) plus status."""

    def __init__(self, rpc_error=None, rpc_errors=None):
        self.rpc_error = rpc_error
        self.rpc_errors = rpc_errors or {}
        self.rpc_calls = []
        self.captured: set[str] = set()
        self.failed: set[str] = set()
        self.recorded_events: dict[str, dict] = {}
        self.attached: dict[str, str] = {}
        self.txn_status: dict[str, str] = {}
        self.lookup_overrides: list = []
        self.fail_attach_after_commit = False
        self._attach_committed_once = False

    async def rpc(self, name, params):
        assert name in BACKEND_RPCS, (
            f"service client may only call backend RPCs, not {name}"
        )
        self.rpc_calls.append((name, params))
        if name in self.rpc_errors:
            raise self.rpc_errors[name]
        if self.rpc_error is not None:
            raise self.rpc_error
        if name == "backend_get_gateway_order_for_payment_transaction":
            if self.lookup_overrides:
                override = self.lookup_overrides.pop(0)
                if isinstance(override, Exception):
                    raise override
                return override
            txn = params["p_payment_transaction_id"]
            return {
                "payment_transaction_id": txn,
                "order_id": params["p_order_id"],
                "gateway": "razorpay",
                "gateway_order_id": self.attached.get(txn),
                "status": self.txn_status.get(txn, "created"),
            }
        if name == "backend_attach_gateway_order":
            txn = params["p_payment_transaction_id"]
            new_id = params["p_gateway_order_id"]
            existing = self.attached.get(txn)
            if existing is not None and existing != new_id:
                raise _upstream_error(400, "22023", "gateway_order_id_conflict")
            self.attached[txn] = new_id
            if self.fail_attach_after_commit and not self._attach_committed_once:
                self._attach_committed_once = True
                raise _upstream_error(504, "timeout", "Upstream service error")
            return None
        if name == "backend_confirm_payment_capture":
            txn = params["p_payment_transaction_id"]
            self.captured.add(txn)
            return str(ORDER_ID)
        if name == "backend_mark_payment_failed":
            txn = params["p_payment_transaction_id"]
            if txn in self.captured:
                raise _upstream_error(400, "P0001", "captured_payment_cannot_be_failed")
            self.failed.add(txn)
            return str(ORDER_ID)
        if name == "backend_record_payment_webhook_event":
            key = (params["p_gateway"], params["p_gateway_event_id"])
            self.recorded_events.setdefault(str(key), params)
            return "event-uuid"
        return None


class FakeRazorpay(RazorpayClient):
    def __init__(
        self,
        payment=None,
        order_notes=None,
        fail_create=False,
        timeout_create=False,
        order_ids=None,
        reply_overrides=None,
    ):
        super().__init__(KEY_ID, KEY_SECRET)
        self.payment = payment
        self.order_notes = order_notes
        self.fail_create = fail_create
        self.timeout_create = timeout_create
        self.order_ids = list(order_ids) if order_ids else []
        self.reply_overrides = reply_overrides or {}
        self.create_calls = []
        self.get_payment_calls = []
        self.get_order_calls = []

    async def create_order(self, amount_paise, currency, notes):
        self.create_calls.append((amount_paise, currency, notes))
        if self.timeout_create:
            raise BadGatewayError("Payment provider is unavailable")
        if self.fail_create:
            raise BadGatewayError("Payment provider request failed")
        order_id = self.order_ids.pop(0) if self.order_ids else RZP_ORDER_ID
        result = {
            "id": order_id,
            "amount": amount_paise,
            "currency": currency,
            "status": "created",
        }
        result.update(self.reply_overrides)
        return result

    async def get_payment(self, payment_id):
        self.get_payment_calls.append(payment_id)
        return dict(self.payment)

    async def get_order(self, order_id):
        self.get_order_calls.append(order_id)
        return {"id": order_id, "notes": dict(self.order_notes or {})}


def _payment(**overrides):
    payment = {
        "id": RZP_PAYMENT_ID,
        "order_id": RZP_ORDER_ID,
        "status": "captured",
        "amount": 39000,
        "currency": "INR",
        "notes": {},
    }
    payment.update(overrides)
    return payment


def _settings():
    settings = make_test_settings(
        razorpay_key_id=KEY_ID,
        razorpay_key_secret=KEY_SECRET,
        razorpay_webhook_secret=WEBHOOK_SECRET,
    )
    return settings


def _client_with(
    user_fake=None, service_fake=None, razorpay_fake=None, authenticated=True
):
    app = create_app(_settings())

    if user_fake is not None:
        app.dependency_overrides[get_user_client] = lambda: user_fake
    if service_fake is not None:
        app.dependency_overrides[get_service_client] = lambda: service_fake
    if razorpay_fake is not None:
        app.dependency_overrides[get_razorpay_client] = lambda: razorpay_fake
    if authenticated:

        async def _user():
            return USER

        app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


def _upstream_error(status, pg_code, message):
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/x")
    response = httpx.Response(
        status, json={"code": pg_code, "message": message}, request=request
    )
    return httpx.HTTPStatusError(message, request=request, response=response)


def _checkout_result(**overrides):
    result = {
        "payment_transaction_id": str(TXN_ID),
        "order_id": str(ORDER_ID),
        "amount": "390.00",
        "currency": "INR",
        "gateway": "razorpay",
    }
    result.update(overrides)
    return result


# --- checkout -----------------------------------------------------------


def test_checkout_success():
    user_fake = FakeUserClient(rpc_result=_checkout_result())
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay()
    client = _client_with(user_fake, service_fake, razorpay_fake)
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["key_id"] == KEY_ID
    assert body["razorpay_order_id"] == RZP_ORDER_ID
    assert body["payment_transaction_id"] == str(TXN_ID)
    assert body["amount_paise"] == 39000
    assert body["currency"] == "INR"
    assert body["prefill_email"] == "customer@example.com"
    assert KEY_SECRET not in response.text
    assert WEBHOOK_SECRET not in response.text
    assert user_fake.rpc_calls == [
        (
            "begin_payment_checkout",
            {"p_order_id": str(ORDER_ID), "p_idempotency_key": "checkout-key-123456"},
        )
    ]
    assert razorpay_fake.create_calls == [
        (
            39000,
            "INR",
            {
                "savebite_payment_transaction_id": str(TXN_ID),
                "savebite_order_id": str(ORDER_ID),
            },
        )
    ]
    assert service_fake.rpc_calls == [
        (
            "backend_get_gateway_order_for_payment_transaction",
            {
                "p_payment_transaction_id": str(TXN_ID),
                "p_order_id": str(ORDER_ID),
            },
        ),
        (
            "backend_attach_gateway_order",
            {
                "p_payment_transaction_id": str(TXN_ID),
                "p_gateway_order_id": RZP_ORDER_ID,
            },
        ),
    ]


def test_checkout_requires_authentication():
    app = create_app(_settings())
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 401


def test_checkout_wrong_owner_or_missing_order():
    user_fake = FakeUserClient(
        rpc_error=_upstream_error(404, "P0002", "order_not_found")
    )
    client = _client_with(user_fake, FakeServiceClient(), FakeRazorpay())
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 404


def test_checkout_expired_or_ineligible_reservation():
    user_fake = FakeUserClient(
        rpc_error=_upstream_error(400, "P0001", "reservation_expired_or_incomplete")
    )
    client = _client_with(user_fake, FakeServiceClient(), FakeRazorpay())
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize("key", [None, "short", "x" * 129, "bad key!"])
def test_checkout_idempotency_key_validation(key):
    user_fake = FakeUserClient(rpc_result=_checkout_result())
    client = _client_with(user_fake, FakeServiceClient(), FakeRazorpay())
    headers = {} if key is None else {"Idempotency-Key": key}
    response = client.post(f"/v1/orders/{ORDER_ID}/checkout", headers=headers)
    assert response.status_code == 422
    assert user_fake.rpc_calls == []


def test_checkout_repeated_same_key_reuses_transaction():
    # B1: same key, same order: begin returns the same
    # transaction, the lookup finds the already-attached
    # Razorpay order, and it is re-issued — no second
    # Razorpay order is created and no attach is attempted.
    user_fake = FakeUserClient(rpc_result=_checkout_result())
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay()
    client = _client_with(user_fake, service_fake, razorpay_fake)
    bodies = []
    for _ in range(2):
        response = client.post(
            f"/v1/orders/{ORDER_ID}/checkout",
            headers={"Idempotency-Key": "checkout-key-123456"},
        )
        assert response.status_code == 201
        bodies.append(response.json())
    assert len(user_fake.rpc_calls) == 2
    assert all(
        call[1]["p_idempotency_key"] == "checkout-key-123456"
        for call in user_fake.rpc_calls
    )
    assert bodies[0]["razorpay_order_id"] == bodies[1]["razorpay_order_id"]
    assert bodies[0]["razorpay_order_id"] == RZP_ORDER_ID
    assert len(razorpay_fake.create_calls) == 1
    assert (
        sum(
            1
            for call in service_fake.rpc_calls
            if call[0] == "backend_attach_gateway_order"
        )
        == 1
    )


def test_checkout_razorpay_timeout_is_502_and_no_attach():
    user_fake = FakeUserClient(rpc_result=_checkout_result())
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(timeout_create=True)
    client = _client_with(user_fake, service_fake, razorpay_fake)
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 502
    # The lookup read happened, but no attach was attempted
    # and the provider create was called exactly once.
    assert service_fake.rpc_calls == [
        (
            "backend_get_gateway_order_for_payment_transaction",
            {
                "p_payment_transaction_id": str(TXN_ID),
                "p_order_id": str(ORDER_ID),
            },
        )
    ]
    assert len(razorpay_fake.create_calls) == 1


def test_checkout_attach_failure_rejected():
    user_fake = FakeUserClient(rpc_result=_checkout_result())
    service_fake = FakeServiceClient(
        rpc_errors={
            "backend_attach_gateway_order": _upstream_error(
                400, "P0001", "payment_transaction_not_attachable"
            )
        }
    )
    client = _client_with(user_fake, service_fake, FakeRazorpay())
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "payment_transaction_not_attachable"
    # The failure is at attach time, after the lookup read and
    # the provider create — and no order id is handed out.
    assert "razorpay_order_id" not in response.text


def test_checkout_amount_conversion_and_currency():
    cases = [("390.00", 39000), ("195.50", 19550), ("0.01", 1)]
    for amount, paise in cases:
        user_fake = FakeUserClient(rpc_result=_checkout_result(amount=amount))
        client = _client_with(user_fake, FakeServiceClient(), FakeRazorpay())
        response = client.post(
            f"/v1/orders/{ORDER_ID}/checkout",
            headers={"Idempotency-Key": "checkout-key-123456"},
        )
        assert response.status_code == 201, response.text
        assert response.json()["amount_paise"] == paise
    user_fake = FakeUserClient(rpc_result=_checkout_result(currency="USD"))
    client = _client_with(user_fake, FakeServiceClient(), FakeRazorpay())
    response = client.post(
        f"/v1/orders/{ORDER_ID}/checkout",
        headers={"Idempotency-Key": "checkout-key-123456"},
    )
    assert response.status_code == 422


# --- verification ---------------------------------------------------------


def _verify_client(razorpay_fake, service_fake=None):
    return _client_with(
        FakeUserClient(), service_fake or FakeServiceClient(), razorpay_fake
    )


def _verify_payload(**overrides):
    payload = {
        "razorpay_order_id": RZP_ORDER_ID,
        "razorpay_payment_id": RZP_PAYMENT_ID,
        "razorpay_signature": checkout_signature(),
    }
    payload.update(overrides)
    return payload


def test_verify_success():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _verify_client(razorpay_fake, service_fake)
    response = client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["verified"] is True
    assert body["order_id"] == str(ORDER_ID)
    assert body["payment_transaction_id"] == str(TXN_ID)
    assert body["amount_paise"] == 39000
    assert service_fake.rpc_calls == [
        (
            "backend_confirm_payment_capture",
            {
                "p_payment_transaction_id": str(TXN_ID),
                "p_gateway_payment_id": RZP_PAYMENT_ID,
                "p_amount": "390.00",
                "p_signature_verified": True,
            },
        )
    ]


def test_verify_requires_authentication():
    app = create_app(_settings())
    app.dependency_overrides[get_razorpay_client] = lambda: FakeRazorpay(
        payment=_payment(), order_notes={}
    )
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 401


@pytest.mark.parametrize(
    "override",
    [
        {"razorpay_signature": "0" * 64},
        {"razorpay_signature": ""},
        {"razorpay_order_id": "order_SomeoneElsesOrder"},
        {"razorpay_payment_id": "pay_SomeoneElsesPayment"},
    ],
)
def test_verify_bad_signature_or_mismatched_ids(override):
    razorpay_fake = FakeRazorpay(
        payment=_payment(),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _verify_client(razorpay_fake)
    response = client.post("/v1/payments/verify", json=_verify_payload(**override))
    assert response.status_code == 422


def test_verify_payment_not_captured_not_confirmed():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(status="authorized"),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _verify_client(razorpay_fake, service_fake)
    response = client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 422
    assert service_fake.rpc_calls == []


def test_verify_currency_mismatch_not_confirmed():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(currency="USD"),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _verify_client(razorpay_fake, service_fake)
    response = client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 422
    assert service_fake.rpc_calls == []


def test_verify_amount_comes_from_provider_not_frontend():
    # The request body carries no amount at all; the amount
    # passed to confirm is the provider-fetched amount.
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(amount=19500),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _verify_client(razorpay_fake, service_fake)
    response = client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 200
    _name, params = service_fake.rpc_calls[0]
    assert params["p_amount"] == "195.00"


def test_verify_replay_is_idempotent():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _verify_client(razorpay_fake, service_fake)
    for _ in range(2):
        response = client.post("/v1/payments/verify", json=_verify_payload())
        assert response.status_code == 200
    assert len(service_fake.captured) == 1


def test_verify_missing_transaction_mapping_not_confirmed():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(payment=_payment(), order_notes={})
    client = _verify_client(razorpay_fake, service_fake)
    response = client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 422
    assert service_fake.rpc_calls == []


# --- webhooks -------------------------------------------------------------


def _webhook_client(service_fake, razorpay_fake):
    app = create_app(_settings())
    app.dependency_overrides[get_service_client] = lambda: service_fake
    app.dependency_overrides[get_razorpay_client] = lambda: razorpay_fake
    return TestClient(app, raise_server_exceptions=False)


def _webhook_body(event, payment_overrides=None):
    return {
        "event": event,
        "payload": {
            "payment": {
                "entity": {
                    "id": RZP_PAYMENT_ID,
                    "order_id": RZP_ORDER_ID,
                    "status": "captured" if event == "payment.captured" else "failed",
                    "amount": 39000,
                    "currency": "INR",
                    "error_code": None
                    if event == "payment.captured"
                    else "BAD_REQUEST_ERROR",
                    "error_description": None
                    if event == "payment.captured"
                    else "Payment failed",
                    **(payment_overrides or {}),
                }
            }
        },
    }


def _post_webhook(client, body, event_id="evt_test_123", tamper=False):
    raw = json.dumps(body).encode("utf-8")
    signature = webhook_signature(raw)
    if tamper:
        # Sign the original body, then tamper the bytes sent:
        # the signature must no longer match what arrives.
        raw = raw + b" "
    return client.post(
        "/v1/webhooks/razorpay",
        content=raw,
        headers={
            "X-Razorpay-Signature": signature,
            "X-Razorpay-Event-Id": event_id,
        },
    )


def test_webhook_captured_success():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _webhook_client(service_fake, razorpay_fake)
    response = _post_webhook(client, _webhook_body("payment.captured"))
    assert response.status_code == 200, response.text
    assert response.json()["processed"] is True
    names = [name for name, _ in service_fake.rpc_calls]
    assert "backend_record_payment_webhook_event" in names
    assert "backend_confirm_payment_capture" in names
    assert len(service_fake.captured) == 1


def test_webhook_invalid_or_missing_signature_rejected():
    service_fake = FakeServiceClient()
    client = _webhook_client(service_fake, FakeRazorpay())
    body = _webhook_body("payment.captured")
    raw = json.dumps(body).encode("utf-8")
    response = client.post(
        "/v1/webhooks/razorpay",
        content=raw,
        headers={"X-Razorpay-Signature": "0" * 64, "X-Razorpay-Event-Id": "evt_1"},
    )
    assert response.status_code == 401
    response = client.post(
        "/v1/webhooks/razorpay", content=raw, headers={"X-Razorpay-Event-Id": "evt_1"}
    )
    assert response.status_code == 401
    assert service_fake.rpc_calls == []


def test_webhook_tampered_body_rejected():
    service_fake = FakeServiceClient()
    client = _webhook_client(service_fake, FakeRazorpay())
    response = _post_webhook(client, _webhook_body("payment.captured"), tamper=True)
    # Tampering after signing changes the body, so the
    # signature no longer matches the raw bytes received.
    assert response.status_code == 401
    assert service_fake.rpc_calls == []


def test_webhook_duplicate_event_no_double_capture():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _webhook_client(service_fake, razorpay_fake)
    for _ in range(2):
        response = _post_webhook(client, _webhook_body("payment.captured"))
        assert response.status_code == 200
    # Recorded twice (deduped by the RPC's unique constraint
    # in production), but the capture itself happened once.
    assert len(service_fake.captured) == 1
    assert len(service_fake.recorded_events) == 1


def test_webhook_failed_marks_failed():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(status="failed"),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _webhook_client(service_fake, razorpay_fake)
    response = _post_webhook(client, _webhook_body("payment.failed"))
    assert response.status_code == 200
    assert response.json()["processed"] is True
    assert str(TXN_ID) in service_fake.failed


def test_webhook_failed_after_capture_does_not_overwrite():
    service_fake = FakeServiceClient()
    service_fake.captured.add(str(TXN_ID))
    razorpay_fake = FakeRazorpay(
        payment=_payment(status="failed"),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    client = _webhook_client(service_fake, razorpay_fake)
    response = _post_webhook(client, _webhook_body("payment.failed"))
    assert response.status_code == 200
    assert response.json()["processed"] is False
    assert response.json()["reason"] == "already_captured"
    assert str(TXN_ID) not in service_fake.failed


def test_webhook_unexpected_event_recorded_but_ignored():
    service_fake = FakeServiceClient()
    client = _webhook_client(service_fake, FakeRazorpay())
    response = _post_webhook(client, {"event": "refund.processed", "payload": {}})
    assert response.status_code == 200
    assert response.json()["processed"] is False
    names = [name for name, _ in service_fake.rpc_calls]
    assert names == ["backend_record_payment_webhook_event"]


def test_webhook_before_verification_then_verification():
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(
        payment=_payment(),
        order_notes={"savebite_payment_transaction_id": str(TXN_ID)},
    )
    webhook_client = _webhook_client(service_fake, razorpay_fake)
    response = _post_webhook(webhook_client, _webhook_body("payment.captured"))
    assert response.status_code == 200
    verify_client = _verify_client(razorpay_fake, service_fake)
    response = verify_client.post("/v1/payments/verify", json=_verify_payload())
    assert response.status_code == 200
    assert len(service_fake.captured) == 1


def test_webhook_record_rpc_failure_is_502():
    service_fake = FakeServiceClient(
        rpc_error=_upstream_error(500, "XX000", "database unavailable")
    )
    client = _webhook_client(service_fake, FakeRazorpay())
    response = _post_webhook(client, _webhook_body("payment.captured"))
    assert response.status_code == 502


def test_webhook_no_secrets_in_response():
    service_fake = FakeServiceClient()
    client = _webhook_client(service_fake, FakeRazorpay())
    response = _post_webhook(client, {"event": "refund.processed", "payload": {}})
    assert KEY_SECRET not in response.text
    assert WEBHOOK_SECRET not in response.text


def test_razorpay_client_never_logs_secret():
    # The client module has no logging calls at all; assert
    # by construction: its source must not contain log/print
    # of the secret attribute.
    import pathlib

    source = pathlib.Path("app/razorpay_client.py").read_text()
    assert "logging" not in source
    assert "print(" not in source


# --- B1: checkout retry recovery ----------------------------------------

OTHER_ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")
TXN_ID_2 = UUID("44444444-4444-4444-8444-444444444444")


def _b1_client(user_fake=None, service_fake=None, razorpay_fake=None):
    return _client_with(
        user_fake or FakeUserClient(rpc_result=_checkout_result()),
        service_fake or FakeServiceClient(),
        razorpay_fake or FakeRazorpay(),
    )


def _b1_checkout(client, order_id=ORDER_ID, key="checkout-key-123456"):
    return client.post(
        f"/v1/orders/{order_id}/checkout", headers={"Idempotency-Key": key}
    )


def test_b1_sequential_retry_after_lost_response_reuses_order():
    # The first checkout attaches; the second call (same key,
    # e.g. after a lost response) must return the identical
    # response, not a second gateway order.
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay()
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    first = _b1_checkout(client)
    second = _b1_checkout(client)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["razorpay_order_id"] == RZP_ORDER_ID
    assert len(razorpay_fake.create_calls) == 1
    assert (
        sum(
            1
            for call in service_fake.rpc_calls
            if call[0] == "backend_attach_gateway_order"
        )
        == 1
    )


def test_b1_different_key_creates_new_transaction():
    # A different idempotency key is a different logical
    # attempt (e.g. a new tab): a new transaction, a new
    # gateway order, and no reuse of the first order.
    def begin_fn(name, params):
        txn = (
            str(TXN_ID)
            if params["p_idempotency_key"] == "checkout-key-aaaaaa1"
            else str(TXN_ID_2)
        )
        return _checkout_result(payment_transaction_id=txn)

    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay()
    client = _b1_client(
        user_fake=FakeUserClient(rpc_result_fn=begin_fn),
        service_fake=service_fake,
        razorpay_fake=razorpay_fake,
    )
    first = _b1_checkout(client, key="checkout-key-aaaaaa1")
    second = _b1_checkout(client, key="checkout-key-bbbbbb2")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["payment_transaction_id"] == str(TXN_ID)
    assert second.json()["payment_transaction_id"] == str(TXN_ID_2)
    assert len(razorpay_fake.create_calls) == 2


def test_b1_different_order_same_key_conflict():
    # The idempotency key is globally unique: the same key
    # for another order is a conflict, and no provider order
    # is created for it.
    def begin_fn(name, params):
        if params["p_order_id"] != str(ORDER_ID):
            raise _upstream_error(400, "22023", "payment_idempotency_conflict")
        return _checkout_result()

    razorpay_fake = FakeRazorpay()
    client = _b1_client(
        user_fake=FakeUserClient(rpc_result_fn=begin_fn),
        razorpay_fake=razorpay_fake,
    )
    assert _b1_checkout(client).status_code == 201
    response = _b1_checkout(client, order_id=OTHER_ORDER_ID)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "payment_idempotency_conflict"
    assert len(razorpay_fake.create_calls) == 1


def test_b1_concurrent_retry_returns_winner_not_loser():
    # Two requests sharing one transaction: A attaches first.
    # B's lookup ran before A's attach (simulated with a
    # one-shot stale lookup result), so B creates a second
    # provider order and loses the attach race. B must return
    # A's winning order — never its own unattached order,
    # and never a bare 422 now that a valid order exists.
    winner = "order_race_winner"
    loser = "order_race_loser"
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(order_ids=[winner, loser])
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    first = _b1_checkout(client)
    assert first.status_code == 201
    assert first.json()["razorpay_order_id"] == winner
    service_fake.lookup_overrides.append(
        {
            "payment_transaction_id": str(TXN_ID),
            "order_id": str(ORDER_ID),
            "gateway": "razorpay",
            "gateway_order_id": None,
            "status": "created",
        }
    )
    second = _b1_checkout(client)
    assert second.status_code == 201
    assert second.json()["razorpay_order_id"] == winner
    assert loser not in first.text
    assert loser not in second.text
    assert len(razorpay_fake.create_calls) == 2


def test_b1_attach_committed_but_response_lost_then_retry_recovers():
    # The attach commits but its response is lost (the first
    # call sees a 502). The retry's lookup finds the
    # committed order and returns it; no second provider
    # order is created.
    service_fake = FakeServiceClient()
    service_fake.fail_attach_after_commit = True
    razorpay_fake = FakeRazorpay()
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    first = _b1_checkout(client)
    assert first.status_code == 502
    assert service_fake.attached[str(TXN_ID)] == RZP_ORDER_ID
    second = _b1_checkout(client)
    assert second.status_code == 201
    assert second.json()["razorpay_order_id"] == RZP_ORDER_ID
    assert len(razorpay_fake.create_calls) == 1


def test_b1_conflict_without_winner_keeps_original_error():
    # An attach conflict with no committed winner on
    # re-lookup (e.g. the conflict came from a failed
    # attach, not a winning one) keeps the original 422 —
    # the loser's unattached order is never returned.
    service_fake = FakeServiceClient(
        rpc_errors={
            "backend_attach_gateway_order": _upstream_error(
                400, "22023", "gateway_order_id_conflict"
            )
        }
    )
    razorpay_fake = FakeRazorpay()
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    response = _b1_checkout(client)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "gateway_order_id_conflict"
    assert "razorpay_order_id" not in response.text
    assert len(razorpay_fake.create_calls) == 1


def test_b1_relookup_failure_keeps_original_conflict():
    # The attach loses a race, but the recovery re-lookup
    # itself fails: fail closed with the original conflict,
    # never a fabricated or guessed order id.
    service_fake = FakeServiceClient()
    service_fake.attached[str(TXN_ID)] = "order_race_winner"
    service_fake.lookup_overrides = [
        {
            "payment_transaction_id": str(TXN_ID),
            "order_id": str(ORDER_ID),
            "gateway": "razorpay",
            "gateway_order_id": None,
            "status": "created",
        },
        _upstream_error(503, "", "Upstream service error"),
    ]
    razorpay_fake = FakeRazorpay(order_ids=["order_race_loser"])
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    response = _b1_checkout(client)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "gateway_order_id_conflict"
    assert "order_race_loser" not in response.text


def test_b1_lookup_unavailable_fails_closed():
    # The attachment state cannot be determined: no provider
    # order may be created, and no attach may be attempted.
    service_fake = FakeServiceClient(
        rpc_errors={
            "backend_get_gateway_order_for_payment_transaction": _upstream_error(
                503, "", "Upstream service error"
            )
        }
    )
    razorpay_fake = FakeRazorpay()
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    response = _b1_checkout(client)
    assert response.status_code == 502
    assert len(razorpay_fake.create_calls) == 0
    assert not any(
        call[0] == "backend_attach_gateway_order" for call in service_fake.rpc_calls
    )


def test_b1_timeout_then_retry_creates_fresh_order():
    # A timed-out create attaches nothing, so it cannot be
    # recovered — but the retry must succeed with a fresh
    # order instead of failing, and the timed-out attempt
    # must never be returned (it produced no order id here).
    razorpay_fake = FakeRazorpay(timeout_create=True, order_ids=["order_retry_fresh"])
    client = _b1_client(razorpay_fake=razorpay_fake)
    first = _b1_checkout(client)
    assert first.status_code == 502
    razorpay_fake.timeout_create = False
    second = _b1_checkout(client)
    assert second.status_code == 201
    assert second.json()["razorpay_order_id"] == "order_retry_fresh"
    assert len(razorpay_fake.create_calls) == 2


@pytest.mark.parametrize(
    "status",
    [
        "captured",
        "failed",
        "reconciliation_required",
        "refunded",
        "partially_refunded",
    ],
)
@pytest.mark.parametrize("attached", [True, False])
def test_b1_non_attachable_statuses_create_nothing(status, attached):
    # No new gateway order for captured, failed,
    # reconciliation-required, refunded, or any other
    # non-attachable state — whether or not an order was
    # previously attached. A failed payment needs a fresh
    # transaction (new idempotency key), not a reset here.
    service_fake = FakeServiceClient()
    service_fake.txn_status[str(TXN_ID)] = status
    if attached:
        service_fake.attached[str(TXN_ID)] = RZP_ORDER_ID
    razorpay_fake = FakeRazorpay()
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    response = _b1_checkout(client)
    assert response.status_code == 422
    assert response.json()["error"]["message"] == "payment_transaction_not_attachable"
    assert len(razorpay_fake.create_calls) == 0


@pytest.mark.parametrize("reply_overrides", [{"amount": 999}, {"currency": "USD"}])
def test_b1_provider_mismatch_not_attached(reply_overrides):
    # A provider order for the wrong amount or currency is
    # never attached and never handed to the frontend.
    service_fake = FakeServiceClient()
    razorpay_fake = FakeRazorpay(reply_overrides=reply_overrides)
    client = _b1_client(service_fake=service_fake, razorpay_fake=razorpay_fake)
    response = _b1_checkout(client)
    assert response.status_code == 502
    assert "razorpay_order_id" not in response.text
    assert not any(
        call[0] == "backend_attach_gateway_order" for call in service_fake.rpc_calls
    )


def test_b1_lookup_rpc_is_service_only_and_no_table_query():
    # The user-context client refuses any backend_* name
    # before any HTTP call, and the checkout path calls the
    # service client only for the lookup + attach RPCs —
    # never a table query, so no private-table access path
    # is introduced by B1.
    user_fake = FakeUserClient()
    with pytest.raises(AssertionError):
        import asyncio

        asyncio.run(
            user_fake.rpc("backend_get_gateway_order_for_payment_transaction", {})
        )
    service_fake = FakeServiceClient()
    assert not hasattr(service_fake, "query")
    client = _b1_client(service_fake=service_fake)
    assert _b1_checkout(client).status_code == 201
    assert {call[0] for call in service_fake.rpc_calls} <= {
        "backend_get_gateway_order_for_payment_transaction",
        "backend_attach_gateway_order",
    }
