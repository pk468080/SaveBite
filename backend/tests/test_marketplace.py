"""Milestone 5 tests: public marketplace discovery and reservations.

Discovery uses an anonymous fake client (no auth override at
all — the routes must work with no bearer token). Reservation
uses an authenticated fake. No test touches live Supabase, and
no test uses the service-role key: get_service_client is
overridden to raise, so any service-role use would 500.
"""

import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    get_anon_client,
    get_current_user,
    get_service_client,
    get_user_client,
)
from app.main import create_app
from app.schemas import AuthenticatedUser
from app.supabase_client import RPCNotAllowedError, SupabaseRestClient
from tests.conftest import test_settings as make_test_settings

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
OTHER_MERCHANT_ID = UUID("33333333-3333-4333-8333-333333333333")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
INACTIVE_STORE_ID = UUID("55555555-5555-4555-8555-555555555555")
UNAPPROVED_STORE_ID = UUID("66666666-6666-4666-8666-666666666666")
LISTING_ID = UUID("77777777-7777-4777-8777-777777777777")
LISTING_B_ID = UUID("88888888-8888-4888-8888-888888888888")
LISTING_C_ID = UUID("99999999-9999-4999-8999-999999999999")
CATEGORY_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
INACTIVE_CATEGORY_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ORDER_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")

USER = AuthenticatedUser(id=USER_ID, email="customer@example.com", token="tok")

# Windows that are open at any 2026 test time, and one expired set.
OPEN = {
    "sale_starts_at": "2026-01-01T09:00:00+00:00",
    "sale_ends_at": "2027-01-01T18:00:00+00:00",
    "pickup_starts_at": "2026-01-01T18:00:00+00:00",
    "pickup_ends_at": "2027-01-01T21:00:00+00:00",
}
EXPIRED = {
    "sale_starts_at": "2026-01-01T09:00:00+00:00",
    "sale_ends_at": "2026-02-01T18:00:00+00:00",
    "pickup_starts_at": "2026-01-01T18:00:00+00:00",
    "pickup_ends_at": "2026-02-01T21:00:00+00:00",
}


def store_row(store_id=STORE_ID, merchant_id=MERCHANT_ID, **overrides):
    row = {
        "id": str(store_id),
        "merchant_id": str(merchant_id),
        "name": "Sharma Foods Dwarka",
        "locality": "Dwarka Sector 7",
        "city": "New Delhi",
        "state": "Delhi",
        "pincode": "110075",
        "timezone": "Asia/Kolkata",
        "status": "active",
    }
    row.update(overrides)
    return row


def listing_row(listing_id=LISTING_ID, store_id=STORE_ID, **overrides):
    row = {
        "id": str(listing_id),
        "store_id": str(store_id),
        "listing_type": "surprise_bag",
        "category_id": str(CATEGORY_ID),
        "title": "Evening Surprise Bag",
        "description": "Assorted bakery items",
        "contents_description": "Bread and pastries",
        "reference_value": "300.00",
        "selling_price": "195.00",
        "currency": "INR",
        "total_quantity": 10,
        "reserved_quantity": 2,
        "sold_quantity": 1,
        "available_quantity": 7,
        "dietary_classification": "vegetarian",
        "allergen_codes": ["gluten"],
        "storage_instructions": "Keep cool",
        "status": "active",
        "created_by": "22222222-2222-4222-8222-222222222222",
        "created_at": "2026-10-01T00:00:00Z",
        "updated_at": "2026-10-01T00:00:00Z",
        "template_id": None,
        "food_safety_notes": "internal note",
    }
    row.update(OPEN)
    row.update(overrides)
    return row


