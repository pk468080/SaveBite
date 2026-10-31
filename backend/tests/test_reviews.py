"""Milestone 9 tests: reviews and ratings.

All Supabase access is faked. The fake enforces the
database rules that matter here: one review per order
(UNIQUE order_id) and, for the insert path, the
collected-order RLS check. No test touches live
Supabase, uses the service-role client, or queries a
private table.
"""

from uuid import UUID

import httpx
from fastapi.testclient import TestClient

from app.dependencies import get_anon_client, get_current_user, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

CUSTOMER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_CUSTOMER_ID = UUID("12121212-1212-4121-8121-121212121212")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")
ORDER_B_ID = UUID("56565656-5656-4565-8565-565656565656")


def order_row(order_id=ORDER_ID, **overrides):
    row = {
        "id": str(order_id),
        "order_number": "SF-20261031-000001",
        "customer_id": str(CUSTOMER_ID),
        "store_id": str(STORE_ID),
        "merchant_id": str(MERCHANT_ID),
        "status": "collected",
    }
    row.update(overrides)
    return row


def review_row(review_id="a0000000-0000-4000-8000-000000000001", **overrides):
    row = {
        "id": review_id,
        "order_id": str(ORDER_ID),
        "customer_id": str(CUSTOMER_ID),
        "store_id": str(STORE_ID),
        "merchant_id": str(MERCHANT_ID),
        "rating": 5,
        "comment": "Great bag, fresh items",
        "moderation_status": "visible",
        "created_at": "2026-10-31T19:00:00+00:00",
    }
    row.update(overrides)
    return row


class ReviewsFake:
    def __init__(self, tables=None):
        self.tables = tables or {}
        self.insert_calls = []
        self.query_calls = []

    def _matches(self, row, filters):
        for key, value in filters.items():
            if isinstance(value, str) and value.startswith("eq."):
                if str(row.get(key)) != value[3:]:
                    return False
        return True

    async def query(self, table, *, select="*", filters=None):
        assert not table.startswith("private."), "private tables must not be queried"
        self.query_calls.append((table, select, filters))
        rows = [
            r for r in self.tables.get(table, []) if self._matches(r, filters or {})
        ]
        # Anonymous readers see visible reviews only, like
        # the real SELECT policy.
        if table == "reviews" and getattr(self, "is_anon", False):
            rows = [r for r in rows if r["moderation_status"] == "visible"]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]

    async def insert(self, table, row):
        assert not table.startswith("private."), "private tables must not be written"
        self.insert_calls.append((table, row))
        existing = self.tables.setdefault(table, [])
        if any(r["order_id"] == row["order_id"] for r in existing):
            request = httpx.Request(
                "POST", "https://example.supabase.co/rest/v1/reviews"
            )
            response = httpx.Response(
                409,
                json={"code": "23505", "message": "duplicate key value"},
                request=request,
            )
            raise httpx.HTTPStatusError("duplicate", request=request, response=response)
        orders = {o["id"]: o for o in self.tables.get("orders", [])}
        order = orders.get(row["order_id"])
        if (
            order is None
            or order["customer_id"] != row["customer_id"]
            or order["store_id"] != row["store_id"]
            or order["merchant_id"] != row["merchant_id"]
            or order["status"] != "collected"
        ):
            request = httpx.Request(
                "POST", "https://example.supabase.co/rest/v1/reviews"
            )
            response = httpx.Response(
                403,
                json={
                    "code": "42501",
                    "message": "new row violates row-level security policy",
                },
                request=request,
            )
            raise httpx.HTTPStatusError("rls", request=request, response=response)
        created = {
            "id": "a0000000-0000-4000-8000-000000000099",
            **row,
            "moderation_status": "visible",
            "created_at": "2026-10-31T20:00:00+00:00",
        }
        existing.append(created)
        return [created]


def _tables(orders=None, reviews=None):
    return {
        "orders": orders if orders is not None else [order_row()],
        "stores": [{"id": str(STORE_ID), "name": "Sharma Foods Dwarka"}],
        "reviews": reviews if reviews is not None else [],
    }


def _client_with(fake, authenticated=True, anon=False):
    app = create_app(make_test_settings())
    app.dependency_overrides[get_user_client] = lambda: fake
    fake.is_anon = anon
    app.dependency_overrides[get_anon_client] = lambda: fake
    if authenticated:
        user = AuthenticatedUser(id=CUSTOMER_ID, email="user@example.com", token="tok")

        async def _user():
            return user

        app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


# --- submission -----------------------------------------------------------


