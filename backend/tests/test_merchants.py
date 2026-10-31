"""Milestone 3 tests: merchant onboarding, stores, store hours.

All Supabase access is faked. No test touches live Supabase, and no
test uses a real secret or token. The fake respects PostgREST
filters (eq / in) and select columns, so membership isolation is
tested for real, not just by setting up convenient rows.
"""

from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_service_client, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_USER_ID = UUID("99999999-9999-4999-8999-999999999999")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_MERCHANT_ID = UUID("33333333-3333-4333-8333-333333333333")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
OTHER_STORE_ID = UUID("55555555-5555-4555-8555-555555555555")

USER = AuthenticatedUser(id=USER_ID, email="owner@example.com", token="tok")


def merchant_row(merchant_id=MERCHANT_ID, **overrides):
    row = {
        "id": str(merchant_id),
        "legal_name": "Sharma Foods Pvt Ltd",
        "display_name": "Sharma Foods",
        "business_type": "restaurant",
        "business_email": "hello@sharma.example.com",
        "business_phone": "9876543210",
        "status": "pending_review",
        "verification_status": "pending",
        "created_at": "2026-10-31T00:00:00Z",
        "updated_at": "2026-10-31T00:00:00Z",
    }
    row.update(overrides)
    return row


def store_row(store_id=STORE_ID, merchant_id=MERCHANT_ID, **overrides):
    row = {
        "id": str(store_id),
        "merchant_id": str(merchant_id),
        "name": "Sharma Foods Dwarka",
        "slug": "sharma-foods-dwarka",
        "address_line_1": "Shop 12, Sector 7 Market",
        "address_line_2": None,
        "locality": "Dwarka Sector 7",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110075",
        "country_code": "IN",
        "contact_phone": "9876543210",
        "pickup_instructions": "Ask at counter",
        "timezone": "Asia/Kolkata",
        "status": "draft",
        "created_at": "2026-10-31T00:00:00Z",
        "updated_at": "2026-10-31T00:00:00Z",
    }
    row.update(overrides)
    return row


def membership(merchant_id, user_id, role, is_active=True):
    return {
        "merchant_id": str(merchant_id),
        "user_id": str(user_id),
        "role": role,
        "is_active": is_active,
    }


def staff(store_id, user_id, role, is_active=True):
    return {
        "store_id": str(store_id),
        "user_id": str(user_id),
        "role": role,
        "is_active": is_active,
    }


class RecordingFake:
    """Fake Supabase client that respects eq/in filters and select."""

    def __init__(self, tables=None, rpc_returns=None, rpc_error=None):
        self.tables = tables or {}
        self.rpc_returns = rpc_returns or {}
        self.rpc_error = rpc_error
        self.rpc_calls = []
        self.query_calls = []

    def _matches(self, row, filters):
        if not filters:
            return True
        for key, value in filters.items():
            if key == "order":
                continue
            if isinstance(value, str) and value.startswith("eq."):
                actual = row.get(key)
                actual_str = (
                    str(actual).lower() if isinstance(actual, bool) else str(actual)
                )
                if actual_str != value[3:]:
                    return False
            elif isinstance(value, str) and value.startswith("in.("):
                wanted = value[4:-1].split(",") if value[4:-1] else []
                if str(row.get(key)) not in wanted:
                    return False
            elif value == "is.null":
                if row.get(key) is not None:
                    return False
        return True

    async def query(self, table, *, select="*", filters=None):
        self.query_calls.append((table, select, filters))
        rows = [r for r in self.tables.get(table, []) if self._matches(r, filters)]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]

    async def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        return self.rpc_returns.get(name)


def _client_with(fake):
    app = create_app(make_test_settings())

    async def _user():
        return USER

    def _client():
        return fake

    def _boom():
        raise AssertionError("service-role client must not be used here")

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_user_client] = _client
    app.dependency_overrides[get_service_client] = _boom
    return TestClient(app, raise_server_exceptions=False)


def _rpc_error(status, pg_code, message):
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/x")
    response = httpx.Response(
        status, json={"code": pg_code, "message": message}, request=request
    )
    return httpx.HTTPStatusError(message, request=request, response=response)


def _application_payload(**overrides):
    payload = {
        "legal_name": "Sharma Foods Pvt Ltd",
        "display_name": "Sharma Foods",
        "business_type": "restaurant",
        "business_email": "hello@sharma.example.com",
        "business_phone": "9876543210",
    }
    payload.update(overrides)
    return payload


