"""Milestone 10 tests: merchant dashboard and analytics.

All Supabase access is faked with eq/in/gte filters.
No test touches live Supabase, uses the service-role
client, or queries a private table. Money is asserted
as exact Decimal strings, never floats.
"""

from uuid import UUID

from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_MERCHANT_ID = UUID("23232323-2323-4232-8232-232323232323")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
OTHER_STORE_ID = UUID("45454545-4545-4454-8454-454545454545")
ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")


def order_row(order_id=ORDER_ID, **overrides):
    row = {
        "id": str(order_id),
        "order_number": "SF-20261031-000001",
        "store_id": str(STORE_ID),
        "status": "collected",
        "payment_status": "captured",
        "total_amount": "390.00",
        "created_at": "2026-10-31T12:00:00+00:00",
        "pickup_starts_at": "2026-10-31T18:00:00+00:00",
        "pickup_ends_at": "2026-10-31T21:00:00+00:00",
        "collected_at": "2026-10-31T18:30:00+00:00",
    }
    row.update(overrides)
    return row


class DashboardFake:
    def __init__(self, tables):
        self.tables = tables
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
            elif isinstance(value, str) and value.startswith("gte."):
                if str(row.get(key)) < value[4:]:
                    return False
        return True

    async def query(self, table, *, select="*", filters=None):
        assert not table.startswith("private."), "private tables must not be queried"
        self.query_calls.append((table, select, filters))
        rows = [
            r for r in self.tables.get(table, []) if self._matches(r, filters or {})
        ]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]


def _tables(orders=None, listings=None, reviews=None, memberships=None):
    return {
        "merchant_memberships": memberships
        if memberships is not None
        else [
            {
                "merchant_id": str(MERCHANT_ID),
                "user_id": str(USER_ID),
                "role": "owner",
                "is_active": True,
            }
        ],
        "store_staff_memberships": [],
        "stores": [
            {
                "id": str(STORE_ID),
                "merchant_id": str(MERCHANT_ID),
                "name": "Sharma Foods Dwarka",
                "status": "active",
                "timezone": "Asia/Kolkata",
            },
            {
                "id": str(OTHER_STORE_ID),
                "merchant_id": str(OTHER_MERCHANT_ID),
                "name": "Other Shop",
                "status": "active",
                "timezone": "Asia/Kolkata",
            },
        ],
        "orders": orders
        if orders is not None
        else [
            order_row(),
            order_row(
                "56565656-5656-4565-8565-565656565656",
                order_number="SF-20261031-000002",
                status="pending_payment",
                payment_status="created",
                total_amount="195.00",
            ),
            order_row(
                "57575757-5757-4575-8575-575757575757",
                order_number="SF-20261031-000003",
                status="cancelled",
                payment_status="failed",
                total_amount="100.00",
            ),
        ],
        "listings": listings
        if listings is not None
        else [
            {
                "id": "77777777-7777-4777-8777-777777777771",
                "store_id": str(STORE_ID),
                "title": "Evening Bag",
                "status": "active",
                "total_quantity": 10,
                "reserved_quantity": 2,
                "sold_quantity": 3,
                "available_quantity": 5,
                "sale_ends_at": "2026-10-31T17:00:00+00:00",
            },
            {
                "id": "77777777-7777-4777-8777-777777777772",
                "store_id": str(STORE_ID),
                "title": "Draft Bag",
                "status": "draft",
                "total_quantity": 4,
                "reserved_quantity": 0,
                "sold_quantity": 0,
                "available_quantity": 4,
                "sale_ends_at": "2026-11-01T17:00:00+00:00",
            },
        ],
        "reviews": reviews
        if reviews is not None
        else [
            {"store_id": str(STORE_ID), "rating": 5, "moderation_status": "visible"},
            {"store_id": str(STORE_ID), "rating": 4, "moderation_status": "visible"},
            {"store_id": str(STORE_ID), "rating": 5, "moderation_status": "hidden"},
        ],
        "order_items": [
            {"order_id": str(ORDER_ID), "quantity": 2},
        ],
    }


