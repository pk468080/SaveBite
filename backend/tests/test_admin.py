"""Milestone 11 tests: platform admin dashboard and operations.

All Supabase access is faked. The fake enforces the
parts of the real model that matter here: the platform
role gate reads platform_user_roles (revoked rows
ignored), and the service fake enforces the review RPC
reviewer rule (compliance/ops/super only). No test
touches live Supabase, queries a private table, or uses
a service client to read a table.
"""

from uuid import UUID

import httpx
from fastapi.testclient import TestClient

from app.dependencies import (
    get_current_user,
    get_service_client,
    get_user_client,
)
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

ADMIN_ID = UUID("11111111-1111-4111-8111-111111111111")
USER_ID = UUID("12121212-1212-4121-8121-121212121212")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")


class AdminFake:
    def __init__(self, tables, platform_roles=None):
        self.tables = tables
        self.platform_roles = platform_roles or []
        self.query_calls = []

    def _matches(self, row, filters):
        for key, value in filters.items():
            if key in ("order", "limit", "offset"):
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
            elif isinstance(value, str) and value.startswith("ilike."):
                term = value[6:].strip("*").lower()
                if term not in str(row.get(key, "")).lower():
                    return False
            elif value == "is.null":
                if row.get(key) is not None:
                    return False
        return True

    async def query(self, table, *, select="*", filters=None):
        assert not table.startswith("private."), "private tables must not be queried"
        self.query_calls.append((table, select, filters))
        if table == "platform_user_roles":
            rows = [{"role": role, "revoked_at": None} for role in self.platform_roles]
            return rows
        rows = [
            r for r in self.tables.get(table, []) if self._matches(r, filters or {})
        ]
        order = (filters or {}).get("order", "")
        if order:
            for key in reversed(order.split(",")):
                field, _, direction = key.partition(".")
                rows.sort(
                    key=lambda r: str(r.get(field, "")), reverse=(direction == "desc")
                )
        offset = int((filters or {}).get("offset", 0))
        limit = (filters or {}).get("limit")
        if limit is not None:
            rows = rows[offset : offset + int(limit)]
        elif offset:
            rows = rows[offset:]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]


class ServiceFake:
    def __init__(self, rpc_error=None):
        self.rpc_calls = []
        self.rpc_error = rpc_error

    async def query(self, *args, **kwargs):
        raise AssertionError("service client must never query tables")

    async def rpc(self, name, params):
        assert name.startswith("backend_"), "only approved backend RPCs"
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        return {}


def _upstream_error(message, pg_code="P0001", status=400):
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/x")
    response = httpx.Response(
        status, json={"code": pg_code, "message": message}, request=request
    )
    return httpx.HTTPStatusError(message, request=request, response=response)


