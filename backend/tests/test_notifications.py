"""Milestone 12 tests: in-app notification reads, read state,
preferences defaults/validation, and the central service.

All Supabase access is faked. No test touches live
Supabase, queries a private table, or uses the
service-role client. Generation is NOT tested through
HTTP because no live generation path exists (see
app/notifications.py); the service functions are unit
tested for catalogue, dedup, recipients, and reminder
eligibility.
"""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_current_user, get_user_client
from app.main import create_app
from app.notifications import (
    build_notification,
    dedup_key,
    reminder_due,
    resolve_admin_recipients,
    resolve_merchant_recipients,
    validate_preference_updates,
)
from app.schemas import AuthenticatedUser
from tests.conftest import test_settings as make_test_settings

USER_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_ID = UUID("12121212-1212-4121-8121-121212121212")
STORE_ID = UUID("44444444-4444-4444-8444-444444444444")
ORDER_ID = UUID("55555555-5555-4555-8555-555555555555")
NOTIF_ID = UUID("66666666-6666-4666-8666-666666666666")
NOTIF_B_ID = UUID("67676767-6767-4676-8676-676767676767")


def notif_row(notif_id=NOTIF_ID, **overrides):
    row = {
        "id": str(notif_id),
        "user_id": str(USER_ID),
        "notification_type": "payment_captured",
        "title": "Payment successful",
        "body": "Payment for order SF-20261031-000001 was captured successfully.",
        "reference_type": "order",
        "reference_id": str(ORDER_ID),
        "read_at": None,
        "created_at": "2026-10-31T12:05:00+00:00",
    }
    row.update(overrides)
    return row


class NotifFake:
    def __init__(self, tables):
        self.tables = tables
        self.query_calls = []
        self.update_calls = []

    def _matches(self, row, filters):
        for key, value in filters.items():
            if key in ("order", "limit", "offset"):
                continue
            if isinstance(value, str) and value.startswith("eq."):
                if str(row.get(key)) != value[3:]:
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

    async def update(self, table, row, filters):
        assert not table.startswith("private."), "private tables must not be written"
        self.update_calls.append((table, row, filters))
        updated = []
        for existing in self.tables.get(table, []):
            if self._matches(existing, filters):
                existing.update(row)
                updated.append(dict(existing))
        return updated