class MarketplaceFake:
    """Fake anon/authenticated client: query honours eq/in filters
    and select projections; insert/update/rpc are tracked and,
    for the anon fake, must never be called by discovery routes."""

    def __init__(self, tables=None, rpc_result=None, rpc_error=None):
        self.tables = tables or {}
        self.rpc_result = rpc_result
        self.rpc_error = rpc_error
        self.query_calls = []
        self.rpc_calls = []
        self.insert_calls = []
        self.update_calls = []

    def _matches(self, row, filters):
        if not filters:
            return True
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
        return True

    async def query(self, table, *, select="*", filters=None):
        self.query_calls.append((table, select, filters))
        rows = [r for r in self.tables.get(table, []) if self._matches(r, filters)]
        if select.strip() == "*":
            return [dict(r) for r in rows]
        columns = [c.strip() for c in select.split(",") if c.strip()]
        return [{c: r[c] for c in columns if c in r} for r in rows]

    async def insert(self, table, row):
        self.insert_calls.append((table, dict(row)))
        raise AssertionError("marketplace routes must not insert")

    async def update(self, table, row, filters):
        self.update_calls.append((table, dict(row), filters))
        raise AssertionError("marketplace routes must not update")

    async def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        if self.rpc_error is not None:
            raise self.rpc_error
        return self.rpc_result


def _tables(listings=None):
    return {
        "stores": [
            store_row(),
            store_row(INACTIVE_STORE_ID, status="inactive"),
            store_row(UNAPPROVED_STORE_ID, OTHER_MERCHANT_ID),
        ],
        "merchants": [
            {"id": str(MERCHANT_ID), "status": "approved"},
            {"id": str(OTHER_MERCHANT_ID), "status": "pending_review"},
        ],
        "categories": [
            {
                "id": str(CATEGORY_ID),
                "parent_id": None,
                "name": "Bakery",
                "slug": "bakery",
                "display_order": 1,
                "is_active": True,
            },
            {
                "id": str(INACTIVE_CATEGORY_ID),
                "parent_id": None,
                "name": "Hidden",
                "slug": "hidden",
                "display_order": 2,
                "is_active": False,
            },
        ],
        "listings": listings if listings is not None else [listing_row()],
        "listing_images": [
            {
                "listing_id": str(LISTING_ID),
                "storage_path": f"{LISTING_ID}/bag.jpg",
                "alt_text": "Bag",
                "display_order": 0,
            },
            {
                "listing_id": str(LISTING_ID),
                "storage_path": "https://evil.example.com/bag.jpg",
                "alt_text": "Evil",
                "display_order": 1,
            },
        ],
    }


def _client_with(fake, authenticated=False):
    app = create_app(make_test_settings())

    def _anon():
        return fake

    def _boom():
        raise AssertionError("service-role client must not be used here")

    app.dependency_overrides[get_anon_client] = _anon
    app.dependency_overrides[get_service_client] = _boom
    if authenticated:

        async def _user():
            return USER

        def _client():
            return fake

        app.dependency_overrides[get_current_user] = _user
        app.dependency_overrides[get_user_client] = _client
    return TestClient(app, raise_server_exceptions=False)


def _upstream_error(status, pg_code, message):
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/rpc/x")
    response = httpx.Response(
        status, json={"code": pg_code, "message": message}, request=request
    )
    return httpx.HTTPStatusError(message, request=request, response=response)


def _reservation_result(**overrides):
    result = {
        "order_id": str(ORDER_ID),
        "order_number": "SF-20261031-000001",
        "status": "pending_payment",
        "total_amount": "390.00",
        "currency": "INR",
        "reservation_expires_at": "2026-10-31T12:05:00Z",
        "pickup_starts_at": "2026-10-31T18:00:00Z",
        "pickup_ends_at": "2026-10-31T21:00:00+00:00",
        "idempotent_replay": False,
    }
    result.update(overrides)
    return result


# --- anonymous discovery ----------------------------------------------


def test_anon_can_browse_and_detail():
    client = _client_with(MarketplaceFake(tables=_tables()))
    response = client.get("/v1/marketplace/listings")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["title"] == "Evening Surprise Bag"
    assert item["store"]["name"] == "Sharma Foods Dwarka"
    assert item["store"]["city"] == "New Delhi"
    detail = client.get(f"/v1/marketplace/listings/{LISTING_ID}")
    assert detail.status_code == 200
    assert detail.json()["id"] == str(LISTING_ID)


