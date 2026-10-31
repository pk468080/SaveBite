"""Milestone 7 tests: customer and merchant order management.

All Supabase access is faked with a query implementation
that honours eq/in/gte/lte/ilike filters and select
projections. No test touches live Supabase, uses the
service-role client, or queries a private table: the fake
has no service client at all, and any private-table query
would raise.
"""

from uuid import UUID

from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

CUSTOMER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_CUSTOMER_ID = UUID("12121212-1212-4121-8121-121212121212")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_MERCHANT_ID = UUID("23232323-2323-4232-8232-232323232323")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
OTHER_STORE_ID = UUID("45454545-4545-4454-8454-454545454545")
ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")
ORDER_B_ID = UUID("56565656-5656-4565-8565-565656565656")
ORDER_C_ID = UUID("57575757-5757-4575-8575-575757575757")
LISTING_ID = UUID("77777777-7777-4777-8777-777777777777")


def order_row(order_id=ORDER_ID, **overrides):
    row = {
        "id": str(order_id),
        "order_number": "SF-20261031-000001",
        "customer_id": str(CUSTOMER_ID),
        "merchant_id": str(MERCHANT_ID),
        "store_id": str(STORE_ID),
        "status": "confirmed",
        "payment_status": "captured",
        "currency": "INR",
        "subtotal_amount": "390.00",
        "discount_amount": "0.00",
        "platform_fee_amount": "0.00",
        "tax_amount": "0.00",
        "total_amount": "390.00",
        "pickup_starts_at": "2026-10-31T18:00:00+00:00",
        "pickup_ends_at": "2026-10-31T21:00:00+00:00",
        "customer_note": "Please pack separately",
        "cancellation_reason": None,
        "confirmed_at": "2026-10-31T12:05:00+00:00",
        "collected_at": None,
        "cancelled_at": None,
        "created_at": "2026-10-31T12:00:00+00:00",
        "updated_at": "2026-10-31T12:05:00+00:00",
        "request_idempotency_key": "secret-key-do-not-expose",
        "request_hash": "secret-hash-do-not-expose",
    }
    row.update(overrides)
    return row


def store_row(store_id=STORE_ID, merchant_id=MERCHANT_ID):
    return {
        "id": str(store_id),
        "merchant_id": str(merchant_id),
        "name": "Sharma Foods Dwarka",
        "address_line_1": "Shop 12, Main Market",
        "address_line_2": None,
        "locality": "Dwarka Sector 7",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110075",
        "contact_phone": "9876543210",
        "pickup_instructions": "Collect from counter",
    }


def item_row(order_id=ORDER_ID, **overrides):
    row = {
        "id": "item-1",
        "order_id": str(order_id),
        "listing_id": str(LISTING_ID),
        "listing_type": "surprise_bag",
        "listing_title_snapshot": "Evening Surprise Bag",
        "listing_description_snapshot": "Assorted bakery items",
        "allergen_codes_snapshot": ["gluten"],
        "dietary_classification_snapshot": "vegetarian",
        "quantity": 2,
        "unit_price": "195.00",
        "reference_value_snapshot": "300.00",
        "line_total": "390.00",
        "created_at": "2026-10-31T12:00:00+00:00",
    }
    row.update(overrides)
    return row


class OrdersFake:
    def __init__(self, tables):
        self.tables = tables
        self.query_calls = []

    def _matches(self, row, filters):
        if not filters:
            return True
        for key, value in filters.items():
            if key in ("order", "limit", "offset"):
                continue
            actual = row.get(key)
            if isinstance(value, str) and value.startswith("eq."):
                actual_str = (
                    str(actual).lower() if isinstance(actual, bool) else str(actual)
                )
                if actual_str != value[3:]:
                    return False
            elif isinstance(value, str) and value.startswith("in.("):
                wanted = value[4:-1].split(",") if value[4:-1] else []
                if str(actual) not in wanted:
                    return False
            elif isinstance(value, str) and value.startswith("gte."):
                if str(actual) < value[4:]:
                    return False
            elif isinstance(value, str) and value.startswith("lte."):
                if str(actual) > value[4:]:
                    return False
            elif isinstance(value, str) and value.startswith("ilike."):
                term = value[6:].strip("*").lower()
                if term not in str(actual).lower():
                    return False
        return True

    async def query(self, table, *, select="*", filters=None):
        assert not table.startswith("private."), "private tables must not be queried"
        self.query_calls.append((table, select, filters))
        rows = [r for r in self.tables.get(table, []) if self._matches(r, filters)]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]


