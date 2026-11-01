"""W8 migration-consistency tests (no live database).

These tests prove the two W8 migration files say what the
W8 audit claims: the dedup fix makes notification keys
per-recipient, and the grants file restricts the two W7
worker RPCs to service_role. Like the W7 tests, they parse
with pglast and assert on file contents only. They do NOT
prove the migrations apply to live — there is no Postgres
in this environment — so apply-time behaviour is reported
honestly in the PR, not claimed here.
"""

import re
from pathlib import Path

import pglast

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
DEDUP = MIGRATIONS / "20261101130000_w8_notification_dedup_per_recipient.sql"
GRANTS = MIGRATIONS / "20261101131000_w8_notification_rpc_grants.sql"


def test_w8_migration_files_exist_and_parse():
    for path in (DEDUP, GRANTS):
        assert path.exists(), f"missing migration: {path.name}"
        assert pglast.parse_sql(path.read_text()), path.name


def test_dedup_key_is_per_recipient():
    text = DEDUP.read_text()
    # The fixed key embeds the recipient id. The old key
    # (type + reference id only) dropped every recipient
    # after the first for multi-recipient events.
    assert (
        "p_notification_type || ':' || p_reference_id::text || ':' || p_user_id::text"
        in text
    ), "dedup key does not embed p_user_id"
    # Only the enqueue helper is replaced; the indexes and
    # ON CONFLICT clauses are unchanged because the key
    # itself is now unique per recipient.
    assert "private.w7_enqueue_notification" in text
    assert "create unique index" not in text


def test_grants_restrict_worker_rpcs_to_service_role():
    text = GRANTS.read_text()
    for signature in (
        "public.backend_process_notification_outbox(text, integer)",
        "public.backend_enqueue_pickup_reminders(timestamptz, integer)",
    ):
        assert f"revoke execute on function {signature} from public" in text, signature
        assert f"grant execute on function {signature} to service_role" in text, (
            signature
        )
    # Nothing here grants anon or authenticated.
    assert "to authenticated" not in text
    assert "to anon" not in text


def test_w8_files_order_after_w7():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    w7_last = "20261101122000_w7_notification_delivery.sql"
    assert names.index(w7_last) < names.index(DEDUP.name) < names.index(GRANTS.name)
    assert re.search(r"NOT APPLIED TO LIVE", DEDUP.read_text())
    assert re.search(r"NOT APPLIED TO LIVE", GRANTS.read_text())