def test_authenticated_customer_can_browse_too():
    client = _client_with(MarketplaceFake(tables=_tables()))
    response = client.get(
        "/v1/marketplace/listings",
        headers={"Authorization": "Bearer some-token"},
    )
    assert response.status_code == 200


def test_categories_active_only():
    client = _client_with(MarketplaceFake(tables=_tables()))
    response = client.get("/v1/marketplace/categories")
    assert response.status_code == 200
    assert [c["slug"] for c in response.json()] == ["bakery"]


@pytest.mark.parametrize(
    "status", ["draft", "paused", "cancelled", "sold_out", "expired"]
)
def test_ineligible_statuses_never_exposed(status):
    tables = _tables(listings=[listing_row(status=status)])
    client = _client_with(MarketplaceFake(tables=tables))
    assert client.get("/v1/marketplace/listings").json()["total"] == 0
    assert client.get(f"/v1/marketplace/listings/{LISTING_ID}").status_code == 404


def test_expired_sale_window_excluded():
    tables = _tables(listings=[listing_row(**EXPIRED)])
    client = _client_with(MarketplaceFake(tables=tables))
    assert client.get("/v1/marketplace/listings").json()["total"] == 0


def test_zero_available_excluded():
    tables = _tables(listings=[listing_row(available_quantity=0)])
    client = _client_with(MarketplaceFake(tables=tables))
    assert client.get("/v1/marketplace/listings").json()["total"] == 0


def test_inactive_and_unapproved_stores_not_exposed():
    tables = _tables(
        listings=[
            listing_row(LISTING_B_ID, INACTIVE_STORE_ID),
            listing_row(LISTING_C_ID, UNAPPROVED_STORE_ID),
        ]
    )
    client = _client_with(MarketplaceFake(tables=tables))
    assert client.get("/v1/marketplace/listings").json()["total"] == 0


def test_inactive_category_listing_excluded():
    tables = _tables(listings=[listing_row(category_id=INACTIVE_CATEGORY_ID)])
    client = _client_with(MarketplaceFake(tables=tables))
    assert client.get("/v1/marketplace/listings").json()["total"] == 0


def test_search_and_filters():
    listings = [
        listing_row(),
        listing_row(
            LISTING_B_ID,
            listing_type="individual_item",
            title="Veg Pizza Slice",
            description="Cheesy slice",
            selling_price="120.00",
            dietary_classification="vegan",
        ),
        listing_row(
            LISTING_C_ID,
            title="Chicken Biryani",
            selling_price="293.00",
            dietary_classification="non_vegetarian",
        ),
    ]
    client = _client_with(MarketplaceFake(tables=_tables(listings=listings)))
    assert client.get("/v1/marketplace/listings?search=pizza").json()["total"] == 1
    assert (
        client.get("/v1/marketplace/listings?listing_type=individual_item").json()[
            "total"
        ]
        == 1
    )
    assert client.get("/v1/marketplace/listings?dietary=vegan").json()["total"] == 1
    assert client.get("/v1/marketplace/listings?min_price=200").json()["total"] == 1
    assert client.get("/v1/marketplace/listings?max_price=150").json()["total"] == 1
    assert client.get("/v1/marketplace/listings?city=New%20Delhi").json()["total"] == 3
    assert client.get("/v1/marketplace/listings?city=Mumbai").json()["total"] == 0
    assert client.get("/v1/marketplace/listings?pincode=110075").json()["total"] == 3
    assert client.get("/v1/marketplace/listings?pincode=110001").json()["total"] == 0
    assert (
        client.get("/v1/marketplace/listings?min_price=300&max_price=100").status_code
        == 422
    )


