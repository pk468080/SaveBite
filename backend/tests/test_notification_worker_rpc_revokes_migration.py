"""Worker-RPC revoke migration-consistency tests (no live database).

These tests prove the revoke migration file says what it
claims: it removes EXECUTE on the two W7 worker RPCs from
anon and authenticated, grants nothing to either role, and
contains no other state-changing statement. Like the
W7/W8/B1 tests, they parse with pglast and assert on file
contents only. They do NOT prove the migration applies to
live — there is no Postgres in this environment — so
apply-time behaviour (including the has_function_privilege
check) is reported honestly in the PR, not claimed here.
"""

import re
from pathlib import Path

import pglast

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
REVOKES = (
    MIGRATIONS / "20261101190000_notification_worker_rpc_revoke_anon_authenticated.sql"
)
SIGNATURES = (
    "public.backend_process_notification_outbox(text, integer)",
    "public.backend_enqueue_pickup_reminders(timestamptz, integer)",
)


def test_revoke_migration_file_exists_and_parses():
    assert REVOKES.exists(), f"missing migration: {REVOKES.name}"
    assert pglast.parse_sql(REVOKES.read_text()), REVOKES.name


def test_revoke_removes_anon_and_authenticated():
    text = REVOKES.read_text()
    for signature in SIGNATURES:
        assert (
            f"revoke execute on function {signature} from anon, authenticated" in text
        ), signature


def test_revoke_grants_nothing_to_anon_or_authenticated():
    text = REVOKES.read_text()
    assert "to anon" not in text
    assert "to authenticated" not in text


def test_revoke_contains_no_other_state_change():
    text = REVOKES.read_text()
    body = re.sub(r"--.*", "", text)
    statements = [s.strip() for s in body.split(";") if s.strip()]
    assert statements, "no statements in migration"
    for statement in statements:
        assert statement.lower().startswith(
            "revoke execute on function public.backend_"
        ), statement
    assert "NOT APPLIED TO LIVE" in text