def _tables(orders=None):
    return {
        "orders": orders if orders is not None else [order_row()],
        "order_items": [item_row()],
        "order_status_events": [
            {
                "id": "evt-1",
                "order_id": str(ORDER_ID),
                "from_status": None,
                "to_status": "pending_payment",
                "actor_type": "customer",
                "actor_user_id": str(CUSTOMER_ID),
                "reason": "reservation_created",
                "created_at": "2026-10-31T12:00:00+00:00",
            },
            {
                "id": "evt-2",
                "order_id": str(ORDER_ID),
                "from_status": "pending_payment",
                "to_status": "confirmed",
                "actor_type": "system",
                "actor_user_id": None,
                "reason": "payment_captured",
                "created_at": "2026-10-31T12:05:00+00:00",
            },
        ],
        "inventory_reservations": [],
        "stores": [store_row(), store_row(OTHER_STORE_ID, OTHER_MERCHANT_ID)],
        "merchant_memberships": [
            {
                "merchant_id": str(MERCHANT_ID),
                "user_id": str(CUSTOMER_ID),
                "role": "owner",
                "is_active": True,
            }
        ],
        "store_staff_memberships": [],
        "listing_images": [
            {
                "listing_id": str(LISTING_ID),
                "storage_path": f"{LISTING_ID}/bag.jpg",
                "display_order": 0,
            },
            {
                "listing_id": str(LISTING_ID),
                "storage_path": "https://evil.example.com/bag.jpg",
                "display_order": 1,
            },
        ],
    }


def _client_with(fake, user_id=CUSTOMER_ID, authenticated=True):
    app = create_app(make_test_settings())
    app.dependency_overrides[get_user_client] = lambda: fake
    if authenticated:
        user = AuthenticatedUser(id=user_id, email="user@example.com", token="tok")

        async def _user():
            return user

        app.dependency_overrides[get_current_user] = _user
    return TestClient(app, raise_server_exceptions=False)


# --- customer history -----------------------------------------------------


def test_customer_sees_own_orders_only():
    orders = [
        order_row(),
        order_row(
            ORDER_B_ID, customer_id=OTHER_CUSTOMER_ID, order_number="SF-20261031-000002"
        ),
    ]
    client = _client_with(OrdersFake(_tables(orders=orders)))
    body = client.get("/v1/orders").json()
    assert body["total"] == 1
    assert body["items"][0]["order_number"] == "SF-20261031-000001"
    assert body["items"][0]["item_count"] == 1
    assert body["items"][0]["items_preview"][0]["title"] == "Evening Surprise Bag"
    assert "customer_id" not in body["items"][0]
    assert "request_hash" not in body["items"][0]


def test_customer_no_orders_empty():
    client = _client_with(OrdersFake(_tables(orders=[])))
    body = client.get("/v1/orders").json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 20}


def test_customer_filters_and_pagination():
    orders = [
        order_row(ORDER_ID, created_at="2026-10-31T12:00:00+00:00"),
        order_row(
            ORDER_B_ID,
            order_number="SF-20261031-000002",
            status="pending_payment",
            payment_status="created",
            created_at="2026-10-30T12:00:00+00:00",
        ),
        order_row(
            ORDER_C_ID,
            order_number="SF-20261031-000003",
            status="cancelled",
            payment_status="failed",
            created_at="2026-10-29T12:00:00+00:00",
        ),
    ]
    client = _client_with(OrdersFake(_tables(orders=orders)))
    assert client.get("/v1/orders?status=pending_payment").json()["total"] == 1
    assert client.get("/v1/orders?payment_status=captured").json()["total"] == 1
    assert (
        client.get("/v1/orders?created_from=2026-10-30T00:00:00Z").json()["total"] == 2
    )
    assert (
        client.get(
            "/v1/orders?created_from=2026-10-30T00:00:00Z&created_to=2026-10-30T23:59:59Z"
        ).json()["total"]
        == 1
    )
    page1 = client.get("/v1/orders?page=1&page_size=2").json()
    page2 = client.get("/v1/orders?page=2&page_size=2").json()
    assert [i["order_number"] for i in page1["items"]] == [
        "SF-20261031-000001",
        "SF-20261031-000002",
    ]
    assert [i["order_number"] for i in page2["items"]] == ["SF-20261031-000003"]
    assert client.get("/v1/orders?page=0").status_code == 422
    assert client.get("/v1/orders?page_size=101").status_code == 422
    assert client.get("/v1/orders?status=bogus").status_code == 422