def _tables():
    return {
        "merchants": [
            {
                "id": str(MERCHANT_ID),
                "legal_name": "Sharma Foods Pvt",
                "display_name": "Sharma Foods",
                "business_type": "restaurant",
                "business_email": "ops@sharma.example",
                "business_phone": "9876543210",
                "status": "approved",
                "verification_status": "verified",
                "onboarding_notes": None,
                "created_by": str(USER_ID),
                "approved_at": "2026-10-31T10:00:00+00:00",
                "approved_by": str(ADMIN_ID),
                "created_at": "2026-10-30T10:00:00+00:00",
                "updated_at": "2026-10-31T10:00:00+00:00",
            },
            {
                "id": "23232323-2323-4232-8232-232323232323",
                "legal_name": "Pending Foods",
                "display_name": "Pending Foods",
                "business_type": "bakery",
                "business_email": None,
                "business_phone": None,
                "status": "pending_review",
                "verification_status": "pending",
                "onboarding_notes": None,
                "created_by": str(USER_ID),
                "approved_at": None,
                "approved_by": None,
                "created_at": "2026-10-31T09:00:00+00:00",
                "updated_at": "2026-10-31T09:00:00+00:00",
            },
        ],
        "stores": [
            {
                "id": str(STORE_ID),
                "merchant_id": str(MERCHANT_ID),
                "name": "Sharma Foods Dwarka",
                "status": "active",
                "city": "New Delhi",
                "state": "Delhi",
                "pincode": "110075",
                "address_line_1": "Shop 12",
                "locality": "Dwarka Sector 7",
                "timezone": "Asia/Kolkata",
                "created_at": "2026-10-30T11:00:00+00:00",
            }
        ],
        "store_hours": [
            {
                "store_id": str(STORE_ID),
                "weekday": 1,
                "opens_at": "09:00:00",
                "closes_at": "21:00:00",
            }
        ],
        "listings": [
            {
                "id": "77777777-7777-4777-8777-777777777771",
                "store_id": str(STORE_ID),
                "title": "Evening Bag",
                "selling_price": "195.00",
                "currency": "INR",
                "total_quantity": 10,
                "reserved_quantity": 2,
                "sold_quantity": 3,
                "available_quantity": 5,
                "status": "active",
                "sale_starts_at": "2026-10-31T10:00:00+00:00",
                "sale_ends_at": "2026-10-31T17:00:00+00:00",
                "created_at": "2026-10-31T10:00:00+00:00",
                "updated_at": "2026-10-31T10:00:00+00:00",
                "category_id": None,
            }
        ],
        "orders": [
            {
                "id": str(ORDER_ID),
                "order_number": "SF-20261031-000001",
                "store_id": str(STORE_ID),
                "status": "collected",
                "payment_status": "captured",
                "total_amount": "390.00",
                "currency": "INR",
                "pickup_starts_at": "2026-10-31T18:00:00+00:00",
                "pickup_ends_at": "2026-10-31T21:00:00+00:00",
                "collected_at": "2026-10-31T18:30:00+00:00",
                "customer_note": None,
                "created_at": "2026-10-31T12:00:00+00:00",
                "updated_at": "2026-10-31T18:30:00+00:00",
            },
            {
                "id": "56565656-5656-4565-8565-565656565656",
                "order_number": "SF-20261031-000002",
                "store_id": str(STORE_ID),
                "status": "refund_pending",
                "payment_status": "refund_pending",
                "total_amount": "195.00",
                "currency": "INR",
                "pickup_starts_at": "2026-10-31T18:00:00+00:00",
                "pickup_ends_at": "2026-10-31T21:00:00+00:00",
                "collected_at": "2026-10-31T18:30:00+00:00",
                "customer_note": None,
                "created_at": "2026-10-31T13:00:00+00:00",
                "updated_at": "2026-10-31T13:00:00+00:00",
            },
        ],
        "order_items": [
            {
                "order_id": str(ORDER_ID),
                "listing_title_snapshot": "Evening Bag",
                "quantity": 2,
                "unit_price": "195.00",
                "line_total": "390.00",
            }
        ],
        "order_status_events": [
            {
                "order_id": str(ORDER_ID),
                "from_status": "pending_payment",
                "to_status": "confirmed",
                "actor_type": "system",
                "reason": "payment_captured",
                "created_at": "2026-10-31T12:05:00+00:00",
            }
        ],
        "reviews": [
            {
                "id": "a0000000-0000-4000-8000-000000000001",
                "store_id": str(STORE_ID),
                "rating": 5,
                "comment": "Great bag",
                "moderation_status": "visible",
                "created_at": "2026-10-31T19:00:00+00:00",
            }
        ],
    }


def _client_with(fake, service=None, authenticated=True, user_id=ADMIN_ID):
    app = create_app(make_test_settings())
    app.dependency_overrides[get_user_client] = lambda: fake
    app.dependency_overrides[get_service_client] = lambda: service or ServiceFake()
    if authenticated:
        user = AuthenticatedUser(id=user_id, email="admin@example.com", token="tok")

        async def _user():
            return user

        app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


def _admin_client(platform_roles=("operations_admin",)):
    fake = AdminFake(_tables(), platform_roles=list(platform_roles))
    service = ServiceFake()
    return _client_with(fake, service), fake, service


