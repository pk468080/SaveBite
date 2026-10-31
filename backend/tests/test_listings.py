"""Milestone 4 tests: listings, inventory, images, categories.

All Supabase access is faked; no test touches live Supabase.
The fake mirrors the real database contract where it matters:
- new listings get status draft (no INSERT grant on status),
- inventory counters start at 0 and available_quantity is the
  GENERATED value total - reserved - sold (see architecture.md),
- insert/update honour eq filters, and forbidden columns in a
  write are rejected, proving the router never sends them.
"""

from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_service_client, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings
from tests.test_merchants import membership, staff, store_row

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
MERCHANT_ID = UUID("22222222-2222-4222-8222-222222222222")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
LISTING_ID = UUID("66666666-6666-4666-8666-666666666666")
CATEGORY_ID = UUID("77777777-7777-4777-8777-777777777777")

USER = AuthenticatedUser(id=USER_ID, email="owner@example.com", token="tok")

FORBIDDEN_INSERT = {
    "status",
    "published_at",
    "available_quantity",
    "reserved_quantity",
    "sold_quantity",
    "id",
    "created_at",
    "updated_at",
}
# Status IS updateable (SELECT,UPDATE grant) — it is only
# forbidden on INSERT, where the database default applies.
FORBIDDEN_UPDATE = {
    "published_at",
    "available_quantity",
    "reserved_quantity",
    "sold_quantity",
    "id",
    "created_at",
    "updated_at",
    "store_id",
    "listing_type",
    "template_id",
    "currency",
    "created_by",
}


def listing_row(**overrides):
    row = {
        "id": str(LISTING_ID),
        "store_id": str(STORE_ID),
        "template_id": None,
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
        # Generated: 10 - 2 - 1 = 7.
        "available_quantity": 7,
        "sale_starts_at": "2026-11-01T09:00:00+00:00",
        "sale_ends_at": "2026-11-01T18:00:00+00:00",
        "pickup_starts_at": "2026-11-01T18:00:00+00:00",
        "pickup_ends_at": "2026-11-01T21:00:00+00:00",
        "prepared_at": None,
        "best_before_at": None,
        "allergen_codes": ["gluten", "dairy"],
        "dietary_classification": "vegetarian",
        "storage_instructions": "Keep cool",
        "food_safety_notes": None,
        "status": "draft",
        "published_at": None,
        "created_by": str(USER_ID),
        "created_at": "2026-10-31T00:00:00Z",
        "updated_at": "2026-10-31T00:00:00Z",
    }
    row.update(overrides)
    return row


def category_row(**overrides):
    row = {
        "id": str(CATEGORY_ID),
        "parent_id": None,
        "name": "Bakery",
        "slug": "bakery",
        "display_order": 1,
        "is_active": True,
    }
    row.update(overrides)
    return row


class ListingFake:
    def __init__(self, tables=None, insert_error=None, update_error=None):
        self.tables = tables or {}
        self.insert_error = insert_error
        self.update_error = update_error
        self.insert_calls = []
        self.update_calls = []
        self.query_calls = []

    def _matches(self, row, filters):
        if not filters:
            return True
        for key, value in filters.items():
            if isinstance(value, str) and value.startswith("eq."):
                actual = row.get(key)
                actual_str = (
                    str(actual).lower() if isinstance(actual, bool) else str(actual)
                )
                if actual_str != value[3:]:
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

    async def insert(self, table, row):
        self.insert_calls.append((table, dict(row)))
        if self.insert_error is not None:
            raise self.insert_error
        forbidden = FORBIDDEN_INSERT & set(row)
        assert not forbidden, f"insert sent forbidden columns: {forbidden}"
        new_row = dict(row)
        new_row["id"] = (
            str(LISTING_ID)
            if table == "listings"
            else "88888888-8888-4888-8888-888888888888"
        )
        new_row["status"] = "draft"
        new_row["reserved_quantity"] = 0
        new_row["sold_quantity"] = 0
        # Generated column, recalculated by the database.
        new_row["available_quantity"] = new_row.get("total_quantity", 0)
        new_row["published_at"] = None
        new_row["created_at"] = "2026-10-31T00:00:00Z"
        new_row["updated_at"] = "2026-10-31T00:00:00Z"
        self.tables.setdefault(table, []).append(new_row)
        return [dict(new_row)]

    async def update(self, table, row, filters):
        self.update_calls.append((table, dict(row), filters))
        if self.update_error is not None:
            raise self.update_error
        forbidden = FORBIDDEN_UPDATE & set(row)
        assert not forbidden, f"update sent forbidden columns: {forbidden}"
        updated = []
        for existing in self.tables.get(table, []):
            if self._matches(existing, filters):
                existing.update(row)
                if table == "listings":
                    # Generated column, recalculated by the database.
                    existing["available_quantity"] = (
                        existing.get("total_quantity", 0)
                        - (existing.get("reserved_quantity", 0) or 0)
                        - (existing.get("sold_quantity", 0) or 0)
                    )
                updated.append(dict(existing))
        return updated

    async def rpc(self, name, params):
        raise AssertionError("listings milestone must not call RPCs")


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