def _client_with(fake, authenticated=True):
    app = create_app(make_test_settings())
    app.dependency_overrides[get_user_client] = lambda: fake
    if authenticated:
        user = AuthenticatedUser(id=USER_ID, email="user@example.com", token="tok")

        async def _user():
            return user

        app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


def test_overview_metrics():
    client = _client_with(DashboardFake(_tables()))
    response = client.get(f"/v1/merchant/dashboard?store_id={STORE_ID}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["store"]["store_name"] == "Sharma Foods Dwarka"
    # open_now is null: the weekday convention is
    # unverified, so it is reported unknown, not guessed.
    assert body["store"]["open_now"] is None
    orders = body["orders"]
    assert orders["total_orders"] == 3
    assert orders["paid_orders"] == 1
    assert orders["awaiting_payment_orders"] == 1
    assert orders["collected_orders"] == 1
    assert orders["cancelled_orders"] == 1
    # Only the captured order counts as captured value;
    # pending (195) and failed (100) never count.
    assert orders["captured_order_value"] == "390.00"
    assert orders["currency"] == "INR"
    inv = body["inventory"]
    assert inv["total_listings"] == 2
    assert inv["published_listings"] == 1
    assert inv["draft_listings"] == 1
    # Generated available_quantity is read, not recomputed:
    # 5 + 4 = 9, reserved 2, sold 3.
    assert inv["total_available_units"] == 9
    assert inv["total_reserved_units"] == 2
    assert inv["total_sold_units"] == 3
    ratings = body["ratings"]
    # Hidden review excluded from average and count.
    assert ratings["total_visible_reviews"] == 2
    assert ratings["average_rating"] == 4.5
    assert ratings["five_star"] == 1 and ratings["four_star"] == 1


def test_overview_unauthorized_store_404():
    client = _client_with(DashboardFake(_tables()))
    assert (
        client.get(f"/v1/merchant/dashboard?store_id={OTHER_STORE_ID}").status_code
        == 404
    )


def test_overview_unauthenticated_401():
    client = _client_with(DashboardFake(_tables()), authenticated=False)
    assert client.get("/v1/merchant/dashboard").status_code == 401


def test_overview_empty_store_zeros_and_null_rating():
    tables = _tables(orders=[], listings=[], reviews=[])
    client = _client_with(DashboardFake(tables))
    body = client.get(f"/v1/merchant/dashboard?store_id={STORE_ID}").json()
    assert body["orders"]["total_orders"] == 0
    assert body["orders"]["captured_order_value"] == "0.00"
    assert body["inventory"]["total_listings"] == 0
    assert body["ratings"]["average_rating"] is None
    assert body["ratings"]["total_visible_reviews"] == 0


def test_sales_grouping_and_boundaries():
    orders = [
        order_row(
            "56565656-5656-4565-8565-565656565656",
            created_at="2026-10-30T12:00:00+00:00",
        ),
        order_row(
            "57575757-5757-4575-8575-575757575757",
            created_at="2026-10-31T12:00:00+00:00",
        ),
        order_row(
            "58585858-5858-4585-8585-585858585858",
            created_at="2026-11-01T00:00:00+00:00",
            status="pending_payment",
            payment_status="created",
            total_amount="50.00",
        ),
    ]
    client = _client_with(DashboardFake(_tables(orders=orders)))
    body = client.get(
        "/v1/merchant/dashboard/sales?store_id="
        f"{STORE_ID}&from=2026-10-30T00:00:00Z&to=2026-11-01T00:00:00Z&group_by=day"
    ).json()
    # Half-open period: the 2026-11-01 order is excluded.
    assert body["totals"]["total_orders"] == 2
    assert body["totals"]["captured_order_value"] == "780.00"
    assert [b["period_start"] for b in body["buckets"]] == ["2026-10-30", "2026-10-31"]
    assert body["reporting_timezone"] == "Asia/Kolkata"
    week = client.get(
        f"/v1/merchant/dashboard/sales?store_id={STORE_ID}&group_by=week"
    ).json()
    assert week["group_by"] == "week"
    assert client.get("/v1/merchant/dashboard/sales?group_by=year").status_code == 422
    assert (
        client.get(
            "/v1/merchant/dashboard/sales?from=2026-11-02T00:00:00Z&to=2026-11-01T00:00:00Z"
        ).status_code
        == 422
    )


def test_sales_authorized_only_never_counts_captured_as_collected():
    orders = [
        order_row(status="confirmed", payment_status="captured", collected_at=None),
    ]
    client = _client_with(DashboardFake(_tables(orders=orders)))
    body = client.get(f"/v1/merchant/dashboard/sales?store_id={STORE_ID}").json()
    assert body["totals"]["captured_orders"] == 1
    assert body["totals"]["captured_order_value"] == "390.00"
    # Captured is not collected: fulfilment stays separate.
    assert body["totals"]["collected_orders"] == 0


def test_inventory_low_stock_threshold():
    client = _client_with(DashboardFake(_tables()))
    body = client.get(
        f"/v1/merchant/dashboard/inventory?store_id={STORE_ID}&low_stock_threshold=5"
    ).json()
    assert body["summary"]["total_available_units"] == 9
    assert [lst["title"] for lst in body["low_stock_listings"]] == [
        "Evening Bag",
        "Draft Bag",
    ]
    assert (
        client.get(
            "/v1/merchant/dashboard/inventory?low_stock_threshold=-1"
        ).status_code
        == 422
    )
    no_threshold = client.get(
        f"/v1/merchant/dashboard/inventory?store_id={STORE_ID}"
    ).json()
    assert no_threshold["low_stock_listings"] == []


def test_pickups_categories_and_unauthorized():
    # The collected order is completed; pending/cancelled
    # orders are not pickup orders at all.
    client = _client_with(DashboardFake(_tables()))
    body = client.get(f"/v1/merchant/dashboard/pickups?store_id={STORE_ID}").json()
    assert body["counts"]["completed_collections"] == 1
    assert len(body["orders"]) == 1
    assert body["orders"][0]["category"] == "completed"
    assert body["orders"][0]["total_quantity"] == 2
    assert (
        client.get(
            f"/v1/merchant/dashboard/pickups?store_id={OTHER_STORE_ID}"
        ).status_code
        == 404
    )
    assert (
        client.get("/v1/merchant/dashboard/pickups?category=bogus").status_code == 422
    )


def test_stores_comparison_only_authorized():
    client = _client_with(DashboardFake(_tables()))
    body = client.get("/v1/merchant/dashboard/stores").json()
    assert [s["store_name"] for s in body["stores"]] == ["Sharma Foods Dwarka"]
    row = body["stores"][0]
    assert row["total_orders"] == 3
    assert row["captured_order_value"] == "390.00"
    assert row["collected_orders"] == 1
    assert row["active_listings"] == 1
    assert row["available_units"] == 9
    assert row["average_rating"] == 4.5
    assert row["review_count"] == 2


def test_no_private_table_queries_and_no_mutation_routes():
    fake = DashboardFake(_tables())
    client = _client_with(fake)
    client.get("/v1/merchant/dashboard")
    client.get("/v1/merchant/dashboard/sales")
    client.get("/v1/merchant/dashboard/inventory")
    client.get("/v1/merchant/dashboard/pickups")
    client.get("/v1/merchant/dashboard/stores")
    assert all(not t.startswith("private.") for t, _s, _f in fake.query_calls)
    # Dashboard is read-only: POST/PUT/DELETE on its paths
    # are not routed.
    assert client.post("/v1/merchant/dashboard").status_code in (404, 405)
