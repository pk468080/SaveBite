"""W7 migration-consistency tests (no live database).

These tests prove the migration files say what the code
claims: they parse, they define the triggers, processor,
and reminder functions, the notifications type CHECK covers
exactly the M12 catalogue, and the trigger bodies carry the
catalogue titles for every event W7 emits. They do NOT
prove the migrations apply to live — there is no Postgres
in this environment — so apply-time behaviour is reported
honestly in the PR, not claimed here.
"""

import re
from pathlib import Path

import pglast

from app.notifications import CATALOGUE, DEFAULT_PREFERENCES

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
PREFS = MIGRATIONS / "20261101120000_w7_notification_preferences.sql"
OUTBOX = MIGRATIONS / "20261101121000_w7_notification_outbox.sql"
DELIVERY = MIGRATIONS / "20261101122000_w7_notification_delivery.sql"

# Events the W7 triggers + worker actually emit. Everything else
# in the catalogue stays unemitted (see the delivery migration
# header for why each one has no trigger).
IMPLEMENTED_EVENTS = [
    "payment_captured",
    "payment_failed",
    "payment_reconciliation_required",
    "pickup_completed",
    "new_paid_order",
    "merchant_pickup_completed",
    "merchant_application_submitted",
    "merchant_application_approved",
    "merchant_application_rejected",
    "merchant_application_reviewed",
    "store_approved",
    "store_deactivated",
    "pickup_reminder",
]


def test_migration_files_exist_and_parse():
    for path in (PREFS, OUTBOX, DELIVERY):
        assert path.exists(), f"missing migration: {path.name}"
        assert pglast.parse_sql(path.read_text()), path.name


def test_notifications_type_check_matches_catalogue_exactly():
    text = DELIVERY.read_text()
    match = re.search(
        r"notifications_type_check\s+check\s*\(notification_type in \((.*?)\)\)",
        text,
        re.DOTALL,
    )
    assert match, "type CHECK not found in delivery migration"
    listed = set(re.findall(r"'([^']+)'", match.group(1)))
    assert listed == set(CATALOGUE), (
        f"CHECK list drifts from catalogue: extra={listed - set(CATALOGUE)}, "
        f"missing={set(CATALOGUE) - listed}"
    )


def test_triggers_processor_and_reminder_functions_defined():
    text = DELIVERY.read_text()
    for name in (
        "w7_enqueue_notification",
        "w7_enqueue_order_notifications",
        "w7_enqueue_merchant_notifications",
        "w7_enqueue_store_notifications",
        "backend_process_notification_outbox",
        "backend_enqueue_pickup_reminders",
    ):
        assert name in text, f"missing function: {name}"
    for trigger in (
        "w7_order_notifications",
        "w7_merchant_notifications",
        "w7_store_notifications",
    ):
        assert f"create trigger {trigger}" in text, f"missing trigger: {trigger}"
    # The processor claims in-app rows only, with SKIP LOCKED,
    # and reclaims jobs past the 10-minute claim window.
    assert "channel = 'in_app'" in text
    assert "for update skip locked" in text
    assert "interval '10 minutes'" in text
    # Reminder eligibility mirrors reminder_due(): eligible
    # statuses + captured payment + absolute window.
    assert "o.status in ('confirmed', 'ready_for_pickup')" in text
    assert "o.payment_status = 'captured'" in text
    assert "p_now < o.pickup_starts_at" in text


def test_trigger_bodies_carry_catalogue_titles():
    text = DELIVERY.read_text()
    for event in IMPLEMENTED_EVENTS:
        assert CATALOGUE[event].title in text, f"title missing for {event}"


def test_no_superseded_post_commit_creation_rpc():
    # W7 superseded the M12 post-commit RPC design with
    # transactional triggers; the delivery migration must not
    # define the old backend_create_notification function.
    assert "backend_create_notification" not in DELIVERY.read_text()


def test_preferences_migration_covers_all_categories():
    text = PREFS.read_text()
    for category in DEFAULT_PREFERENCES:
        assert category in text, f"missing preference column: {category}"
    assert "notification_preferences_mandatory_check" in text
    for policy in (
        "notification_preferences_select_own",
        "notification_preferences_insert_own",
        "notification_preferences_update_own",
    ):
        assert policy in text, f"missing policy: {policy}"


def test_outbox_extension_for_in_app_delivery():
    text = OUTBOX.read_text()
    assert "'in_app'" in text
    assert "notification_outbox_dedup_key_idx" in text
    assert "claimed_by" in text
    assert "claimed_at" in text
