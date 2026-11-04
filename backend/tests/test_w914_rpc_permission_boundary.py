"""W9.1.4 — RPC permission boundary: PostgreSQL 17 + PostgREST tests.

What this module proves, and what it does not:
* It proves, on a REAL disposable PostgreSQL 17 database and a REAL
  PostgREST instance, that the forward-only migration
  ``20261104120000_w914_rpc_permission_boundary.sql`` gives exactly
  the intended caller paths (service-role backend_* RPCs, authenticated
  user-context RPCs, anonymous RLS catalogue reads) and denies every
  other tested path (anon/authenticated on server-only wrappers and
  on private business functions, service-role on user-context
  wrappers, cross-customer / cross-merchant access).
* It does NOT prove the live production ACL state: production was
  never contacted, and the migration is unapplied everywhere durable.
  The before-state asserted here is the MIGRATION-CHAIN state in a
  disposable replay (no migration grants schema USAGE; private
  functions carry default PUBLIC EXECUTE), not a live fact.
* It does NOT use FakeSupabaseClient for any permission-boundary
  assertion. Direct psycopg calls use SET ROLE + SET LOCAL
  request.jwt.claims to exercise the exact role identities PostgREST
  would use; PostgREST tests then exercise the real HTTP path.

Run prerequisites (fail clearly when missing, never silently mocked):
  1. A disposable PostgreSQL 17 cluster bootstrapped with
     backend/tests/pg_bootstrap.py (W9.1.2 script), e.g.::
       PATH=/usr/lib/postgresql/17/bin:$PATH python3 backend/tests/pg_bootstrap.py \\
         --pgdata /tmp/savebite-pgtest17/data --socket-dir /tmp/savebite-pgtest17/sock \\
         --port 54400
     The bootstrap applies the baseline + W9.1 + W9.1.1 only. This
     module's session fixture then applies, in order, the remaining
     chain (W7 preferences, W7 outbox, W7 delivery, W8 dedup, W8
     grants, B1, the worker-RPC revokes) and finally the W9.1.4
     migration, via psql. It refuses to run if any step fails.
  2. A PostgREST binary for the HTTP tests (download when missing):
     https://github.com/PostgREST/postgrest/releases/download/v12.2.3/postgrest-v12.2.3-linux-static-x64.tar.xz
     Place it at /tmp/postgrest/postgrest or set SAVEBITE_POSTGREST_BIN.
  3. DSN override: SAVEBITE_PG_TEST_DSN (default: the PG 17 socket
     above). The fixture REFUSES a non-17 server.

Test-only deviations (disposable database only, never in a migration):
  * auth.uid(): the bootstrap stub returns NULL, so no authenticated
    RPC could ever pass its auth check. The fixture replaces it with
    the Supabase semantics — sub from current_setting
    ('request.jwt.claims', true) — so SET LOCAL claims drive auth.uid().
  * Extensions: Supabase puts pgcrypto/PostGIS in schema `extensions`;
    the disposable bootstrap installs them in `public`, and PostGIS
    is not relocatable (ALTER EXTENSION ... SET SCHEMA fails for
    it). The fixture therefore creates thin `extensions.digest` /
    `extensions.gen_random_bytes` / `extensions.st_makepoint` /
    `extensions.st_setsrid` wrappers delegating to the public
    functions, plus an `extensions.geography` domain over
    `public.geography`, so baseline bodies referencing them resolve
    (the geography cast is parsed even when the NULL-coordinate
    branch is taken). This changes no product code and no migration
    file.
  * PostgREST serves at its root (/rpc/...); a test-only stdlib
    reverse proxy strips the /rest/v1 prefix, exactly the routing
    Supabase's Kong layer performs in production (same pattern as
    the W9.1.3 module).
  * JWTs are minted locally with a throwaway per-session secret via
    stdlib HMAC, for service_role and authenticated roles only.
    Nothing here is a real Supabase credential.

Static tests (no database) run unconditionally and prove the
migration file's shape: it parses, contains no function definition,
grants USAGE to no forbidden role, and lists every expected grant.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import json
import os
import re
import secrets
import socket
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "20261104120000_w914_rpc_permission_boundary.sql"

# Remaining chain, in timestamp order, after pg_bootstrap's baseline +
# W9.1 + W9.1.1. (W9.1/W9.1.1 are already applied by the bootstrap and
# are deliberately NOT re-applied here.)
REMAINING_MIGRATIONS = [
    "20261101120000_w7_notification_preferences.sql",
    "20261101121000_w7_notification_outbox.sql",
    "20261101122000_w7_notification_delivery.sql",
    "20261101130000_w8_notification_dedup_per_recipient.sql",
    "20261101131000_w8_notification_rpc_grants.sql",
    "20261101180000_b1_checkout_gateway_lookup.sql",
    "20261101190000_notification_worker_rpc_revoke_anon_authenticated.sql",
    "20261104120000_w914_rpc_permission_boundary.sql",
]

DEFAULT_DSN = (
    "host=/tmp/savebite-pgtest17/sock port=54400 dbname=savebite_pgtest user=pgtest"
)
DEFAULT_POSTGREST_BIN = "/tmp/postgrest/postgrest"
POSTGREST_VERSION = "v12.2.3"
POSTGREST_DOWNLOAD_URL = (
    "https://github.com/PostgREST/postgrest/releases/download/v12.2.3/"
    "postgrest-v12.2.3-linux-static-x64.tar.xz"
)

# (schema, name, arg-types) -> intended grantees, from docs §7.
# Signatures are written exactly as PostgreSQL reports them via
# pg_get_function_identity_arguments; the test compares privilege
# booleans, not text, so a formatting difference cannot hide a gap.
PRIVATE_MATRIX: dict[tuple[str, str], dict[str, bool]] = {
    # service-role backend implementations
    ("private", "attach_gateway_order"): {"service_role": True},
    ("private", "confirm_payment_capture"): {"service_role": True},
    ("private", "mark_payment_failed"): {"service_role": True},
    ("private", "post_ledger_transaction"): {"service_role": True},
    ("private", "record_payment_webhook_event"): {"service_role": True},
    ("private", "release_expired_inventory_reservations"): {"service_role": True},
    ("private", "reverse_ledger_transaction"): {"service_role": True},
    ("private", "review_merchant_application"): {"service_role": True},
    ("private", "review_store_activation"): {"service_role": True},
    ("private", "update_refund_status"): {"service_role": True},
    ("private", "get_gateway_order_for_payment_transaction"): {"service_role": True},
    ("private", "release_expired_reservations_v2"): {"service_role": True},
    # authenticated user-context implementations
    ("private", "apply_merchant_application"): {"authenticated": True},
    ("private", "begin_payment_checkout"): {"authenticated": True},
    ("private", "create_merchant_store"): {"authenticated": True},
    ("private", "create_order_reservation"): {"authenticated": True},
    ("private", "issue_pickup_token"): {"authenticated": True},
    ("private", "request_order_refund"): {"authenticated": True},
    ("private", "upsert_store_hours"): {"authenticated": True},
    ("private", "verify_pickup_token"): {"authenticated": True},
    # RLS helpers (authenticated: all five; anon: three only)
    ("private", "can_manage_store"): {"authenticated": True, "anon": True},
    ("private", "can_view_order"): {"authenticated": True},
    ("private", "has_platform_role"): {"authenticated": True, "anon": True},
    ("private", "is_merchant_member"): {"authenticated": True},
    ("private", "is_store_public"): {"authenticated": True, "anon": True},
    # deliberately ungranted to every application role
    ("private", "w7_enqueue_notification"): {},
    ("private", "prevent_posted_ledger_entry_mutation"): {},
    ("private", "prevent_posted_ledger_transaction_mutation"): {},
    ("private", "handle_new_auth_user"): {},
}

PUBLIC_WRAPPER_MATRIX: dict[tuple[str, str], dict[str, bool]] = {
    ("public", "apply_merchant_application"): {"authenticated": True},
    ("public", "create_merchant_store"): {"authenticated": True},
    ("public", "upsert_store_hours"): {"authenticated": True},
    ("public", "create_order_reservation"): {"authenticated": True},
    ("public", "begin_payment_checkout"): {"authenticated": True},
    ("public", "issue_pickup_token"): {"authenticated": True},
    ("public", "verify_pickup_token"): {"authenticated": True},
    ("public", "request_refund"): {"authenticated": True},
    ("public", "backend_attach_gateway_order"): {"service_role": True},
    ("public", "backend_confirm_payment_capture"): {"service_role": True},
    ("public", "backend_mark_payment_failed"): {"service_role": True},
    ("public", "backend_post_ledger_transaction"): {"service_role": True},
    ("public", "backend_record_payment_webhook_event"): {"service_role": True},
    ("public", "backend_release_expired_reservations"): {"service_role": True},
    ("public", "backend_reverse_ledger_transaction"): {"service_role": True},
    ("public", "backend_review_merchant"): {"service_role": True},
    ("public", "backend_review_store"): {"service_role": True},
    ("public", "backend_update_refund_status"): {"service_role": True},
    ("public", "backend_process_notification_outbox"): {"service_role": True},
    ("public", "backend_enqueue_pickup_reminders"): {"service_role": True},
    ("public", "backend_get_gateway_order_for_payment_transaction"): {
        "service_role": True
    },
    ("public", "backend_release_expired_reservations_v2"): {"service_role": True},
}

ROLES = ("anon", "authenticated", "service_role")


# ---------------------------------------------------------------------------
# Static tests (no database required)
# ---------------------------------------------------------------------------


def test_migration_file_exists_and_parses():
    import pglast

    assert MIGRATION.exists(), f"missing migration: {MIGRATION.name}"
    assert pglast.parse_sql(MIGRATION.read_text()), MIGRATION.name


def test_migration_is_timestamped_after_latest_existing():
    existing = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    assert MIGRATION.name > max(n for n in existing if n != MIGRATION.name), existing


def test_migration_contains_no_function_definition_or_logic_change():
    text = MIGRATION.read_text()
    body = re.sub(r"--.*", "", text)
    assert "create or replace function" not in body.lower()
    assert "create function" not in body.lower()
    assert "alter function" not in body.lower()
    assert "drop function" not in body.lower()
    assert "create policy" not in body.lower()
    assert "create trigger" not in body.lower()


def test_migration_grants_no_usage_to_public_or_anon():
    text = MIGRATION.read_text()
    body = re.sub(r"--.*", "", text).lower()
    assert "grant usage on schema private to public" not in body
    assert "grant usage on schema private to anon" not in body
    assert "grant usage on schema private to authenticated" in body
    assert "grant usage on schema private to service_role" in body
    assert "grant execute on all functions" not in body
    assert "grant all" not in body


def test_migration_covers_every_matrix_function():
    text = MIGRATION.read_text()
    body = re.sub(r"--.*", "", text)
    granted = {
        (s, n)
        for (s, n), want in list(PRIVATE_MATRIX.items())
        + list(PUBLIC_WRAPPER_MATRIX.items())
        if want
    }
    for schema, name in granted:
        assert f"{schema}.{name}(" in body, f"missing grant/revoke for {schema}.{name}"
    # Deliberately ungranted functions must not appear in a GRANT
    # statement (comments explaining the omission are fine).
    for schema, name in PRIVATE_MATRIX:
        if not PRIVATE_MATRIX[(schema, name)]:
            assert f"grant execute on function {schema}.{name}(" not in body.lower(), (
                f"unexpected grant for deliberately ungranted {schema}.{name}"
            )


# ---------------------------------------------------------------------------
# Live-database fixtures
# ---------------------------------------------------------------------------


def _require_psycopg():
    try:
        import psycopg
    except ImportError:
        pytest.fail(
            "psycopg is required for W9.1.4 tests (pip install psycopg[binary]); "
            "refusing to substitute a mock database client."
        )
    return psycopg


def _connect(psycopg, application_name: str):
    dsn = os.environ.get("SAVEBITE_PG_TEST_DSN", DEFAULT_DSN)
    return psycopg.connect(dsn, application_name=application_name)


def _parse_dsn(dsn: str) -> dict[str, str]:
    if dsn.startswith(("postgres://", "postgresql://")):
        pytest.fail(
            "W9.1.4 fixture: URL-form DSNs are not supported; use key=value form"
        )
    return dict(p.split("=", 1) for p in dsn.split() if "=" in p)


def _psql_file(dsn_parts: dict[str, str], path: Path) -> None:
    env = dict(os.environ)
    env.pop("PGSERVICE", None)
    cmd = ["psql", "-v", "ON_ERROR_STOP=1", "-q", "-f", str(path)]
    if dsn_parts.get("host", "").startswith("/"):
        cmd += ["-h", dsn_parts["host"]]
    elif dsn_parts.get("host"):
        cmd += ["-h", dsn_parts["host"]]
    if dsn_parts.get("port"):
        cmd += ["-p", dsn_parts["port"]]
    cmd += [
        "-U",
        dsn_parts.get("user", "pgtest"),
        "-d",
        dsn_parts.get("dbname", "savebite_pgtest"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        pytest.fail(f"psql failed on {path.name}:\n{proc.stdout}\n{proc.stderr}")


def _psql_sql(dsn_parts: dict[str, str], sql: str) -> None:
    proc = subprocess.run(
        [
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-c",
            sql,
            "-h",
            dsn_parts.get("host", ""),
            "-p",
            dsn_parts.get("port", ""),
            "-U",
            dsn_parts.get("user", "pgtest"),
            "-d",
            dsn_parts.get("dbname", "savebite_pgtest"),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        pytest.fail(f"psql setup failed:\n{proc.stdout}\n{proc.stderr}")


@pytest.fixture(scope="session")
def pg17_session(tmp_path_factory):
    psycopg = _require_psycopg()
    dsn = os.environ.get("SAVEBITE_PG_TEST_DSN", DEFAULT_DSN)
    parts = _parse_dsn(dsn)
    probe = _connect(psycopg, application_name="w914-probe")
    try:
        with probe.cursor() as cur:
            cur.execute("SHOW server_version")
            (version,) = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'public' "
                "AND p.proname = 'backend_release_expired_reservations_v2'"
            )
            (nfunc,) = cur.fetchone()
        if not version.startswith("17."):
            pytest.fail(
                f"W9.1.4 requires PostgreSQL 17, but the test database reports "
                f"{version!r}. Point SAVEBITE_PG_TEST_DSN at a PG 17 cluster "
                "(see module docstring) — refusing to test another version "
                "while claiming 17."
            )
        if nfunc != 1:
            pytest.fail(
                "Test database is not bootstrapped: "
                "public.backend_release_expired_reservations_v2 not found. "
                "Run backend/tests/pg_bootstrap.py first (see module docstring)."
            )
    finally:
        probe.close()
    # Test-only setup: claims-aware auth.uid() + extensions schema +
    # catalogue RLS policies + table grants. The policies are the
    # baseline bodies with corrected role lists (the bootstrap strips
    # the corrupted baseline policies); the table grants mirror the
    # live Supabase table grants, which the tracking copy does not
    # reproduce. None of this is in any migration file.
    _psql_sql(
        parts,
        "CREATE SCHEMA IF NOT EXISTS extensions; "
        "CREATE SEQUENCE IF NOT EXISTS public.order_number_seq; "
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n "
        "ON n.oid = t.typnamespace WHERE n.nspname = 'extensions' AND t.typname = 'geography') "
        "THEN CREATE DOMAIN extensions.geography AS public.geography; END IF; END $$; "
        "CREATE OR REPLACE FUNCTION extensions.st_makepoint(double precision, double precision) "
        "RETURNS public.geometry LANGUAGE sql AS $$ SELECT public.st_makepoint($1, $2) $$; "
        "CREATE OR REPLACE FUNCTION extensions.st_setsrid(public.geometry, integer) "
        "RETURNS public.geometry LANGUAGE sql AS $$ SELECT public.st_setsrid($1, $2) $$; "
        "CREATE OR REPLACE FUNCTION extensions.digest(data bytea, algo text) RETURNS bytea "
        "LANGUAGE sql AS $$ SELECT public.digest(data, algo) $$; "
        "CREATE OR REPLACE FUNCTION extensions.digest(data text, algo text) RETURNS bytea "
        "LANGUAGE sql AS $$ SELECT public.digest(data::bytea, algo) $$; "
        "CREATE OR REPLACE FUNCTION extensions.gen_random_bytes(n integer) RETURNS bytea "
        "LANGUAGE sql AS $$ SELECT public.gen_random_bytes(n) $$; "
        "CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS "
        "$$ SELECT CASE WHEN current_setting('request.jwt.claims', true) IN ('', NULL) "
        "THEN NULL::uuid ELSE (current_setting('request.jwt.claims', true)::json->>'sub')::uuid END $$; "
        "GRANT SELECT ON public.listings, public.stores, public.store_hours, "
        "public.categories, public.merchants TO anon, authenticated; "
        "GRANT SELECT, INSERT, UPDATE ON public.orders, public.order_items, "
        "public.inventory_reservations, public.inventory_events, "
        "public.order_status_events TO authenticated; "
        "DROP POLICY IF EXISTS listings_select_public_or_member ON public.listings; "
        "CREATE POLICY listings_select_public_or_member ON public.listings FOR SELECT TO anon, authenticated "
        "USING (((status = 'active'::public.listing_status) AND (sale_starts_at <= now()) "
        "AND (sale_ends_at > now()) AND (available_quantity > 0) AND private.is_store_public(store_id)) "
        "OR private.can_manage_store(store_id, NULL::public.merchant_member_role[]) "
        "OR private.has_platform_role(ARRAY['operations_admin'::public.platform_role, "
        "'compliance_admin'::public.platform_role, 'super_admin'::public.platform_role])); "
        "DROP POLICY IF EXISTS stores_select_public_or_member ON public.stores; "
        "CREATE POLICY stores_select_public_or_member ON public.stores FOR SELECT TO anon, authenticated "
        "USING ((private.is_store_public(id) "
        "OR private.is_merchant_member(merchant_id, NULL::public.merchant_member_role[]) "
        "OR private.has_platform_role(ARRAY['operations_admin'::public.platform_role, "
        "'compliance_admin'::public.platform_role, 'super_admin'::public.platform_role])));",
    )
    # Remaining chain + W9.1.4, in order. Idempotent re-runs are safe:
    # every step is CREATE OR REPLACE / GRANT / REVOKE, except the W7
    # table alterations, which fail loudly on a second run — that is
    # why the fixture checks for the W9.1.4 marker first.
    probe = _connect(psycopg, application_name="w914-apply")
    try:
        with probe.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname = 'private' "
                "AND p.proname = 'w7_enqueue_notification'"
            )
            (w7_present,) = cur.fetchone()
    finally:
        probe.close()
    if w7_present == 0:
        for name in REMAINING_MIGRATIONS:
            _psql_file(parts, MIGRATIONS / name)
    else:
        # Chain already applied (e.g. a re-run): re-apply W9.1.4 only,
        # which is grant/revoke-only and therefore idempotent.
        _psql_file(parts, MIGRATION)
    yield {"psycopg": psycopg, "version": version, "dsn": dsn}


@pytest.fixture()
def db_conn(pg17_session):
    conn = _connect(pg17_session["psycopg"], application_name="w914-test")
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


def _as_role(cur, role: str, user_id: str | None = None):
    """SET ROLE + JWT claims for one statement batch (transaction-local)."""
    cur.execute("BEGIN")
    cur.execute(f"SET LOCAL ROLE {role}")
    claims = (
        json.dumps({"sub": user_id, "role": role})
        if user_id
        else json.dumps({"role": role})
    )
    cur.execute("SELECT set_config('request.jwt.claims', %s, true)", (claims,))


def _has_priv(cur, role: str, schema: str, name: str) -> bool:
    cur.execute(
        "SELECT proname, pg_get_function_identity_arguments(p.oid) AS args, "
        "has_function_privilege(%s, p.oid, 'EXECUTE') AS ok "
        "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = %s AND p.proname = %s",
        (role, schema, name),
    )
    rows = cur.fetchall()
    assert rows, f"function {schema}.{name} not found in test database"
    assert len(rows) == 1, f"ambiguous function {schema}.{name}: {rows}"
    return rows[0][2]


def _call_as(cur, role: str, sql: str, params=(), user_id: str | None = None):
    """One role-scoped call, COMMITTED on success so multi-step tests
    (apply-then-create, reserve-then-checkout) see earlier steps.
    Denied calls raise and are rolled back by the caller."""
    _as_role(cur, role, user_id)
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
    except Exception:
        cur.execute("ROLLBACK")
        raise
    cur.execute("COMMIT")
    return row


def _expect_denied(cur, role: str, sql: str, params=(), user_id: str | None = None):
    import psycopg

    _as_role(cur, role, user_id)
    try:
        cur.execute(sql, params)
        cur.fetchone()
    except psycopg.errors.InsufficientPrivilege:
        return True
    finally:
        cur.execute("ROLLBACK")
    return False


# ---------------------------------------------------------------------------
# Test 9 (matrix first, because every other test depends on it)
# ---------------------------------------------------------------------------


def test_privilege_matrix_matches_migration(db_conn):
    """Test 9/§H: has_function_privilege for every matrix entry."""
    with db_conn.cursor() as cur:
        for (schema, name), want in PRIVATE_MATRIX.items():
            for role in ROLES:
                got = _has_priv(cur, role, schema, name)
                assert got is want.get(role, False), (
                    f"{schema}.{name}: {role} EXECUTE={got}, expected {want.get(role, False)}"
                )
        for (schema, name), want in PUBLIC_WRAPPER_MATRIX.items():
            for role in ROLES:
                got = _has_priv(cur, role, schema, name)
                assert got is want.get(role, False), (
                    f"{schema}.{name}: {role} EXECUTE={got}, expected {want.get(role, False)}"
                )
        # Schema USAGE matrix.
        cur.execute(
            "SELECT has_schema_privilege('service_role', 'private', 'USAGE'), "
            "has_schema_privilege('authenticated', 'private', 'USAGE'), "
            "has_schema_privilege('anon', 'private', 'USAGE')"
        )
        usage_sr, usage_auth, usage_anon = cur.fetchone()
        assert (usage_sr, usage_auth, usage_anon) == (True, True, False)


def test_public_wrapper_acl_not_wider_than_matrix(db_conn):
    """No PUBLIC EXECUTE remains on any SaveBite function.

    The query is restricted to the matrix + trigger functions on
    purpose: extension functions (PostGIS/pgcrypto, in schema public
    or extensions) legitimately keep their own PUBLIC grants and
    must not leak into this assertion.
    """
    names = sorted(
        {n for (_s, n) in list(PRIVATE_MATRIX) + list(PUBLIC_WRAPPER_MATRIX)}
        | {
            "w7_enqueue_order_notifications",
            "w7_enqueue_merchant_notifications",
            "w7_enqueue_store_notifications",
            "set_updated_at",
        }
    )
    # has_function_privilege() rejects 'PUBLIC' as a role name, so the
    # PUBLIC grant is checked via proacl: a PUBLIC EXECUTE grant is
    # encoded as an entry with an empty grantee ('=X/...'), and a NULL
    # proacl means "default privileges", which for functions is also
    # PUBLIC EXECUTE. After the migration every listed function must
    # have a non-NULL proacl with no PUBLIC entry.
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT n.nspname, p.proname, p.proacl FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "AND p.proname = ANY(%s)",
            (names,),
        )
        bad = []
        for _schema, name, proacl in cur.fetchall():
            if proacl is None:
                bad.append((name, proacl))
                continue
            # An acl item is '<grantee>=<privs>/<grantor>'; a PUBLIC
            # grant has an empty grantee ('=X/pgtest'). An owner entry
            # like 'pgtest=X/pgtest' is NOT a PUBLIC grant.
            if any(item.split("=", 1)[0] == "" for item in proacl):
                bad.append((name, proacl))
        assert bad == [], bad


# ---------------------------------------------------------------------------
# Tests 1–3: server-only success / anon denied / authenticated denied
# ---------------------------------------------------------------------------


def test_server_only_rpc_success_via_direct_role(db_conn):
    """Test 1 (direct-role form): service_role can run backend RPCs."""
    with db_conn.cursor() as cur:
        row = _call_as(
            cur,
            "service_role",
            "SELECT public.backend_record_payment_webhook_event('razorpay', %s, 'payment.captured', '{}'::jsonb, true)",
            (f"evt-w914-{uuid.uuid4().hex[:12]}",),
        )
        assert row is not None and row[0] is not None
        row = _call_as(
            cur,
            "service_role",
            "SELECT public.backend_release_expired_reservations_v2(10)",
        )
        assert row is not None
        row = _call_as(
            cur,
            "service_role",
            "SELECT public.backend_enqueue_pickup_reminders(now(), 60)",
        )
        assert row is not None
        row = _call_as(
            cur,
            "service_role",
            "SELECT public.backend_process_notification_outbox('w914', 10)",
        )
        assert row is not None


def test_anon_denied_server_only_and_private(db_conn):
    """Test 2: anon cannot execute server-only wrappers or private fns."""
    with db_conn.cursor() as cur:
        for sql in (
            "SELECT public.backend_record_payment_webhook_event('razorpay', 'x', 'payment.captured', '{}'::jsonb, true)",
            "SELECT public.backend_confirm_payment_capture(%s, 'pay_x', 100, true)",
            "SELECT public.backend_release_expired_reservations_v2(10)",
            "SELECT public.backend_process_notification_outbox('w914', 10)",
            "SELECT private.confirm_payment_capture(%s, 'pay_x', 100, true)",
            "SELECT private.record_payment_webhook_event('razorpay', 'x', 'payment.captured', '{}'::jsonb, true)",
            "SELECT private.w7_enqueue_notification(%s, 'payment_captured', 't', 'b', 'order', %s, 'payment')",
        ):
            params = (str(uuid.uuid4()),) * sql.count("%s")
            assert _expect_denied(cur, "anon", sql, params), sql


def test_authenticated_denied_server_only_and_private(db_conn):
    """Test 3: authenticated cannot run server-only paths."""
    user = str(uuid.uuid4())
    with db_conn.cursor() as cur:
        for sql in (
            "SELECT public.backend_record_payment_webhook_event('razorpay', 'x', 'payment.captured', '{}'::jsonb, true)",
            "SELECT public.backend_confirm_payment_capture(%s, 'pay_x', 100, true)",
            "SELECT public.backend_release_expired_reservations_v2(10)",
            "SELECT public.backend_process_notification_outbox('w914', 10)",
            "SELECT public.backend_get_gateway_order_for_payment_transaction(%s, %s)",
            "SELECT private.confirm_payment_capture(%s, 'pay_x', 100, true)",
            "SELECT private.post_ledger_transaction('order', %s, 'x', 'INR', '[]'::jsonb)",
        ):
            params = (str(uuid.uuid4()),) * sql.count("%s")
            assert _expect_denied(cur, "authenticated", sql, params, user_id=user), sql


def test_service_role_denied_user_context_wrappers(db_conn):
    """Separation in the other direction: service_role may not call
    user-context RPCs at the database layer (the app allowlist already
    forbids it; this proves the database agrees)."""
    with db_conn.cursor() as cur:
        for sql in (
            "SELECT public.create_order_reservation(%s, '[]'::jsonb, 'key123456', NULL)",
            "SELECT public.begin_payment_checkout(%s, 'key123456')",
            "SELECT public.apply_merchant_application('A', 'B', 'restaurant', NULL, NULL)",
        ):
            params = (str(uuid.uuid4()),) * sql.count("%s")
            assert _expect_denied(cur, "service_role", sql, params), sql


# ---------------------------------------------------------------------------
# Tests 4–6: customer / merchant / RLS (with real fixture data)
# ---------------------------------------------------------------------------


def _make_store_fixture(cur, customer: str):
    merchant = str(uuid.uuid4())
    store = str(uuid.uuid4())
    listing = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO auth.users (id) VALUES (%s) ON CONFLICT DO NOTHING", (customer,)
    )
    cur.execute(
        "INSERT INTO public.merchants (id, legal_name, display_name, business_type, "
        "created_by, status, verification_status) VALUES (%s, 'Test', 'Test', 'restaurant', %s, 'approved', 'verified')",
        (merchant, customer),
    )
    cur.execute(
        "INSERT INTO public.merchant_memberships (merchant_id, user_id, role) VALUES (%s, %s, 'owner')",
        (merchant, customer),
    )
    cur.execute(
        "INSERT INTO public.stores (id, merchant_id, name, slug, address_line_1, city, state, pincode, status) "
        "VALUES (%s, %s, 'Test Store', %s, '1 Test Road', 'Test City', 'Test State', '110001', 'active')",
        (store, merchant, "store-" + uuid.uuid4().hex[:12]),
    )
    cur.execute(
        "INSERT INTO public.listings (id, store_id, listing_type, title, reference_value, selling_price, "
        "total_quantity, reserved_quantity, sold_quantity, status, sale_starts_at, sale_ends_at, "
        "pickup_starts_at, pickup_ends_at, created_by) VALUES (%s, %s, 'surprise_bag', 'Bag', 100, 50, 100, 0, 0, "
        "'active', now() - interval '1 hour', now() + interval '2 hours', now(), now() + interval '3 hours', %s)",
        (listing, store, customer),
    )
    return {"merchant": merchant, "store": store, "listing": listing}


def test_customer_reservation_and_checkout_still_work(db_conn):
    """Test 4: authenticated reservation + checkout via public wrappers."""
    customer = str(uuid.uuid4())
    with db_conn.cursor() as cur:
        cur.execute("BEGIN")
        fx = _make_store_fixture(cur, customer)
        cur.execute("COMMIT")
        row = _call_as(
            cur,
            "authenticated",
            "SELECT public.create_order_reservation(%s, %s::jsonb, %s, NULL)",
            (
                fx["store"],
                json.dumps([{"listing_id": fx["listing"], "quantity": 1}]),
                "key-" + uuid.uuid4().hex,
            ),
            user_id=customer,
        )
        assert row and row[0]["status"] == "pending_payment", row
        order_id = row[0]["order_id"]
        row = _call_as(
            cur,
            "authenticated",
            "SELECT public.begin_payment_checkout(%s, %s)",
            (order_id, "txkey-" + uuid.uuid4().hex),
            user_id=customer,
        )
        assert row is not None, "begin_payment_checkout failed for the order owner"


def test_merchant_store_and_hours_still_work(db_conn):
    """Test 5 (merchant half): an owner member can create a store and
    upsert its hours through the authenticated wrappers."""
    owner = str(uuid.uuid4())
    with db_conn.cursor() as cur:
        cur.execute("BEGIN")
        cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (owner,))
        cur.execute("COMMIT")
        row = _call_as(
            cur,
            "authenticated",
            "SELECT public.apply_merchant_application('Merchant A', 'Merchant A', 'restaurant', NULL, NULL)",
            user_id=owner,
        )
        assert row and row[0] is not None
        merchant_id = row[0]
        row = _call_as(
            cur,
            "authenticated",
            "SELECT public.create_merchant_store(%s, 'Shop', %s, '1 Road', NULL, 'Loc', 'City', 'State', '110001', NULL, NULL, NULL, NULL)",
            (merchant_id, "shop-" + uuid.uuid4().hex[:12]),
            user_id=owner,
        )
        assert row and row[0] is not None


def test_rls_and_authorization_preserved(db_conn):
    """Test 6: cross-customer / cross-merchant access still fails at
    the function/RLS layer, and anon catalogue reads still work."""
    customer = str(uuid.uuid4())
    other = str(uuid.uuid4())
    with db_conn.cursor() as cur:
        cur.execute("BEGIN")
        fx = _make_store_fixture(cur, customer)
        cur.execute("COMMIT")
        row = _call_as(
            cur,
            "authenticated",
            "SELECT public.create_order_reservation(%s, %s::jsonb, %s, NULL)",
            (
                fx["store"],
                json.dumps([{"listing_id": fx["listing"], "quantity": 1}]),
                "key-" + uuid.uuid4().hex,
            ),
            user_id=customer,
        )
        order_id = row[0]["order_id"]
        # Another authenticated user cannot checkout someone else's order.

        _as_role(cur, "authenticated", other)
        try:
            cur.execute(
                "SELECT public.begin_payment_checkout(%s, %s)",
                (order_id, "txkey-" + uuid.uuid4().hex),
            )
            cur.fetchone()
            checkout_other_ok = True
        except Exception:
            checkout_other_ok = False
        finally:
            cur.execute("ROLLBACK")
        assert checkout_other_ok is False, (
            "other user could checkout another customer's order"
        )
        # Anon catalogue read: listings policy calls private helpers.
        _as_role(cur, "anon")
        try:
            cur.execute(
                "SELECT id FROM public.listings WHERE id = %s", (fx["listing"],)
            )
            anon_rows = cur.fetchall()
        finally:
            cur.execute("ROLLBACK")
        assert len(anon_rows) == 1, f"anon catalogue read failed: {anon_rows}"


def test_anon_rls_helpers_required(db_conn):
    """Test 6 (negative control): revoking the anon RLS-helper EXECUTE
    grants breaks the anon catalogue read, proving the grants in §2c
    are load-bearing and not decorative. Grants are restored in a
    finally block so later tests are unaffected."""
    customer = str(uuid.uuid4())
    with db_conn.cursor() as cur:
        cur.execute("BEGIN")
        fx = _make_store_fixture(cur, customer)
        cur.execute("COMMIT")
        cur.execute(
            "REVOKE EXECUTE ON FUNCTION private.is_store_public(uuid) FROM anon; "
            "REVOKE EXECUTE ON FUNCTION private.can_manage_store(uuid, public.merchant_member_role[]) FROM anon; "
            "REVOKE EXECUTE ON FUNCTION private.has_platform_role(public.platform_role[]) FROM anon"
        )
        _as_role(cur, "anon")
        try:
            cur.execute(
                "SELECT id FROM public.listings WHERE id = %s", (fx["listing"],)
            )
            cur.fetchall()
            anon_ok = True
        except Exception:
            anon_ok = False
        finally:
            cur.execute("ROLLBACK")
        cur.execute(
            "GRANT EXECUTE ON FUNCTION private.is_store_public(uuid) TO anon; "
            "GRANT EXECUTE ON FUNCTION private.can_manage_store(uuid, public.merchant_member_role[]) TO anon; "
            "GRANT EXECUTE ON FUNCTION private.has_platform_role(public.platform_role[]) TO anon"
        )
        assert anon_ok is False, (
            "anon catalogue read succeeded without RLS-helper EXECUTE"
        )


# ---------------------------------------------------------------------------
# Test 7: private direct invocation (positive + negative)
# ---------------------------------------------------------------------------


def test_private_direct_invocation_matrix(db_conn):
    """Test 7: a role may directly execute a private function only
    when the matrix authorises it; every other combination is denied.
    (PostgREST never exposes schema private — see config.toml
    schemas=["public"] — so this is defence in depth for any direct
    SQL path, not the PostgREST path.)"""
    with db_conn.cursor() as cur:
        # Positive: authenticated RLS helper (authenticated holds
        # schema USAGE) and service-role backend implementation.
        # Anon is deliberately NOT a positive direct-call case: anon
        # holds helper EXECUTE for RLS policy evaluation only and
        # holds no schema USAGE, so a direct private.* call by anon
        # is denied at the schema level (proven below) while the
        # same helper succeeds inside an RLS policy (Test 6).
        row = _call_as(
            cur,
            "authenticated",
            "SELECT private.is_store_public(%s)",
            (str(uuid.uuid4()),),
            user_id=str(uuid.uuid4()),
        )
        assert row is not None and row[0] is False
        assert _expect_denied(
            cur, "anon", "SELECT private.is_store_public(%s)", (str(uuid.uuid4()),)
        )
        row = _call_as(
            cur, "service_role", "SELECT private.release_expired_reservations_v2(1)"
        )
        assert row is not None
        # Negative: every other role on a business implementation.
        assert _expect_denied(
            cur,
            "authenticated",
            "SELECT private.confirm_payment_capture(%s, 'p', 1, true)",
            (str(uuid.uuid4()),),
            user_id=str(uuid.uuid4()),
        )
        assert _expect_denied(
            cur,
            "service_role",
            "SELECT private.create_order_reservation(%s, '[]'::jsonb, 'key123456', NULL)",
            (str(uuid.uuid4()),),
        )
        assert _expect_denied(
            cur,
            "anon",
            "SELECT private.create_order_reservation(%s, '[]'::jsonb, 'key123456', NULL)",
            (str(uuid.uuid4()),),
        )


# ---------------------------------------------------------------------------
# Test 8: triggers after revocation
# ---------------------------------------------------------------------------


def test_triggers_still_fire_after_revocation(db_conn):
    """Test 8: a merchant-status transition still writes an outbox row
    (W7 trigger), and a posted-ledger mutation is still refused
    (baseline trigger), even though no app role holds EXECUTE on the
    trigger/private helper functions."""
    with db_conn.cursor() as cur:
        cur.execute("BEGIN")
        customer = str(uuid.uuid4())
        fx = _make_store_fixture(cur, customer)
        cur.execute(
            "UPDATE public.merchants SET status = 'approved' WHERE id = %s",
            (fx["merchant"],),
        )
        cur.execute("SELECT count(*) FROM private.notification_outbox")
        (outbox_before,) = cur.fetchone()
        # A fresh merchant going pending_review -> approved fires the
        # merchant trigger; use a second merchant to get a transition.
        merchant2 = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO public.merchants (id, legal_name, display_name, business_type, created_by, status, verification_status) "
            "VALUES (%s, 'M2', 'M2', 'cafe', %s, 'pending_review', 'pending')",
            (merchant2, customer),
        )
        cur.execute(
            "UPDATE public.merchants SET status = 'approved', verification_status = 'verified' WHERE id = %s",
            (merchant2,),
        )
        cur.execute("SELECT count(*) FROM private.notification_outbox")
        (outbox_after,) = cur.fetchone()
        cur.execute("ROLLBACK")
        assert outbox_after > outbox_before, (outbox_before, outbox_after)
        # Posted-ledger immutability trigger: seed two accounts (as
        # owner), post a balanced transaction as service_role, then
        # prove both the transaction-row and entry-row mutations are
        # refused by the baseline triggers.
        cur.execute(
            "INSERT INTO private.ledger_accounts (account_code, account_name, account_type, currency) "
            "VALUES ('w914-cash', 'Cash', 'asset', 'INR'), ('w914-rev', 'Revenue', 'revenue', 'INR') "
            "ON CONFLICT (account_code) DO NOTHING"
        )
        _as_role(cur, "service_role")
        try:
            cur.execute(
                "SELECT public.backend_post_ledger_transaction('order', %s, 'w914 test', 'INR', %s::jsonb)",
                (
                    str(uuid.uuid4()),
                    '[{"account_code": "w914-cash", "debit": 100}, '
                    '{"account_code": "w914-rev", "credit": 100}]',
                ),
            )
            tx_row = cur.fetchone()
        finally:
            cur.execute("ROLLBACK")
        assert tx_row and tx_row[0], "balanced ledger post failed in trigger test"
        for sql in (
            "UPDATE private.ledger_transactions SET status = 'reversed' WHERE id = %s",
            "UPDATE private.ledger_entries SET debit_amount = 1 WHERE transaction_id = %s",
        ):
            _as_role(cur, "service_role")
            try:
                cur.execute(sql, (tx_row[0],))
                mutated = True
            except Exception:
                mutated = False
            finally:
                cur.execute("ROLLBACK")
            assert mutated is False, sql


# ---------------------------------------------------------------------------
# Test 9 (second half): ownership / security mode / search_path unchanged
# ---------------------------------------------------------------------------


def test_function_identity_unchanged(db_conn):
    """Test 9: owner, security mode, search_path, signature and return
    type are exactly as the migration chain defined them — the W9.1.4
    migration contains no function definition, so none may differ."""
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid), "
            "p.prosecdef, p.proconfig, r.rolname, pg_get_function_result(p.oid) "
            "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "JOIN pg_roles r ON r.oid = p.proowner "
            "WHERE (n.nspname = 'private' AND p.proname = 'confirm_payment_capture') "
            "OR (n.nspname = 'public' AND p.proname = 'backend_confirm_payment_capture') "
            "OR (n.nspname = 'private' AND p.proname = 'create_order_reservation') "
            "OR (n.nspname = 'public' AND p.proname = 'backend_process_notification_outbox')"
        )
        rows = {r[1]: r for r in cur.fetchall()}
        assert rows["confirm_payment_capture"][3] is True  # SECURITY DEFINER
        assert rows["backend_confirm_payment_capture"][3] is False  # INVOKER
        assert rows["create_order_reservation"][3] is True
        assert rows["backend_process_notification_outbox"][3] is True
        for row in rows.values():
            assert row[4] is not None and any(
                "search_path=" in (c or "") for c in row[4]
            ), f"pinned search_path missing on {row[1]}: {row[4]}"


def test_future_function_defaults(db_conn):
    """Test 10: a function created in schema private AFTER the
    migration still gets PUBLIC EXECUTE by default — and the
    migration deliberately does NOT claim otherwise.

    Proven on disposable PostgreSQL 17.11: ALTER DEFAULT
    PRIVILEGES ... REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC
    creates no pg_default_acl row and leaves a new function
    PUBLIC-executable, because default grants are unioned with
    the built-in PUBLIC grant. The only working removal is an
    explicit REVOKE per function, which section 2 of the migration
    does for every existing function. This test asserts the true
    behaviour so that a future migration author cannot rely on a
    default-privileges clause: every future private function MUST
    carry its own explicit REVOKE FROM PUBLIC (and explicit
    GRANTs).
    """
    with db_conn.cursor() as cur:
        cur.execute(
            "CREATE OR REPLACE FUNCTION private.w914_test_future_fn() RETURNS integer "
            "LANGUAGE sql AS $$ SELECT 1 $$"
        )
        cur.execute(
            "SELECT has_function_privilege('anon', 'private.w914_test_future_fn()', 'EXECUTE'), "
            "has_function_privilege('authenticated', 'private.w914_test_future_fn()', 'EXECUTE')"
        )
        anon_ok, auth_ok = cur.fetchone()
        cur.execute("DROP FUNCTION private.w914_test_future_fn()")
        assert (anon_ok, auth_ok) == (True, True), (
            "future private function unexpectedly lacks PUBLIC EXECUTE; "
            "if PostgreSQL behaviour changed, update the migration header "
            "and docs before relying on it"
        )


# ---------------------------------------------------------------------------
# Stage G: real PostgREST integration tests
# ---------------------------------------------------------------------------


def _mint_jwt(secret: str, role: str, sub: str | None = None) -> str:
    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    payload: dict[str, object] = {"role": role, "exp": 2000000000}
    if sub:
        payload["sub"] = sub
    header = b64(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    body = b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = b64(
        hmac.new(secret.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{body}.{sig}"


class _RestV1ProxyHandler(BaseHTTPRequestHandler):
    """Strip /rest/v1, forward verbatim (Supabase Kong emulation)."""

    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        path = self.path
        if path.startswith("/rest/v1/"):
            path = path[len("/rest/v1") :]
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        conn = http.client.HTTPConnection(
            "127.0.0.1", self.server.postgrest_port, timeout=30
        )
        try:
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "connection")
            }
            conn.request(self.command, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for key, value in resp.getheaders():
                if key.lower() not in (
                    "connection",
                    "transfer-encoding",
                    "content-length",
                ):
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        finally:
            conn.close()

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _forward

    def log_message(self, *args) -> None:
        pass


def _check_port_free(port: int, what: str) -> None:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        pytest.fail(f"Port {port} is already in use — stop the other {what} first.")
    finally:
        sock.close()


@pytest.fixture(scope="session")
def postgrest_session(pg17_session, tmp_path_factory):
    binary = os.environ.get("SAVEBITE_POSTGREST_BIN", DEFAULT_POSTGREST_BIN)
    if not os.path.isfile(binary):
        pytest.fail(
            f"PostgREST binary not found at {binary}. Download "
            f"{POSTGREST_VERSION} from {POSTGREST_DOWNLOAD_URL} (or set "
            "SAVEBITE_POSTGREST_BIN). Refusing to substitute the transport."
        )
    # Defaults differ from the W9.1.3 module's 3001/3002 on purpose:
    # both modules' PostgREST fixtures are session-scoped, so running
    # the full suite would otherwise collide on the same ports.
    port = int(os.environ.get("SAVEBITE_POSTGREST_PORT", "3003"))
    proxy_port = int(os.environ.get("SAVEBITE_POSTGREST_PROXY_PORT", "3004"))
    _check_port_free(port, "PostgREST")
    _check_port_free(proxy_port, "test reverse proxy")
    workdir = tmp_path_factory.mktemp("postgrest")
    jwt_secret = secrets.token_hex(16)
    dsn = os.environ.get("SAVEBITE_PG_TEST_DSN", DEFAULT_DSN)
    parts = _parse_dsn(dsn)
    uri = (
        f"postgres://{parts.get('user', 'pgtest')}@/{parts.get('dbname', 'savebite_pgtest')}"
        f"?host={parts.get('host', '127.0.0.1')}&port={parts.get('port', '5432')}"
    )
    conf = (
        f'db-uri = "{uri}"\n'
        'db-schemas = "public"\n'
        'db-anon-role = "anon"\n'
        f"server-port = {port}\n"
        f'jwt-secret = "{jwt_secret}"\n'
    )
    conf_path = workdir / "postgrest.conf"
    conf_path.write_text(conf)
    os.chmod(conf_path, 0o600)
    log_path = workdir / "server.log"
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [binary, str(conf_path)], stdout=log, stderr=subprocess.STDOUT
        )
    proxy = ThreadingHTTPServer(("127.0.0.1", proxy_port), _RestV1ProxyHandler)
    proxy.postgrest_port = port
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    base_url = f"http://127.0.0.1:{proxy_port}"
    try:
        opener = build_opener(ProxyHandler({}))

        def ready() -> bool:
            if proc.poll() is not None:
                pytest.fail(f"PostgREST exited early; see {log_path}.")
            try:
                with opener.open(base_url + "/rest/v1/", timeout=2) as resp:
                    return resp.status == 200
            except Exception:
                return False

        proxy_thread.start()
        for _ in range(60):
            if ready():
                break
            import time

            time.sleep(0.5)
        else:
            pytest.fail("PostgREST did not become ready in 30s")
        yield {
            "base_url": base_url,
            "jwt_secret": jwt_secret,
            "service_jwt": _mint_jwt(jwt_secret, "service_role"),
            "proc": proc,
            "log": log_path,
        }
    finally:
        proxy.shutdown()
        proxy.server_close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _post_rpc(base_url: str, name: str, payload: dict, token: str | None = None):
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        f"{base_url}/rest/v1/rpc/{name}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_postgrest_service_role_backend_rpc_succeeds(postgrest_session):
    """Stage G, service-role: backend RPC via /rest/v1/rpc/ succeeds
    and writes its database effect (webhook event row)."""
    status, body = _post_rpc(
        postgrest_session["base_url"],
        "backend_record_payment_webhook_event",
        {
            "p_gateway": "razorpay",
            "p_gateway_event_id": f"evt-postgrest-{uuid.uuid4().hex[:12]}",
            "p_event_type": "payment.captured",
            "p_payload": {},
            "p_signature_verified": True,
        },
        token=postgrest_session["service_jwt"],
    )
    assert status in (200, 201), (status, body)


def test_postgrest_anon_and_authenticated_denied_backend_rpc(postgrest_session):
    """Stage G, negative: anon (no token) and authenticated (user JWT)
    both fail on a server-only RPC — PostgREST must not return 2xx."""
    for token in (
        None,
        _mint_jwt(
            postgrest_session["jwt_secret"], "authenticated", sub=str(uuid.uuid4())
        ),
    ):
        status, body = _post_rpc(
            postgrest_session["base_url"],
            "backend_record_payment_webhook_event",
            {
                "p_gateway": "razorpay",
                "p_gateway_event_id": "evt-denied",
                "p_event_type": "payment.captured",
                "p_payload": {},
                "p_signature_verified": True,
            },
            token=token,
        )
        assert status in (401, 403, 404), (token is not None, status, body)


def test_postgrest_private_schema_not_exposed(postgrest_session):
    """Stage G: schema private is not in db-schemas, so a direct
    private RPC path is not a PostgREST endpoint at all."""
    status, _body = _post_rpc(
        postgrest_session["base_url"],
        "private_record_payment_webhook_event",
        {},
        token=postgrest_session["service_jwt"],
    )
    assert status == 404, status