def test_submit_collected_order_success():
    fake = ReviewsFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        f"/v1/orders/{ORDER_ID}/review", json={"rating": 5, "comment": "Great bag"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_number"] == "SF-20261031-000001"
    assert body["store_name"] == "Sharma Foods Dwarka"
    assert body["rating"] == 5
    assert body["moderation_status"] == "visible"
    assert "customer_id" not in body
    table, row = fake.insert_calls[0]
    assert table == "reviews"
    # Store/merchant/customer come from the order, never
    # from the request body (which carries only rating).
    assert row["store_id"] == str(STORE_ID)
    assert row["merchant_id"] == str(MERCHANT_ID)
    assert row["customer_id"] == str(CUSTOMER_ID)


def test_submit_requires_authentication():
    client = _client_with(ReviewsFake(tables=_tables()), authenticated=False)
    assert (
        client.post(f"/v1/orders/{ORDER_ID}/review", json={"rating": 5}).status_code
        == 401
    )


def test_submit_other_customer_order_404():
    tables = _tables(orders=[order_row(customer_id=OTHER_CUSTOMER_ID)])
    fake = ReviewsFake(tables=tables)
    client = _client_with(fake)
    assert (
        client.post(f"/v1/orders/{ORDER_ID}/review", json={"rating": 5}).status_code
        == 404
    )
    assert fake.insert_calls == []


def test_submit_uncollected_orders_rejected():
    for status in (
        "pending_payment",
        "confirmed",
        "ready_for_pickup",
        "expired",
        "cancelled",
        "refund_pending",
    ):
        fake = ReviewsFake(tables=_tables(orders=[order_row(status=status)]))
        client = _client_with(fake)
        response = client.post(f"/v1/orders/{ORDER_ID}/review", json={"rating": 5})
        assert response.status_code == 422, status
        assert fake.insert_calls == []


def test_submit_rating_validation():
    fake = ReviewsFake(tables=_tables())
    client = _client_with(fake)
    for bad in (0, 6, 4.5, "five"):
        response = client.post(f"/v1/orders/{ORDER_ID}/review", json={"rating": bad})
        assert response.status_code == 422, bad
    assert fake.insert_calls == []


def test_submit_comment_limits_and_whitespace():
    fake = ReviewsFake(tables=_tables())
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/orders/{ORDER_ID}/review", json={"rating": 4, "comment": "x" * 1001}
        ).status_code
        == 422
    )
    response = client.post(
        f"/v1/orders/{ORDER_ID}/review", json={"rating": 4, "comment": "   "}
    )
    assert response.status_code == 200
    assert response.json()["comment"] is None


def test_submit_duplicate_rejected_and_no_second_review():
    fake = ReviewsFake(tables=_tables(reviews=[review_row()]))
    client = _client_with(fake)
    response = client.post(f"/v1/orders/{ORDER_ID}/review", json={"rating": 1})
    assert response.status_code == 409
    assert len(fake.tables["reviews"]) == 1
    assert fake.tables["reviews"][0]["rating"] == 5


def test_submit_client_supplied_store_ignored():
    fake = ReviewsFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        f"/v1/orders/{ORDER_ID}/review",
        json={
            "rating": 5,
            "store_id": "99999999-9999-4999-8999-999999999999",
            "customer_id": str(OTHER_CUSTOMER_ID),
            "status": "collected",
        },
    )
    assert response.status_code == 200, response.text
    _table, row = fake.insert_calls[0]
    assert row["store_id"] == str(STORE_ID)
    assert row["customer_id"] == str(CUSTOMER_ID)


# --- customer history -------------------------------------------------------


def test_my_reviews_only_own_and_pagination():
    reviews = [
        review_row(
            "a0000000-0000-4000-8000-000000000001",
            created_at="2026-10-31T19:00:00+00:00",
        ),
        review_row(
            "a0000000-0000-4000-8000-000000000002",
            order_id=str(ORDER_B_ID),
            rating=3,
            created_at="2026-10-30T19:00:00+00:00",
        ),
        review_row(
            "a0000000-0000-4000-8000-000000000003",
            customer_id=OTHER_CUSTOMER_ID,
            created_at="2026-10-29T19:00:00+00:00",
        ),
    ]
    tables = _tables(reviews=reviews)
    tables["orders"].append(order_row(ORDER_B_ID, order_number="SF-20261031-000002"))
    fake = ReviewsFake(tables=tables)
    client = _client_with(fake)
    body = client.get("/v1/my/reviews").json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [
        "a0000000-0000-4000-8000-000000000001",
        "a0000000-0000-4000-8000-000000000002",
    ]
    assert "customer_id" not in body["items"][0]
    assert client.get("/v1/my/reviews?rating=3").json()["total"] == 1
    page2 = client.get("/v1/my/reviews?page=2&page_size=1").json()
    assert [i["id"] for i in page2["items"]] == ["a0000000-0000-4000-8000-000000000002"]
    assert client.get("/v1/my/reviews?page_size=101").status_code == 422


