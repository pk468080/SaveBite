"""Milestone 8 tests: pickup token issuance and verification.

All Supabase calls are faked. The fake verify RPC mirrors
the real database rules that matter here: a token can be
used once, and a second verification fails. Database
atomicity itself (FOR UPDATE row locks) is a property of
the real RPC, not something a mock can prove — the tests
prove the API never bypasses the RPC and never invents a
collection. No test touches live Supabase or a private
table, and no test uses the service-role client.
"""

from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

CUSTOMER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_CUSTOMER_ID = UUID("12121212-1212-4121-8121-121212121212")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")
TOKEN = "a" * 64
QR_PAYLOAD = f"SB1:{TOKEN}"


class PickupFake:
    def __init__(self, tables=None, rpc_error=None, used_tokens=None):
        self.tables = tables or {}
        self.rpc_error = rpc_error
        self.rpc_calls = []
        self.query_calls = []
        self.used_tokens = set(used_tokens or [])

    async def query(self, table, *, select="*", filters=None):
        assert not table.startswith("private."), "private tables must not be queried"
        self.query_calls.append((table, select, filters))
        rows = list(self.tables.get(table, []))
        if filters:
            for key, value in filters.items():
                if isinstance(value, str) and value.startswith("eq."):
                    rows = [r for r in rows if str(r.get(key)) == value[3:]]
                elif isinstance(value, str) and value.startswith("in.("):
                    wanted = value[4:-1].split(",") if value[4:-1] else []
                    rows = [r for r in rows if str(r.get(key)) in wanted]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]

    async def rpc(self, name, params):
        assert not name.startswith("backend_"), (
            "pickup RPCs are user-context, not backend"
        )
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        if name == "issue_pickup_token":
            return {
                "pickup_token_id": "token-uuid-not-exposed",
                "pickup_token": TOKEN,
                "expires_at": "2026-10-31T21:30:00+00:00",
            }
        if name == "verify_pickup_token":
            if params["p_pickup_token"] in self.used_tokens:
                raise _upstream_error(400, "P0001", "pickup_token_invalid_or_used")
            self.used_tokens.add(params["p_pickup_token"])
            return {
                "order_id": str(ORDER_ID),
                "order_number": "SF-20261031-000001",
                "status": "collected",
                "collected_at": "2026-10-31T18:30:00+00:00",
            }
        return {}


def _tables():
    return {
        "orders": [
            {
                "id": str(ORDER_ID),
                "order_number": "SF-20261031-000001",
                "customer_id": str(CUSTOMER_ID),
                "store_id": str(STORE_ID),
                "status": "confirmed",
                "payment_status": "captured",
                "pickup_starts_at": "2026-10-31T18:00:00+00:00",
                "pickup_ends_at": "2026-10-31T21:00:00+00:00",
            }
        ],
        "stores": [
            {
                "id": str(STORE_ID),
                "name": "Sharma Foods Dwarka",
                "pickup_instructions": "Collect from counter",
            }
        ],
        "order_items": [
            {
                "order_id": str(ORDER_ID),
                "listing_title_snapshot": "Evening Surprise Bag",
                "quantity": 2,
            }
        ],
    }


def _client_with(fake, authenticated=True):
    app = create_app(make_test_settings())
    app.dependency_overrides[get_user_client] = lambda: fake
    if authenticated:
        user = AuthenticatedUser(id=CUSTOMER_ID, email="user@example.com", token="tok")

        async def _user():
            return user

        app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


def _upstream_error(status, pg_code, message):
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/x")
    response = httpx.Response(
        status, json={"code": pg_code, "message": message}, request=request
    )
    return httpx.HTTPStatusError(message, request=request, response=response)


# --- issuance -------------------------------------------------------------


def test_issue_success_returns_token_once_and_qr_payload():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(f"/v1/orders/{ORDER_ID}/pickup-token")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["pickup_token"] == TOKEN
    assert body["qr_payload"] == QR_PAYLOAD
    assert body["order_number"] == "SF-20261031-000001"
    assert body["store_name"] == "Sharma Foods Dwarka"
    assert body["expires_at"] == "2026-10-31T21:30:00Z"
    assert body["pickup_instructions"] == "Collect from counter"
    # No internal token id, no hash, no customer contact data.
    assert "pickup_token_id" not in body
    assert "token_hash" not in response.text
    assert "user@example.com" not in response.text
    assert fake.rpc_calls == [("issue_pickup_token", {"p_order_id": str(ORDER_ID)})]