def test_pagination_and_sorting_stable():
    listings = [
        listing_row(
            LISTING_ID, selling_price="300.00", created_at="2026-10-01T00:00:00Z"
        ),
        listing_row(
            LISTING_B_ID, selling_price="100.00", created_at="2026-10-03T00:00:00Z"
        ),
        listing_row(
            LISTING_C_ID, selling_price="200.00", created_at="2026-10-02T00:00:00Z"
        ),
    ]
    client = _client_with(MarketplaceFake(tables=_tables(listings=listings)))
    low = client.get("/v1/marketplace/listings?sort=lowest_price").json()
    assert [i["selling_price"] for i in low["items"]] == ["100.00", "200.00", "300.00"]
    high = client.get("/v1/marketplace/listings?sort=highest_price").json()
    assert [i["selling_price"] for i in high["items"]] == ["300.00", "200.00", "100.00"]
    newest = client.get("/v1/marketplace/listings?sort=newest").json()
    assert [i["id"] for i in newest["items"]] == [
        str(LISTING_B_ID),
        str(LISTING_C_ID),
        str(LISTING_ID),
    ]
    page1 = client.get("/v1/marketplace/listings?page=1&page_size=2").json()
    page2 = client.get("/v1/marketplace/listings?page=2&page_size=2").json()
    assert len(page1["items"]) == 2 and len(page2["items"]) == 1
    assert page1["total"] == 3
    assert {i["id"] for i in page1["items"]} & {
        i["id"] for i in page2["items"]
    } == set()


def test_detail_exposes_no_internal_fields():
    client = _client_with(MarketplaceFake(tables=_tables()))
    body = client.get(f"/v1/marketplace/listings/{LISTING_ID}").json()
    for forbidden in (
        "created_by",
        "created_at",
        "updated_at",
        "template_id",
        "food_safety_notes",
        "total_quantity",
        "reserved_quantity",
        "sold_quantity",
        "contact_phone",
        "merchant_id",
    ):
        assert forbidden not in body, forbidden
        assert forbidden not in body["store"], forbidden
    assert body["available_quantity"] == 7


def test_images_resolve_to_bucket_paths_only():
    client = _client_with(MarketplaceFake(tables=_tables()))
    body = client.get(f"/v1/marketplace/listings/{LISTING_ID}").json()
    assert [img["storage_path"] for img in body["images"]] == [f"{LISTING_ID}/bag.jpg"]


def test_listing_select_projection_is_explicit():
    fake = MarketplaceFake(tables=_tables())
    client = _client_with(fake)
    client.get("/v1/marketplace/listings")
    listing_calls = [c for c in fake.query_calls if c[0] == "listings"]
    assert listing_calls
    select = listing_calls[0][1]
    assert select != "*"
    assert "created_by" not in select
    assert "food_safety_notes" not in select
    assert "template_id" not in select


# --- anonymous client security -----------------------------------------


def test_anon_client_cannot_write_or_rpc():
    settings = make_test_settings()
    anon = SupabaseRestClient(settings, anonymous=True)
    with pytest.raises(RPCNotAllowedError):
        asyncio.run(anon.insert("listings", {}))
    with pytest.raises(RPCNotAllowedError):
        asyncio.run(anon.update("listings", {}, {}))
    with pytest.raises(RPCNotAllowedError):
        asyncio.run(anon.rpc("create_order_reservation", {}))


def test_discovery_never_writes_or_calls_rpc():
    fake = MarketplaceFake(tables=_tables())
    client = _client_with(fake)
    client.get("/v1/marketplace/listings")
    client.get(f"/v1/marketplace/listings/{LISTING_ID}")
    client.get("/v1/marketplace/categories")
    assert fake.insert_calls == []
    assert fake.update_calls == []
    assert fake.rpc_calls == []


# --- reservations --------------------------------------------------------


def test_reservation_requires_authentication():
    app = create_app(make_test_settings())
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 2}],
        },
        headers={"Idempotency-Key": "test-key-123456"},
    )
    assert response.status_code == 401