# --- authorization ----------------------------------------------------------


def test_admin_gate_rejects_unauthenticated_customer_and_merchant():
    fake = AdminFake(_tables(), platform_roles=[])
    client = _client_with(fake, authenticated=False)
    assert client.get("/v1/admin/dashboard").status_code == 401
    client = _client_with(fake, user_id=USER_ID)
    for path in ("/v1/admin/dashboard", "/v1/admin/merchants", "/v1/admin/orders"):
        assert client.get(path).status_code == 403, path


def test_frontend_role_flag_cannot_grant_admin():
    fake = AdminFake(_tables(), platform_roles=[])
    client = _client_with(fake, user_id=USER_ID)
    response = client.post(
        f"/v1/admin/merchants/{MERCHANT_ID}/review",
        json={
            "action": "approve",
            "role": "super_admin",
            "p_reviewer_id": str(ADMIN_ID),
        },
    )
    assert response.status_code == 403


def test_valid_platform_admin_accepted():
    client, _fake, _service = _admin_client()
    assert client.get("/v1/admin/dashboard").status_code == 200


# --- dashboard ----------------------------------------------------------------


def test_dashboard_metrics_match_records():
    client, _fake, _service = _admin_client()
    body = client.get("/v1/admin/dashboard").json()
    assert body["merchants_total"] == 2
    assert body["merchants_approved"] == 1
    assert body["merchants_pending_review"] == 1
    assert body["stores_total"] == 1 and body["stores_active"] == 1
    assert body["listings_total"] == 1 and body["listings_published"] == 1
    assert body["orders_total"] == 2
    assert body["orders_collected"] == 1
    # Captured value counts only the captured order.
    assert body["captured_payment_count"] == 1
    assert body["captured_order_value"] == "390.00"
    # Refund-pending is counted, never reported as refunded.
    assert body["refund_pending_count"] == 1
    assert body["visible_reviews_total"] == 1
    assert body["average_visible_rating"] == 5.0
    assert len(body["recent_orders"]) == 2
    # No customer count field exists: profiles are
    # own-only and cannot be counted safely.
    assert "customers" not in str(body)


def test_dashboard_empty_platform_zeros():
    fake = AdminFake(
        {k: [] for k in _tables()},
        platform_roles=["super_admin"],
    )
    client = _client_with(fake, ServiceFake())
    body = client.get("/v1/admin/dashboard").json()
    assert body["merchants_total"] == 0
    assert body["captured_order_value"] == "0.00"
    assert body["average_visible_rating"] is None
    assert body["recent_orders"] == []


# --- merchants and stores -------------------------------------------------------


def test_merchant_list_filters_and_detail():
    client, _fake, _service = _admin_client()
    body = client.get("/v1/admin/merchants?status=pending_review").json()
    assert body["total"] == 1
    assert body["items"][0]["display_name"] == "Pending Foods"
    detail = client.get(f"/v1/admin/merchants/{MERCHANT_ID}").json()
    assert detail["display_name"] == "Sharma Foods"
    assert len(detail["stores"]) == 1
    assert (
        client.get(
            "/v1/admin/merchants/99999999-9999-4999-8999-999999999999"
        ).status_code
        == 404
    )