def test_issue_requires_authentication():
    client = _client_with(PickupFake(tables=_tables()), authenticated=False)
    assert client.post(f"/v1/orders/{ORDER_ID}/pickup-token").status_code == 401


def test_issue_other_customer_order_404():
    tables = _tables()
    tables["orders"][0]["customer_id"] = str(OTHER_CUSTOMER_ID)
    fake = PickupFake(tables=tables)
    client = _client_with(fake)
    assert client.post(f"/v1/orders/{ORDER_ID}/pickup-token").status_code == 404
    assert fake.rpc_calls == []


@pytest.mark.parametrize(
    "error,expected",
    [
        (_upstream_error(400, "P0001", "pickup_not_available"), 422),
        (_upstream_error(400, "P0001", "pickup_window_expired"), 422),
    ],
)
def test_issue_ineligible_order_rejected(error, expected):
    fake = PickupFake(tables=_tables(), rpc_error=error)
    client = _client_with(fake)
    response = client.post(f"/v1/orders/{ORDER_ID}/pickup-token")
    assert response.status_code == expected


# --- verification -----------------------------------------------------------


def test_verify_success_collects_once():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": QR_PAYLOAD},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "collected"
    assert body["order_number"] == "SF-20261031-000001"
    assert body["store_name"] == "Sharma Foods Dwarka"
    assert body["collected_at"] == "2026-10-31T18:30:00Z"
    assert body["items"][0]["title"] == "Evening Surprise Bag"
    # The QR prefix is stripped before the RPC; the RPC
    # receives only the raw token.
    assert fake.rpc_calls == [
        (
            "verify_pickup_token",
            {"p_store_id": str(STORE_ID), "p_pickup_token": TOKEN},
        )
    ]


def test_verify_accepts_raw_token_too():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert response.status_code == 200


def test_verify_requires_authentication():
    client = _client_with(PickupFake(tables=_tables()), authenticated=False)
    response = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert response.status_code == 401


def test_verify_unauthorized_store_403():
    fake = PickupFake(
        tables=_tables(),
        rpc_error=_upstream_error(403, "42501", "pickup_access_denied"),
    )
    client = _client_with(fake)
    response = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert response.status_code == 403


def test_verify_wrong_store_or_ineligible_422_generic():
    for message in ("order_not_collectable", "outside_pickup_window"):
        fake = PickupFake(
            tables=_tables(), rpc_error=_upstream_error(400, "P0001", message)
        )
        client = _client_with(fake)
        response = client.post(
            "/v1/merchant/pickups/verify",
            json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
        )
        assert response.status_code == 422, message
        # The generic message must not say which reason it was
        # beyond the safe category.
        assert "token_hash" not in response.text


def test_verify_invalid_format_rejected_before_rpc():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    for bad in ("short", "not-hex-" + "z" * 58, "SB1:short"):
        response = client.post(
            "/v1/merchant/pickups/verify",
            json={"store_id": str(STORE_ID), "pickup_token": bad},
        )
        assert response.status_code == 422, bad
    assert fake.rpc_calls == []


def test_verify_replay_second_scan_fails():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    first = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert first.status_code == 200
    second = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert second.status_code == 422
    assert "already used" in second.json()["error"]["message"]


def test_verify_already_used_token_from_start_fails():
    fake = PickupFake(tables=_tables(), used_tokens={TOKEN})
    client = _client_with(fake)
    response = client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert response.status_code == 422


def test_verify_request_carries_no_identity_or_status():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        "/v1/merchant/pickups/verify",
        json={
            "store_id": str(STORE_ID),
            "pickup_token": TOKEN,
            "customer_id": str(OTHER_CUSTOMER_ID),
            "status": "collected",
            "merchant_id": "99999999-9999-4999-8999-999999999999",
        },
    )
    assert response.status_code == 200, response.text
    _name, params = fake.rpc_calls[0]
    assert set(params) == {"p_store_id", "p_pickup_token"}


def test_no_private_table_queries():
    fake = PickupFake(tables=_tables())
    client = _client_with(fake)
    client.post(f"/v1/orders/{ORDER_ID}/pickup-token")
    client.post(
        "/v1/merchant/pickups/verify",
        json={"store_id": str(STORE_ID), "pickup_token": TOKEN},
    )
    assert all(not t.startswith("private.") for t, _s, _f in fake.query_calls)