def test_reservation_success_calls_approved_rpc():
    fake = MarketplaceFake(tables=_tables(), rpc_result=_reservation_result())
    client = _client_with(fake, authenticated=True)
    response = client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 2}],
            "customer_note": "Please pack separately",
        },
        headers={"Idempotency-Key": "my-key-12345678"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["order_id"] == str(ORDER_ID)
    assert body["order_number"] == "SF-20261031-000001"
    assert body["status"] == "pending_payment"
    assert body["total_amount"] == "390.00"
    assert body["reservation_expires_at"] == "2026-10-31T12:05:00Z"
    assert body["pickup_starts_at"] == "2026-10-31T18:00:00Z"
    assert body["idempotent_replay"] is False
    assert fake.rpc_calls == [
        (
            "create_order_reservation",
            {
                "p_store_id": str(STORE_ID),
                "p_items": [{"listing_id": str(LISTING_ID), "quantity": 2}],
                "p_idempotency_key": "my-key-12345678",
                "p_customer_note": "Please pack separately",
            },
        )
    ]
    assert fake.insert_calls == [] and fake.update_calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"store_id": str(STORE_ID), "items": []},
        {
            "store_id": str(STORE_ID),
            "items": [
                {"listing_id": str(LISTING_ID), "quantity": 1},
                {"listing_id": str(LISTING_ID), "quantity": 1},
            ],
        },
        {
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 0}],
        },
        {
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 21}],
        },
        {
            "store_id": str(STORE_ID),
            "items": [
                {"listing_id": str(LISTING_ID), "quantity": 1} for _ in range(21)
            ],
        },
    ],
)
def test_reservation_validation(payload):
    fake = MarketplaceFake(tables=_tables(), rpc_result=_reservation_result())
    client = _client_with(fake, authenticated=True)
    response = client.post(
        "/v1/orders/reservations",
        json=payload,
        headers={"Idempotency-Key": "valid-key-123456"},
    )
    assert response.status_code == 422, (payload, response.text)
    assert fake.rpc_calls == []


@pytest.mark.parametrize("key", [None, "short", "x" * 129])
def test_reservation_idempotency_key_validation(key):
    fake = MarketplaceFake(tables=_tables(), rpc_result=_reservation_result())
    client = _client_with(fake, authenticated=True)
    headers = {} if key is None else {"Idempotency-Key": key}
    response = client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 1}],
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert fake.rpc_calls == []


def test_reservation_ignores_caller_supplied_identity():
    fake = MarketplaceFake(tables=_tables(), rpc_result=_reservation_result())
    client = _client_with(fake, authenticated=True)
    response = client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 1}],
            "customer_id": "99999999-9999-4999-8999-999999999999",
            "role": "admin",
        },
        headers={"Idempotency-Key": "valid-key-123456"},
    )
    assert response.status_code == 201, response.text
    _name, params = fake.rpc_calls[0]
    assert "customer_id" not in params and "role" not in params


def test_reservation_idempotent_replay():
    fake = MarketplaceFake(
        tables=_tables(),
        rpc_result=_reservation_result(
            idempotent_replay=True, reservation_expires_at=None
        ),
    )
    # Replay responses carry no expiry key at all in the real RPC;
    # the fake result above keeps the key with None to prove the
    # API handles both shapes. Drop it here to match the RPC.
    fake.rpc_result.pop("reservation_expires_at", None)
    client = _client_with(fake, authenticated=True)
    response = client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 1}],
        },
        headers={"Idempotency-Key": "valid-key-123456"},
    )
    assert response.status_code == 201
    assert response.json()["idempotent_replay"] is True
    assert response.json()["reservation_expires_at"] is None


def test_reservation_rpc_insufficient_inventory_422():
    fake = MarketplaceFake(
        tables=_tables(),
        rpc_error=_upstream_error(400, "P0001", "insufficient_inventory"),
    )
    client = _client_with(fake, authenticated=True)
    response = client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 5}],
        },
        headers={"Idempotency-Key": "valid-key-123456"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_reservation_no_payment_checkout_called():
    fake = MarketplaceFake(tables=_tables(), rpc_result=_reservation_result())
    client = _client_with(fake, authenticated=True)
    client.post(
        "/v1/orders/reservations",
        json={
            "store_id": str(STORE_ID),
            "items": [{"listing_id": str(LISTING_ID), "quantity": 1}],
        },
        headers={"Idempotency-Key": "valid-key-123456"},
    )
    assert [name for name, _ in fake.rpc_calls] == ["create_order_reservation"]