def _tables(*, merchant_role="owner", store_role=None, listing=None, categories=True):
    tables = {
        "stores": [store_row()],
        "merchant_memberships": [membership(MERCHANT_ID, USER_ID, merchant_role)],
        "store_staff_memberships": [],
        "categories": [category_row()] if categories else [],
        "listing_templates": [],
        "listings": [listing] if listing is not None else [],
        "listing_images": [],
    }
    if store_role:
        tables["store_staff_memberships"] = [staff(STORE_ID, USER_ID, store_role)]
    return tables


def _listing_payload(**overrides):
    payload = {
        "listing_type": "surprise_bag",
        "category_id": str(CATEGORY_ID),
        "title": "Evening Surprise Bag",
        "description": "Assorted bakery items",
        "reference_value": "300.00",
        "selling_price": "195.00",
        "total_quantity": 10,
        "sale_starts_at": "2026-11-01T09:00:00+00:00",
        "sale_ends_at": "2026-11-01T18:00:00+00:00",
        "pickup_starts_at": "2026-11-01T18:00:00+00:00",
        "pickup_ends_at": "2026-11-01T21:00:00+00:00",
        "allergen_codes": ["gluten"],
        "dietary_classification": "vegetarian",
    }
    payload.update(overrides)
    return payload


def _upstream_error(status, pg_code, message):
    request = httpx.Request("POST", "https://example.supabase.co/rest/v1/listings")
    response = httpx.Response(
        status, json={"code": pg_code, "message": message}, request=request
    )
    return httpx.HTTPStatusError(message, request=request, response=response)


# --- authentication -------------------------------------------------


def test_unauthenticated_rejected():
    app = create_app(make_test_settings())
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/v1/categories").status_code == 401
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 401
    )
    assert client.get(f"/v1/listings/{LISTING_ID}").status_code == 401
    assert client.patch(f"/v1/listings/{LISTING_ID}", json={}).status_code == 401
    assert client.post(f"/v1/listings/{LISTING_ID}/publish").status_code == 401
    assert client.get(f"/v1/listings/{LISTING_ID}/inventory").status_code == 401


# --- categories ------------------------------------------------------


def test_categories_active_only():
    fake = ListingFake(tables=_tables())
    client = _client_with(fake)
    response = client.get("/v1/categories")
    assert response.status_code == 200
    assert [c["slug"] for c in response.json()] == ["bakery"]
    # The query asked for active only.
    assert any(
        call[2] and call[2].get("is_active") == "eq.true"
        for call in fake.query_calls
        if call[0] == "categories"
    )


# --- create ----------------------------------------------------------


def test_create_listing_success_draft_and_forbidden_columns():
    fake = ListingFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(f"/v1/stores/{STORE_ID}/listings", json=_listing_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["created_by"] == str(USER_ID)
    # Generated-column value: total - reserved - sold = 10.
    assert body["available_quantity"] == 10
    table, row = fake.insert_calls[0]
    assert table == "listings"
    assert row["created_by"] == str(USER_ID)
    assert row["currency"] == "INR"
    assert "status" not in row
    assert "available_quantity" not in row


@pytest.mark.parametrize(
    "role", ["owner", "admin", "store_manager", "inventory_manager"]
)
def test_create_listing_roles_allowed(role):
    tables = _tables(
        merchant_role="owner" if role in ("owner", "admin") else "store_manager"
    )
    if role in ("store_manager", "inventory_manager"):
        tables["merchant_memberships"] = [
            membership(MERCHANT_ID, USER_ID, "store_manager")
        ]
        tables["store_staff_memberships"] = [staff(STORE_ID, USER_ID, role)]
    elif role == "admin":
        tables["merchant_memberships"] = [membership(MERCHANT_ID, USER_ID, "admin")]
    fake = ListingFake(tables=tables)
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 201
    )


@pytest.mark.parametrize("role", ["finance_viewer", "pickup_operator"])
def test_create_listing_roles_denied(role):
    tables = _tables(merchant_role=role)
    fake = ListingFake(tables=tables)
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 403
    )
    assert not fake.insert_calls