def _store_payload(**overrides):
    payload = {
        "name": "Sharma Foods Dwarka",
        "slug": "sharma-foods-dwarka",
        "address_line_1": "Shop 12, Sector 7 Market",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110075",
        "latitude": 28.5921,
        "longitude": 77.0460,
    }
    payload.update(overrides)
    return payload


# --- Authentication ---


def test_unauthenticated_requests_rejected(client):
    assert (
        client.post(
            "/v1/merchants/applications", json=_application_payload()
        ).status_code
        == 401
    )
    assert client.get("/v1/merchants").status_code == 401
    assert client.get(f"/v1/merchants/{MERCHANT_ID}").status_code == 401
    assert client.get(f"/v1/merchants/{MERCHANT_ID}/stores").status_code == 401
    assert client.get(f"/v1/stores/{STORE_ID}/hours").status_code == 401
    assert (
        client.put(f"/v1/stores/{STORE_ID}/hours", json={"hours": []}).status_code
        == 401
    )


# --- Merchant applications ---


def test_application_success_and_exact_rpc_args():
    fake = RecordingFake(
        tables={"merchants": [merchant_row()]},
        rpc_returns={"apply_merchant_application": str(MERCHANT_ID)},
    )
    client = _client_with(fake)
    response = client.post("/v1/merchants/applications", json=_application_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == str(MERCHANT_ID)
    assert body["status"] == "pending_review"
    assert body["business_type"] == "restaurant"
    assert fake.rpc_calls == [
        (
            "apply_merchant_application",
            {
                "p_legal_name": "Sharma Foods Pvt Ltd",
                "p_display_name": "Sharma Foods",
                "p_business_type": "restaurant",
                "p_business_email": "hello@sharma.example.com",
                "p_business_phone": "9876543210",
            },
        )
    ]


def test_application_rejects_forbidden_body_fields():
    """user_id / role / status / reviewer_id in the body must not
    reach the RPC and must not appear in the response."""
    fake = RecordingFake(
        tables={"merchants": [merchant_row()]},
        rpc_returns={"apply_merchant_application": str(MERCHANT_ID)},
    )
    client = _client_with(fake)
    payload = _application_payload(
        user_id=str(OTHER_USER_ID),
        role="super_admin",
        status="approved",
        p_reviewer_id="attacker",
    )
    response = client.post("/v1/merchants/applications", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "pending_review"
    rpc_params = fake.rpc_calls[0][1]
    assert "p_reviewer_id" not in rpc_params
    assert set(rpc_params) == {
        "p_legal_name",
        "p_display_name",
        "p_business_type",
        "p_business_email",
        "p_business_phone",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"legal_name": "   "},
        {"display_name": ""},
        {"business_type": "spaceship"},
        {"business_email": "not-an-email"},
        {"business_email": "a@b"},
        {"business_phone": "12345"},
        {"business_phone": "1234567890"},
    ],
)
def test_application_validation(overrides):
    fake = RecordingFake()
    client = _client_with(fake)
    response = client.post(
        "/v1/merchants/applications", json=_application_payload(**overrides)
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert fake.rpc_calls == []


def test_application_optional_contact_fields():
    fake = RecordingFake(
        tables={"merchants": [merchant_row(business_email=None, business_phone=None)]},
        rpc_returns={"apply_merchant_application": str(MERCHANT_ID)},
    )
    client = _client_with(fake)
    payload = _application_payload()
    del payload["business_email"]
    del payload["business_phone"]
    response = client.post("/v1/merchants/applications", json=payload)
    assert response.status_code == 201, response.text
    assert fake.rpc_calls[0][1]["p_business_email"] is None
    assert fake.rpc_calls[0][1]["p_business_phone"] is None


def test_rpc_validation_error_maps_to_422_envelope():
    fake = RecordingFake(
        rpc_returns={},
        rpc_error=_rpc_error(400, "22023", "business_name_required"),
    )
    client = _client_with(fake)
    response = client.post("/v1/merchants/applications", json=_application_payload())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "business_name_required" in response.json()["error"]["message"]


# --- Merchant list / get / isolation ---


def test_list_merchants_only_active_own_memberships():
    fake = RecordingFake(
        tables={
            "merchant_memberships": [
                membership(MERCHANT_ID, USER_ID, "owner"),
                membership(
                    OTHER_MERCHANT_ID, USER_ID, "finance_viewer", is_active=False
                ),
                membership(OTHER_MERCHANT_ID, OTHER_USER_ID, "owner"),
            ],
            "merchants": [
                merchant_row(),
                merchant_row(OTHER_MERCHANT_ID, display_name="Other"),
            ],
        }
    )
    client = _client_with(fake)
    response = client.get("/v1/merchants")
    assert response.status_code == 200, response.text
    ids = [m["id"] for m in response.json()]
    assert ids == [str(MERCHANT_ID)]


def test_list_merchants_empty_when_no_membership():
    fake = RecordingFake(tables={"merchant_memberships": []})
    client = _client_with(fake)
    response = client.get("/v1/merchants")
    assert response.status_code == 200
    assert response.json() == []


def test_get_merchant_member_ok_nonmember_forbidden():
    fake = RecordingFake(
        tables={
            "merchant_memberships": [
                membership(MERCHANT_ID, USER_ID, "finance_viewer")
            ],
            "merchants": [merchant_row()],
        }
    )
    client = _client_with(fake)
    assert client.get(f"/v1/merchants/{MERCHANT_ID}").status_code == 200
    fake2 = RecordingFake(tables={"merchant_memberships": []})
    client2 = _client_with(fake2)
    response = client2.get(f"/v1/merchants/{MERCHANT_ID}")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_get_merchant_member_but_row_missing_is_404():
    fake = RecordingFake(
        tables={
            "merchant_memberships": [membership(MERCHANT_ID, USER_ID, "owner")],
            "merchants": [],
        }
    )
    client = _client_with(fake)
    assert client.get(f"/v1/merchants/{MERCHANT_ID}").status_code == 404


# --- Store creation ---


def test_store_create_owner_success_and_exact_rpc_args():
    fake = RecordingFake(
        tables={
            "merchant_memberships": [membership(MERCHANT_ID, USER_ID, "owner")],
            "stores": [store_row()],
        },
        rpc_returns={"create_merchant_store": str(STORE_ID)},
    )
    client = _client_with(fake)
    response = client.post(f"/v1/merchants/{MERCHANT_ID}/stores", json=_store_payload())
    assert response.status_code == 201, response.text
    assert response.json()["id"] == str(STORE_ID)
    assert response.json()["status"] == "draft"
    assert fake.rpc_calls == [
        (
            "create_merchant_store",
            {
                "p_merchant_id": str(MERCHANT_ID),
                "p_name": "Sharma Foods Dwarka",
                "p_slug": "sharma-foods-dwarka",
                "p_address_line_1": "Shop 12, Sector 7 Market",
                "p_address_line_2": None,
                "p_locality": None,
                "p_city": "New Delhi",
                "p_state": "Delhi",
                "p_pincode": "110075",
                "p_latitude": 28.5921,
                "p_longitude": 77.0460,
                "p_contact_phone": None,
                "p_pickup_instructions": None,
            },
        )
    ]


def test_store_create_admin_ok_viewer_and_nonmember_forbidden():
    for role, expected in [("admin", 201), ("finance_viewer", 403)]:
        fake = RecordingFake(
            tables={
                "merchant_memberships": [membership(MERCHANT_ID, USER_ID, role)],
                "stores": [store_row()],
            },
            rpc_returns={"create_merchant_store": str(STORE_ID)},
        )
        client = _client_with(fake)
        response = client.post(
            f"/v1/merchants/{MERCHANT_ID}/stores", json=_store_payload()
        )
        assert response.status_code == expected, (role, response.text)
    fake = RecordingFake(tables={"merchant_memberships": []})
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/merchants/{MERCHANT_ID}/stores", json=_store_payload()
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"pincode": "11007"},
        {"pincode": "011007"},
        {"pincode": "ABCDEF"},
        {"latitude": 28.5},
        {"longitude": 77.0},
        {"latitude": 91.0, "longitude": 77.0},
        {"latitude": 28.5, "longitude": 181.0},
        {"name": "   "},
        {"slug": "Bad Slug!"},
        {"slug": ""},
        {"address_line_1": ""},
    ],
)
def test_store_create_validation(overrides):
    fake = RecordingFake(
        tables={"merchant_memberships": [membership(MERCHANT_ID, USER_ID, "owner")]}
    )
    client = _client_with(fake)
    payload = _store_payload(**overrides)
    # The two single-coordinate cases must actually omit the other
    # coordinate; the default payload supplies both.
    if set(overrides) == {"latitude"}:
        del payload["longitude"]
    if set(overrides) == {"longitude"}:
        del payload["latitude"]
    response = client.post(f"/v1/merchants/{MERCHANT_ID}/stores", json=payload)
    assert response.status_code == 422, (overrides, response.text)
    assert fake.rpc_calls == []