def test_my_reviews_empty():
    client = _client_with(ReviewsFake(tables=_tables()))
    body = client.get("/v1/my/reviews").json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_my_reviews_include_own_hidden():
    reviews = [review_row(moderation_status="hidden")]
    fake = ReviewsFake(tables=_tables(reviews=reviews))
    client = _client_with(fake)
    body = client.get("/v1/my/reviews").json()
    assert body["total"] == 1
    assert body["items"][0]["moderation_status"] == "hidden"


# --- public reviews ---------------------------------------------------------


def test_public_reviews_visible_only_and_sorts():
    reviews = [
        review_row(
            "a0000000-0000-4000-8000-000000000001",
            rating=5,
            created_at="2026-10-31T19:00:00+00:00",
        ),
        review_row(
            "a0000000-0000-4000-8000-000000000002",
            rating=2,
            created_at="2026-10-30T19:00:00+00:00",
        ),
        review_row(
            "a0000000-0000-4000-8000-000000000003",
            rating=4,
            moderation_status="hidden",
            created_at="2026-10-29T19:00:00+00:00",
        ),
        review_row(
            "a0000000-0000-4000-8000-000000000004",
            rating=3,
            moderation_status="under_review",
            created_at="2026-10-28T19:00:00+00:00",
        ),
    ]
    fake = ReviewsFake(tables=_tables(reviews=reviews))
    client = _client_with(fake, authenticated=False, anon=True)
    body = client.get(f"/v1/stores/{STORE_ID}/reviews").json()
    assert body["total"] == 2
    assert [i["rating"] for i in body["items"]] == [5, 2]
    assert (
        client.get(f"/v1/stores/{STORE_ID}/reviews?sort=lowest").json()["items"][0][
            "rating"
        ]
        == 2
    )
    assert client.get(f"/v1/stores/{STORE_ID}/reviews?rating=5").json()["total"] == 1
    assert "customer_id" not in str(body["items"])
    assert "user@example.com" not in str(body["items"])
    assert "SF-20261031" not in str(body["items"])


def test_public_reviews_empty_and_missing_store():
    fake = ReviewsFake(tables=_tables())
    client = _client_with(fake, authenticated=False, anon=True)
    body = client.get(f"/v1/stores/{STORE_ID}/reviews").json()
    assert body["total"] == 0 and body["items"] == []
    assert (
        client.get(
            "/v1/stores/99999999-9999-4999-8999-999999999999/reviews"
        ).status_code
        == 404
    )


# --- rating summary -----------------------------------------------------------


def test_rating_summary_correct_and_consistent():
    reviews = [
        review_row("a0000000-0000-4000-8000-000000000001", rating=5),
        review_row("a0000000-0000-4000-8000-000000000002", rating=5),
        review_row("a0000000-0000-4000-8000-000000000003", rating=4),
        review_row("a0000000-0000-4000-8000-000000000004", rating=1),
        review_row(
            "a0000000-0000-4000-8000-000000000005", rating=5, moderation_status="hidden"
        ),
    ]
    fake = ReviewsFake(tables=_tables(reviews=reviews))
    client = _client_with(fake, authenticated=False, anon=True)
    body = client.get(f"/v1/stores/{STORE_ID}/rating-summary").json()
    # Hidden review excluded, same rule as the public list.
    assert body["total_reviews"] == 4
    assert body["five_star"] == 2
    assert body["four_star"] == 1
    assert body["three_star"] == 0
    assert body["two_star"] == 0
    assert body["one_star"] == 1
    assert body["average_rating"] == 3.75


def test_rating_summary_zero_reviews():
    fake = ReviewsFake(tables=_tables())
    client = _client_with(fake, authenticated=False, anon=True)
    body = client.get(f"/v1/stores/{STORE_ID}/rating-summary").json()
    assert body["average_rating"] is None
    assert body["total_reviews"] == 0
    assert body["five_star"] == 0 and body["one_star"] == 0


def test_no_private_table_access():
    fake = ReviewsFake(tables=_tables(reviews=[review_row()]))
    client = _client_with(fake)
    client.post(f"/v1/orders/{ORDER_ID}/review", json={"rating": 5})
    client.get("/v1/my/reviews")
    client.get(f"/v1/stores/{STORE_ID}/reviews")
    client.get(f"/v1/stores/{STORE_ID}/rating-summary")
    assert all(not t.startswith("private.") for t, _s, _f in fake.query_calls)