def test_create_listing_store_manager_without_merchant_membership_denied():
    tables = _tables(merchant_role="owner")
    tables["merchant_memberships"] = []
    tables["store_staff_memberships"] = [staff(STORE_ID, USER_ID, "store_manager")]
    fake = ListingFake(tables=tables)
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 403
    )


def test_create_listing_unknown_store_404():
    fake = ListingFake(tables=_tables())
    fake.tables["stores"] = []
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 404
    )


def test_create_listing_inactive_category_404():
    fake = ListingFake(tables=_tables(categories=False))
    client = _client_with(fake)
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"listing_type": "bundle"},
        {"reference_value": "-1.00"},
        {"selling_price": "0"},
        {"selling_price": "-5"},
        {"total_quantity": 0},
        {"total_quantity": -3},
        {"title": "   "},
        {"sale_ends_at": "2026-11-01T08:00:00+00:00"},
        {"pickup_ends_at": "2026-11-01T17:00:00+00:00"},
        {"pickup_ends_at": "2026-11-01T12:00:00+00:00"},
        {"allergen_codes": ["Bad Code!"]},
        {"dietary_classification": "pescatarian"},
        {
            "best_before_at": "2026-10-31T00:00:00+00:00",
            "prepared_at": "2026-11-01T00:00:00+00:00",
        },
    ],
)
def test_create_listing_validation(overrides):
    fake = ListingFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        f"/v1/stores/{STORE_ID}/listings", json=_listing_payload(**overrides)
    )
    assert response.status_code == 422, (overrides, response.text)
    assert not fake.insert_calls


def test_create_listing_selling_above_reference_allowed_by_db():
    # The database has no selling <= reference check (only >= 0),
    # so the API does not invent one. Documented, not a bug.
    fake = ListingFake(tables=_tables())
    client = _client_with(fake)
    response = client.post(
        f"/v1/stores/{STORE_ID}/listings",
        json=_listing_payload(selling_price="350.00"),
    )
    assert response.status_code == 201, response.text


def test_create_listing_forbidden_body_fields_ignored():
    fake = ListingFake(tables=_tables())
    client = _client_with(fake)
    payload = _listing_payload(
        status="active",
        reserved_quantity=99,
        sold_quantity=99,
        available_quantity=99,
        created_by="99999999-9999-4999-8999-999999999999",
    )
    response = client.post(f"/v1/stores/{STORE_ID}/listings", json=payload)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"
    assert response.json()["reserved_quantity"] == 0


def test_create_listing_upstream_42501_maps_to_403():
    fake = ListingFake(
        tables=_tables(),
        insert_error=_upstream_error(400, "42501", "listing_access_denied"),
    )
    client = _client_with(fake)
    response = client.post(f"/v1/stores/{STORE_ID}/listings", json=_listing_payload())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


# --- read / inventory -------------------------------------------------


def test_get_listing_and_computed_available():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.get(f"/v1/listings/{LISTING_ID}")
    assert response.status_code == 200
    # Generated: 10 total - 2 reserved - 1 sold = 7.
    assert response.json()["available_quantity"] == 7


def test_list_store_listings_member_only():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.get(f"/v1/stores/{STORE_ID}/listings")
    assert response.status_code == 200
    assert len(response.json()) == 1
    fake.tables["merchant_memberships"] = []
    assert client.get(f"/v1/stores/{STORE_ID}/listings").status_code == 403


def test_get_listing_unknown_404():
    fake = ListingFake(tables=_tables())
    client = _client_with(fake)
    assert client.get(f"/v1/listings/{LISTING_ID}").status_code == 404


def test_inventory_view():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.get(f"/v1/listings/{LISTING_ID}/inventory")
    assert response.status_code == 200
    body = response.json()
    assert body["total_quantity"] == 10
    assert body["reserved_quantity"] == 2
    assert body["sold_quantity"] == 1
    assert body["available_quantity"] == 7
    assert body["status"] == "draft"


# --- update -----------------------------------------------------------