def test_store_create_slug_lowercased_and_no_location_without_both():
    fake = RecordingFake(
        tables={
            "merchant_memberships": [membership(MERCHANT_ID, USER_ID, "owner")],
            "stores": [store_row()],
        },
        rpc_returns={"create_merchant_store": str(STORE_ID)},
    )
    client = _client_with(fake)
    payload = _store_payload(slug="Sharma-Foods-Dwarka")
    del payload["latitude"]
    del payload["longitude"]
    response = client.post(f"/v1/merchants/{MERCHANT_ID}/stores", json=payload)
    assert response.status_code == 201, response.text
    assert fake.rpc_calls[0][1]["p_slug"] == "sharma-foods-dwarka"
    assert fake.rpc_calls[0][1]["p_latitude"] is None
    assert fake.rpc_calls[0][1]["p_longitude"] is None


def test_store_list_isolation():
    fake = RecordingFake(
        tables={
            "merchant_memberships": [membership(MERCHANT_ID, USER_ID, "owner")],
            "stores": [store_row(), store_row(OTHER_STORE_ID, OTHER_MERCHANT_ID)],
        }
    )
    client = _client_with(fake)
    response = client.get(f"/v1/merchants/{MERCHANT_ID}/stores")
    assert response.status_code == 200
    assert [s["id"] for s in response.json()] == [str(STORE_ID)]
    fake2 = RecordingFake(tables={"merchant_memberships": []})
    assert (
        _client_with(fake2).get(f"/v1/merchants/{MERCHANT_ID}/stores").status_code
        == 403
    )