def test_customer_unauthenticated_rejected():
    client = _client_with(OrdersFake(_tables()), authenticated=False)
    assert client.get("/v1/orders").status_code == 401
    assert client.get(f"/v1/orders/{ORDER_ID}").status_code == 401


# --- customer detail ------------------------------------------------------


def test_customer_detail_complete():
    client = _client_with(OrdersFake(_tables()))
    response = client.get(f"/v1/orders/{ORDER_ID}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["order_number"] == "SF-20261031-000001"
    assert body["status"] == "confirmed"
    assert body["payment"]["status"] == "captured"
    assert body["payment"]["amount_paid"] == "390.00"
    assert body["payment"]["gateway_label"] == "Razorpay"
    assert body["store"]["name"] == "Sharma Foods Dwarka"
    assert body["store"]["address_line_1"] == "Shop 12, Main Market"
    assert body["pickup_starts_at"] == "2026-10-31T18:00:00Z"
    assert body["items"][0]["title"] == "Evening Surprise Bag"
    assert body["items"][0]["quantity"] == 2
    assert body["items"][0]["line_total"] == "390.00"
    assert body["items"][0]["image_path"] == f"{LISTING_ID}/bag.jpg"
    assert [e["label"] for e in body["timeline"]] == [
        "Reservation created",
        "Payment confirmed",
    ]
    assert "actor_user_id" not in str(body["timeline"])
    for forbidden in (
        "request_idempotency_key",
        "request_hash",
        "gateway_payment_id",
        "gateway_signature_verified",
    ):
        assert forbidden not in response.text, forbidden


def test_customer_detail_other_customer_404():
    orders = [order_row(customer_id=OTHER_CUSTOMER_ID)]
    client = _client_with(OrdersFake(_tables(orders=orders)))
    assert client.get(f"/v1/orders/{ORDER_ID}").status_code == 404


def test_customer_detail_missing_404():
    client = _client_with(OrdersFake(_tables(orders=[])))
    assert client.get(f"/v1/orders/{ORDER_ID}").status_code == 404


def test_timeline_no_fabricated_events():
    # An order with no event rows gets an empty timeline, not
    # a guessed history derived from its current status.
    tables = _tables()
    tables["order_status_events"] = []
    client = _client_with(OrdersFake(tables))
    body = client.get(f"/v1/orders/{ORDER_ID}").json()
    assert body["timeline"] == []
    assert body["status"] == "confirmed"


def test_expired_and_reconciliation_states_not_success():
    orders = [
        order_row(ORDER_B_ID, status="expired", payment_status="failed"),
        order_row(
            ORDER_C_ID,
            status="pending_payment",
            payment_status="reconciliation_required",
        ),
    ]
    client = _client_with(OrdersFake(_tables(orders=orders)))
    body = client.get("/v1/orders").json()
    # item counts come from the single item row for ORDER_ID;
    # these two orders have no items in the fake, which is
    # fine — the point is their statuses are shown as-is.
    assert body["total"] == 2
    expired = [i for i in body["items"] if i["status"] == "expired"][0]
    assert expired["payment_status"] == "failed"
    recon = [
        i for i in body["items"] if i["payment_status"] == "reconciliation_required"
    ][0]
    assert recon["status"] == "pending_payment"


def test_pending_order_shows_reservation_expiry():
    tables = _tables(
        orders=[
            order_row(
                status="pending_payment", payment_status="created", confirmed_at=None
            )
        ]
    )
    tables["inventory_reservations"] = [
        {
            "id": "res-1",
            "order_id": str(ORDER_ID),
            "status": "active",
            "expires_at": "2026-10-31T12:05:00+00:00",
        }
    ]
    client = _client_with(OrdersFake(tables))
    body = client.get(f"/v1/orders/{ORDER_ID}").json()
    assert body["reservation_expires_at"] == "2026-10-31T12:05:00Z"
    assert body["payment"]["amount_paid"] == "0"
    assert body["payment"]["gateway_label"] is None


# --- merchant ---------------------------------------------------------------


def _merchant_tables(orders):
    tables = _tables(orders=orders)
    # The caller is the merchant owner (user id CUSTOMER_ID in
    # this test setup doubles as the merchant user).
    return tables


def test_merchant_sees_authorized_store_orders_only():
    orders = [
        order_row(),
        order_row(
            ORDER_B_ID,
            store_id=OTHER_STORE_ID,
            merchant_id=OTHER_MERCHANT_ID,
            order_number="SF-20261031-000002",
        ),
    ]
    client = _client_with(OrdersFake(_merchant_tables(orders)))
    body = client.get("/v1/merchant/orders").json()
    assert body["total"] == 1
    assert body["items"][0]["order_number"] == "SF-20261031-000001"
    assert "customer_id" not in body["items"][0]
    assert "email" not in str(body["items"][0])


def test_merchant_unauthorized_store_filter_empty():
    client = _client_with(OrdersFake(_merchant_tables([order_row()])))
    body = client.get(f"/v1/merchant/orders?store_id={OTHER_STORE_ID}").json()
    assert body["total"] == 0
    assert client.get(f"/v1/merchant/orders/{ORDER_B_ID}").status_code == 404


def test_merchant_detail_and_search_and_filters():
    orders = [
        order_row(),
        order_row(
            ORDER_B_ID,
            order_number="SF-20261031-000002",
            status="pending_payment",
            payment_status="created",
        ),
    ]
    client = _client_with(OrdersFake(_merchant_tables(orders)))
    assert client.get("/v1/merchant/orders?search=000002").json()["total"] == 1
    assert client.get("/v1/merchant/orders?status=pending_payment").json()["total"] == 1
    assert (
        client.get("/v1/merchant/orders?payment_status=captured").json()["total"] == 1
    )
    detail = client.get(f"/v1/merchant/orders/{ORDER_ID}")
    assert detail.status_code == 200
    assert detail.json()["order_number"] == "SF-20261031-000001"
    assert "customer@example.com" not in detail.text
    assert detail.json()["customer_note"] == "Please pack separately"


def test_merchant_summary_counts():
    orders = [
        order_row(),
        order_row(
            ORDER_B_ID,
            order_number="SF-20261031-000002",
            status="pending_payment",
            payment_status="created",
        ),
        order_row(
            ORDER_C_ID,
            order_number="SF-20261031-000003",
            status="collected",
            payment_status="captured",
            collected_at="2026-10-31T19:00:00+00:00",
        ),
    ]
    client = _client_with(OrdersFake(_merchant_tables(orders)))
    body = client.get("/v1/merchant/orders/summary").json()
    assert body["total"] == 3
    assert body["awaiting_payment"] == 1
    assert body["paid"] == 2
    assert body["completed"] == 1
    assert body["cancelled_or_expired"] == 0


def test_merchant_no_membership_empty():
    tables = _tables()
    tables["merchant_memberships"] = []
    client = _client_with(OrdersFake(tables))
    assert client.get("/v1/merchant/orders").json()["total"] == 0
    assert client.get("/v1/merchant/orders/summary").json()["total"] == 0
    assert client.get(f"/v1/merchant/orders/{ORDER_ID}").status_code == 404


def test_no_private_table_queries():
    fake = OrdersFake(_tables())
    client = _client_with(fake)
    client.get("/v1/orders")
    client.get(f"/v1/orders/{ORDER_ID}")
    client.get("/v1/merchant/orders")
    client.get("/v1/merchant/orders/summary")
    assert all(not table.startswith("private.") for table, _s, _f in fake.query_calls)
    assert all(table != "payment_transactions" for table, _s, _f in fake.query_calls)