def test_update_listing_success_and_reserved_protection():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.patch(
        f"/v1/listings/{LISTING_ID}",
        json={"title": "New Title", "total_quantity": 5},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "New Title"
    # 5 total - 2 reserved - 1 sold = 2 available.
    assert response.json()["available_quantity"] == 2
    table, row, _filters = fake.update_calls[0]
    assert "reserved_quantity" not in row
    assert "available_quantity" not in row
    assert "status" not in row


def test_update_listing_below_reserved_plus_sold_422():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.patch(f"/v1/listings/{LISTING_ID}", json={"total_quantity": 2})
    assert response.status_code == 422
    assert not fake.update_calls


def test_update_listing_invalid_window_422():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.patch(
        f"/v1/listings/{LISTING_ID}",
        json={"pickup_ends_at": "2026-11-01T17:00:00+00:00"},
    )
    assert response.status_code == 422
    assert not fake.update_calls


def test_update_listing_cancelled_cannot_edit():
    fake = ListingFake(tables=_tables(listing=listing_row(status="cancelled")))
    client = _client_with(fake)
    assert (
        client.patch(f"/v1/listings/{LISTING_ID}", json={"title": "X"}).status_code
        == 403
    )


def test_update_listing_finance_viewer_denied():
    fake = ListingFake(
        tables=_tables(merchant_role="finance_viewer", listing=listing_row())
    )
    client = _client_with(fake)
    assert (
        client.patch(f"/v1/listings/{LISTING_ID}", json={"title": "X"}).status_code
        == 403
    )


# --- transitions --------------------------------------------------------


@pytest.mark.parametrize(
    "from_status,to_endpoint,expected",
    [
        ("draft", "publish", 200),
        ("draft", "pause", 422),
        ("draft", "cancel", 200),
        ("active", "pause", 200),
        ("active", "publish", 422),
        ("paused", "resume", 200),
        ("paused", "pause", 422),
        ("cancelled", "publish", 422),
        ("cancelled", "cancel", 422),
        ("sold_out", "cancel", 200),
    ],
)
def test_transitions(from_status, to_endpoint, expected):
    fake = ListingFake(tables=_tables(listing=listing_row(status=from_status)))
    client = _client_with(fake)
    response = client.post(f"/v1/listings/{LISTING_ID}/{to_endpoint}")
    assert response.status_code == expected, (from_status, to_endpoint, response.text)
    if expected == 200:
        assert response.json()["status"] in ("active", "paused", "cancelled")


def test_publish_zero_available_422():
    fake = ListingFake(
        tables=_tables(
            listing=listing_row(status="draft", total_quantity=3, reserved_quantity=3)
        )
    )
    client = _client_with(fake)
    assert client.post(f"/v1/listings/{LISTING_ID}/publish").status_code == 422


def test_cancel_is_update_not_delete():
    fake = ListingFake(tables=_tables(listing=listing_row(status="active")))
    client = _client_with(fake)
    response = client.post(f"/v1/listings/{LISTING_ID}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert fake.update_calls


# --- images -------------------------------------------------------------


def test_add_image_success_and_path_rule():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.post(
        f"/v1/listings/{LISTING_ID}/images",
        json={
            "storage_path": f"{LISTING_ID}/bag.jpg",
            "alt_text": "Surprise bag",
            "display_order": 0,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["storage_path"] == f"{LISTING_ID}/bag.jpg"
    table, row = fake.insert_calls[0]
    assert table == "listing_images"


def test_add_image_wrong_listing_path_422():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.post(
        f"/v1/listings/{LISTING_ID}/images",
        json={"storage_path": "other-id/bag.jpg"},
    )
    assert response.status_code == 422
    assert not fake.insert_calls


def test_add_image_url_rejected():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    response = client.post(
        f"/v1/listings/{LISTING_ID}/images",
        json={"storage_path": "https://example.com/bag.jpg"},
    )
    assert response.status_code == 422


def test_list_images_sorted():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    fake.tables["listing_images"] = [
        {
            "id": "88888888-8888-4888-8888-888888888888",
            "listing_id": str(LISTING_ID),
            "storage_path": f"{LISTING_ID}/b.jpg",
            "alt_text": None,
            "display_order": 1,
            "created_at": "2026-10-31T00:00:00Z",
        },
        {
            "id": "99999999-9999-4999-8999-999999999999",
            "listing_id": str(LISTING_ID),
            "storage_path": f"{LISTING_ID}/a.jpg",
            "alt_text": None,
            "display_order": 0,
            "created_at": "2026-10-31T00:00:00Z",
        },
    ]
    client = _client_with(fake)
    response = client.get(f"/v1/listings/{LISTING_ID}/images")
    assert response.status_code == 200
    assert [img["storage_path"] for img in response.json()] == [
        f"{LISTING_ID}/a.jpg",
        f"{LISTING_ID}/b.jpg",
    ]


def test_service_role_never_used():
    fake = ListingFake(tables=_tables(listing=listing_row()))
    client = _client_with(fake)
    # get_service_client is overridden to raise; any use would 500.
    assert client.get(f"/v1/listings/{LISTING_ID}").status_code == 200
    assert (
        client.post(
            f"/v1/stores/{STORE_ID}/listings", json=_listing_payload()
        ).status_code
        == 201
    )