def _tables(notifications=None):
    return {
        "notifications": notifications
        if notifications is not None
        else [
            notif_row(),
            notif_row(
                NOTIF_B_ID,
                notification_type="pickup_completed",
                title="Pickup completed",
                created_at="2026-10-31T18:30:00+00:00",
                read_at="2026-10-31T18:35:00+00:00",
            ),
            notif_row(
                "68686868-6868-4686-8686-686868686868",
                user_id=str(OTHER_ID),
                created_at="2026-10-31T13:00:00+00:00",
            ),
        ]
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


# --- list / count / detail ----------------------------------------------------


def test_list_only_own_newest_first_and_filters():
    client = _client_with(NotifFake(_tables()))
    body = client.get("/v1/notifications").json()
    assert body["total"] == 2
    assert [i["id"] for i in body["items"]] == [str(NOTIF_B_ID), str(NOTIF_ID)]
    assert body["items"][0]["is_read"] is True
    assert body["items"][1]["is_read"] is False
    unread = client.get("/v1/notifications?unread_only=true").json()
    assert unread["total"] == 1
    filtered = client.get("/v1/notifications?notification_type=pickup_completed").json()
    assert filtered["total"] == 1
    assert client.get("/v1/notifications?notification_type=bogus").status_code == 422
    page2 = client.get("/v1/notifications?page=2&page_size=1").json()
    assert len(page2["items"]) == 1


def test_unread_count_and_detail_ownership():
    client = _client_with(NotifFake(_tables()))
    assert client.get("/v1/notifications/unread-count").json() == {"unread_count": 1}
    detail = client.get(f"/v1/notifications/{NOTIF_ID}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "Payment successful"
    assert (
        client.get("/v1/notifications/99999999-9999-4999-8999-999999999999").status_code
        == 404
    )


def test_unauthenticated_rejected():
    client = _client_with(NotifFake(_tables()), authenticated=False)
    assert client.get("/v1/notifications").status_code == 401
    assert client.get("/v1/notifications/unread-count").status_code == 401


# --- read state -----------------------------------------------------------------


def test_mark_read_idempotent_and_read_all_scoped():
    fake = NotifFake(_tables())
    client = _client_with(fake)
    first = client.post(f"/v1/notifications/{NOTIF_ID}/read").json()
    assert first["already_read"] is False
    assert first["read_at"] is not None
    second = client.post(f"/v1/notifications/{NOTIF_ID}/read").json()
    assert second["already_read"] is True
    assert second["read_at"] == first["read_at"]
    # The other user's notification is untouched by read-all.
    result = client.post("/v1/notifications/read-all").json()
    assert result["updated_count"] == 0
    other = [r for r in fake.tables["notifications"] if r["user_id"] == str(OTHER_ID)][
        0
    ]
    assert other["read_at"] is None
    assert (
        client.post(
            "/v1/notifications/99999999-9999-4999-8999-999999999999/read"
        ).status_code
        == 404
    )


def test_read_all_updates_only_caller_unread():
    fake = NotifFake(_tables(notifications=[notif_row(), notif_row(NOTIF_B_ID)]))
    client = _client_with(fake)
    result = client.post("/v1/notifications/read-all").json()
    assert result["updated_count"] == 2
    assert client.get("/v1/notifications/unread-count").json() == {"unread_count": 0}


# --- preferences ------------------------------------------------------------------


def test_preferences_defaults_and_validation():
    client = _client_with(NotifFake(_tables()))
    body = client.get("/v1/notifications/preferences").json()
    assert body["persisted"] is False
    assert body["preferences"]["payment_updates"] is True
    assert "payment_updates" in body["mandatory_categories"]
    # Unknown category is rejected before any storage attempt.
    assert (
        client.patch(
            "/v1/notifications/preferences",
            json={"preferences": {"spam": True}},
        ).status_code
        == 422
    )
    # Mandatory categories cannot be disabled.
    assert (
        client.patch(
            "/v1/notifications/preferences",
            json={"preferences": {"payment_updates": False}},
        ).status_code
        == 422
    )
    # A valid update is validated but honestly reports
    # that storage is not configured yet.
    assert (
        client.patch(
            "/v1/notifications/preferences",
            json={"preferences": {"pickup_reminders": False}},
        ).status_code
        == 501
    )


# --- service: catalogue, dedup, recipients -----------------------------------------


def test_catalogue_build_and_dedup():
    payload = build_notification(
        "payment_captured",
        str(USER_ID),
        str(ORDER_ID),
        {"order_number": "SF-20261031-000001"},
    )
    assert payload["title"] == "Payment successful"
    assert "SF-20261031-000001" in payload["body"]
    assert payload["dedup_key"] == f"payment_captured:{ORDER_ID}"
    assert dedup_key("payment_captured", str(ORDER_ID)) == dedup_key(
        "payment_captured", str(ORDER_ID)
    )
    assert dedup_key("pickup_reminder", str(ORDER_ID), "30min") != dedup_key(
        "pickup_reminder", str(ORDER_ID), "2h"
    )
    with pytest.raises(ValueError):
        build_notification("bogus_event", str(USER_ID), None, {})


def test_merchant_recipients_from_membership_only():
    recipients = resolve_merchant_recipients(
        [
            {"user_id": "u-owner", "role": "owner", "is_active": True},
            {"user_id": "u-admin", "role": "admin", "is_active": True},
            {"user_id": "u-finance", "role": "finance_viewer", "is_active": True},
            {"user_id": "u-inactive", "role": "owner", "is_active": False},
        ],
        [
            {
                "user_id": "u-manager",
                "store_id": str(STORE_ID),
                "role": "store_manager",
                "is_active": True,
            },
            {
                "user_id": "u-pickup",
                "store_id": str(STORE_ID),
                "role": "pickup_operator",
                "is_active": True,
            },
            {
                "user_id": "u-other-store",
                "store_id": "other",
                "role": "store_manager",
                "is_active": True,
            },
        ],
        str(STORE_ID),
    )
    assert recipients == ["u-admin", "u-manager", "u-owner", "u-pickup"]


def test_admin_recipients_verifiable_roles_only():
    recipients = resolve_admin_recipients(
        [
            {"user_id": "u-ops", "role": "operations_admin", "revoked_at": None},
            {"user_id": "u-super", "role": "super_admin", "revoked_at": None},
            {"user_id": "u-support", "role": "support_agent", "revoked_at": None},
            {
                "user_id": "u-revoked",
                "role": "super_admin",
                "revoked_at": "2026-10-01T00:00:00+00:00",
            },
        ]
    )
    assert recipients == ["u-ops", "u-super"]


def test_preference_validation_rules():
    assert validate_preference_updates({"pickup_reminders": False}) == []
    errors = validate_preference_updates({"payment_updates": False, "nope": True})
    assert len(errors) == 2


# --- reminders ----------------------------------------------------------------------


def _order(**overrides):
    order = {
        "status": "confirmed",
        "payment_status": "captured",
        "pickup_starts_at": "2026-10-31T18:00:00+00:00",
    }
    order.update(overrides)
    return order


def test_reminder_eligibility():
    # Pickup at 18:00. 17:45 is inside both the 30-minute
    # and the 2-hour windows; 15:30 is inside neither.
    assert (
        reminder_due(_order(), datetime(2026, 10, 31, 17, 45, tzinfo=UTC), 30) is True
    )
    assert (
        reminder_due(_order(), datetime(2026, 10, 31, 17, 45, tzinfo=UTC), 120) is True
    )
    assert (
        reminder_due(_order(), datetime(2026, 10, 31, 15, 30, tzinfo=UTC), 30) is False
    )
    assert (
        reminder_due(_order(), datetime(2026, 10, 31, 16, 30, tzinfo=UTC), 120) is True
    )
    # After pickup starts, no reminder is due.
    assert (
        reminder_due(_order(), datetime(2026, 10, 31, 18, 5, tzinfo=UTC), 30) is False
    )
    # Collected, unpaid, cancelled, expired orders never qualify.
    assert (
        reminder_due(
            _order(status="collected"), datetime(2026, 10, 31, 17, 45, tzinfo=UTC), 30
        )
        is False
    )
    assert (
        reminder_due(
            _order(payment_status="created"),
            datetime(2026, 10, 31, 17, 45, tzinfo=UTC),
            30,
        )
        is False
    )
    assert (
        reminder_due(
            _order(status="cancelled"), datetime(2026, 10, 31, 17, 45, tzinfo=UTC), 30
        )
        is False
    )
    assert (
        reminder_due(
            _order(status="expired"), datetime(2026, 10, 31, 17, 45, tzinfo=UTC), 30
        )
        is False
    )
    # Too early for the 30-minute window.
    assert (
        reminder_due(_order(), datetime(2026, 10, 31, 10, 0, tzinfo=UTC), 30) is False
    )


def test_no_private_tables_and_no_generation_route():
    fake = NotifFake(_tables())
    client = _client_with(fake)
    client.get("/v1/notifications")
    assert all(not t.startswith("private.") for t, _s, _f in fake.query_calls)
    # There is no notification creation endpoint: posting
    # a notification payload must not be routed.
    assert client.post("/v1/notifications", json={}).status_code in (404, 405)