# --- Store hours ---


def _hours_tables(
    merchant_role="owner", store_role=None, merchant_active=True, store_active=True
):
    tables = {
        "stores": [store_row()],
        "merchant_memberships": [
            membership(MERCHANT_ID, USER_ID, merchant_role, is_active=merchant_active)
        ]
        if merchant_role
        else [],
        "store_staff_memberships": [
            staff(STORE_ID, USER_ID, store_role, is_active=store_active)
        ]
        if store_role
        else [],
        "store_hours": [
            {
                "store_id": str(STORE_ID),
                "weekday": 0,
                "opens_at": "09:00:00",
                "closes_at": "21:00:00",
                "is_closed": False,
            },
            {
                "store_id": str(STORE_ID),
                "weekday": 6,
                "opens_at": None,
                "closes_at": None,
                "is_closed": True,
            },
        ],
    }
    return tables


@pytest.mark.parametrize(
    "merchant_role,store_role,expected",
    [
        ("owner", None, 200),
        ("admin", None, 200),
        ("finance_viewer", "store_manager", 200),
        ("finance_viewer", None, 403),
        (None, "store_manager", 403),
        ("owner", "store_manager", 200),
    ],
)
def test_hours_get_authorisation(merchant_role, store_role, expected):
    fake = RecordingFake(tables=_hours_tables(merchant_role, store_role))
    client = _client_with(fake)
    response = client.get(f"/v1/stores/{STORE_ID}/hours")
    assert response.status_code == expected, (merchant_role, store_role, response.text)
    if expected == 200:
        body = response.json()
        assert body["store_id"] == str(STORE_ID)
        assert [h["weekday"] for h in body["hours"]] == [0, 6]


def test_hours_get_unknown_store_is_404():
    fake = RecordingFake(tables={"stores": []})
    client = _client_with(fake)
    assert client.get(f"/v1/stores/{STORE_ID}/hours").status_code == 404