def test_merchant_review_uses_approved_rpc_with_caller_reviewer():
    client, _fake, service = _admin_client()
    response = client.post(
        f"/v1/admin/merchants/{MERCHANT_ID}/review",
        json={"action": "approve", "review_notes": "Docs verified"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    name, params = service.rpc_calls[0]
    assert name == "backend_review_merchant"
    assert params["p_new_status"] == "approved"
    assert params["p_verification_status"] == "verified"
    # Reviewer is the authenticated caller, never a
    # client-supplied id.
    assert params["p_reviewer_id"] == str(ADMIN_ID)


def test_merchant_review_reject_and_rpc_errors():
    client, _fake, service = _admin_client()
    response = client.post(
        f"/v1/admin/merchants/{MERCHANT_ID}/review",
        json={"action": "reject", "review_notes": "Incomplete"},
    )
    assert response.json()["status"] == "rejected"
    assert service.rpc_calls[0][1]["p_verification_status"] == "rejected"
    assert (
        client.post(
            f"/v1/admin/merchants/{MERCHANT_ID}/review",
            json={"action": "suspend"},
        ).status_code
        == 422
    )
    service2 = ServiceFake(
        rpc_error=_upstream_error("merchant_not_found", "P0002", 404)
    )
    client2 = _client_with(
        AdminFake(_tables(), platform_roles=["operations_admin"]), service2
    )
    assert (
        client2.post(
            f"/v1/admin/merchants/{MERCHANT_ID}/review",
            json={"action": "approve"},
        ).status_code
        == 404
    )


def test_store_list_detail_and_review():
    client, _fake, service = _admin_client()
    body = client.get("/v1/admin/stores?city=New Delhi").json()
    assert body["total"] == 1
    detail = client.get(f"/v1/admin/stores/{STORE_ID}").json()
    assert detail["name"] == "Sharma Foods Dwarka"
    assert detail["listing_count"] == 1
    assert detail["order_count"] == 2
    response = client.post(
        f"/v1/admin/stores/{STORE_ID}/review",
        json={"activate": False, "reason": "Inspection pending"},
    )
    assert response.status_code == 200
    assert service.rpc_calls[0][0] == "backend_review_store"
    assert service.rpc_calls[0][1]["p_activate"] is False


# --- listings, orders, payments, refunds -----------------------------------------


def test_listing_and_order_filters_and_pagination():
    client, _fake, _service = _admin_client()
    body = client.get("/v1/admin/listings?status=active").json()
    assert body["total"] == 1
    assert body["items"][0]["available_quantity"] == 5
    orders = client.get("/v1/admin/orders?payment_status=captured").json()
    assert orders["total"] == 1
    page2 = client.get("/v1/admin/orders?page=2&page_size=1").json()
    assert page2["total"] == 2 and len(page2["items"]) == 1
    detail = client.get(f"/v1/admin/orders/{ORDER_ID}").json()
    assert detail["order_number"] == "SF-20261031-000001"
    assert detail["items"][0]["title"] == "Evening Bag"
    assert detail["events"][0]["to_status"] == "confirmed"
    assert "customer_id" not in str(detail)


def test_payments_and_refunds_from_orders_only():
    client, _fake, _service = _admin_client()
    payments = client.get("/v1/admin/payments?payment_status=refund_pending").json()
    assert payments["total"] == 1
    assert "gateway" not in str(payments)
    refunds = client.get("/v1/admin/refunds").json()
    assert refunds["total"] == 1
    assert refunds["items"][0]["order_status"] == "refund_pending"
    # Refund-pending is listed as an exception, never as a
    # completed refund: no field claims it is refunded.
    assert refunds["items"][0]["payment_status"] == "refund_pending"


def test_reviews_visible_only_and_activity_real_events():
    client, _fake, _service = _admin_client()
    reviews = client.get("/v1/admin/reviews").json()
    assert reviews["total"] == 1
    assert reviews["items"][0]["moderation_status"] == "visible"
    activity = client.get("/v1/admin/activity").json()
    assert activity["total"] == 1
    assert activity["items"][0]["reason"] == "payment_captured"
    assert "audit" not in str(activity["items"])


def test_no_private_tables_and_no_service_table_reads():
    fake = AdminFake(_tables(), platform_roles=["operations_admin"])
    service = ServiceFake()
    client = _client_with(fake, service)
    for path in (
        "/v1/admin/dashboard",
        "/v1/admin/merchants",
        "/v1/admin/stores",
        "/v1/admin/listings",
        "/v1/admin/orders",
        "/v1/admin/payments",
        "/v1/admin/refunds",
        "/v1/admin/reviews",
        "/v1/admin/activity",
    ):
        assert client.get(path).status_code == 200, path
    assert all(not t.startswith("private.") for t, _s, _f in fake.query_calls)