def test_hours_put_owner_success_and_exact_rpc_args():
    fake = RecordingFake(
        tables=_hours_tables("owner"),
        rpc_returns={"upsert_store_hours": 2},
    )
    client = _client_with(fake)
    payload = {
        "hours": [
            {"weekday": 0, "opens_at": "09:00", "closes_at": "21:00"},
            {"weekday": 6, "is_closed": True},
        ]
    }
    response = client.put(f"/v1/stores/{STORE_ID}/hours", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["processed"] == 2
    assert fake.rpc_calls == [
        (
            "upsert_store_hours",
            {
                "p_store_id": str(STORE_ID),
                "p_hours": [
                    {
                        "weekday": 0,
                        "is_closed": False,
                        "opens_at": "09:00:00",
                        "closes_at": "21:00:00",
                    },
                    {
                        "weekday": 6,
                        "is_closed": True,
                        "opens_at": None,
                        "closes_at": None,
                    },
                ],
            },
        )
    ]


def test_hours_put_store_manager_ok_viewer_forbidden():
    fake = RecordingFake(
        tables=_hours_tables("finance_viewer", "store_manager"),
        rpc_returns={"upsert_store_hours": 1},
    )
    client = _client_with(fake)
    response = client.put(
        f"/v1/stores/{STORE_ID}/hours",
        json={"hours": [{"weekday": 1, "opens_at": "09:00", "closes_at": "18:00"}]},
    )
    assert response.status_code == 200, response.text
    fake2 = RecordingFake(tables=_hours_tables("finance_viewer", None))
    response2 = _client_with(fake2).put(
        f"/v1/stores/{STORE_ID}/hours",
        json={"hours": [{"weekday": 1, "opens_at": "09:00", "closes_at": "18:00"}]},
    )
    assert response2.status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"hours": []},
        {"hours": [{"weekday": 0, "opens_at": "09:00", "closes_at": "18:00"}] * 2},
        {
            "hours": [
                {"weekday": i, "opens_at": "09:00", "closes_at": "18:00"}
                for i in range(8)
            ]
        },
        {"hours": [{"weekday": 7, "opens_at": "09:00", "closes_at": "18:00"}]},
        {"hours": [{"weekday": -1, "opens_at": "09:00", "closes_at": "18:00"}]},
        {
            "hours": [
                {
                    "weekday": 0,
                    "is_closed": True,
                    "opens_at": "09:00",
                    "closes_at": "18:00",
                }
            ]
        },
        {"hours": [{"weekday": 0, "opens_at": "09:00"}]},
        {"hours": [{"weekday": 0, "opens_at": "18:00", "closes_at": "09:00"}]},
        {"hours": [{"weekday": 0, "opens_at": "09:00", "closes_at": "09:00"}]},
    ],
)
def test_hours_put_validation(payload):
    fake = RecordingFake(tables=_hours_tables("owner"))
    client = _client_with(fake)
    response = client.put(f"/v1/stores/{STORE_ID}/hours", json=payload)
    assert response.status_code == 422, (payload, response.text)
    assert fake.rpc_calls == []


def test_hours_put_rpc_access_denied_maps_to_403():
    fake = RecordingFake(
        tables=_hours_tables("owner"),
        rpc_error=_rpc_error(400, "42501", "store_access_denied"),
    )
    client = _client_with(fake)
    response = client.put(
        f"/v1/stores/{STORE_ID}/hours",
        json={"hours": [{"weekday": 1, "opens_at": "09:00", "closes_at": "18:00"}]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_service_role_client_never_used():
    """get_service_client is overridden to raise; every endpoint
    still succeeds, proving none of them depends on it."""
    fake = RecordingFake(
        tables={
            "merchant_memberships": [membership(MERCHANT_ID, USER_ID, "owner")],
            "merchants": [merchant_row()],
            "stores": [store_row()],
            "store_hours": [],
        },
        rpc_returns={
            "apply_merchant_application": str(MERCHANT_ID),
            "create_merchant_store": str(STORE_ID),
            "upsert_store_hours": 1,
        },
    )
    client = _client_with(fake)
    assert (
        client.post(
            "/v1/merchants/applications", json=_application_payload()
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/v1/merchants/{MERCHANT_ID}/stores", json=_store_payload()
        ).status_code
        == 201
    )
    assert (
        client.put(
            f"/v1/stores/{STORE_ID}/hours",
            json={"hours": [{"weekday": 1, "opens_at": "09:00", "closes_at": "18:00"}]},
        ).status_code
        == 200
    )
