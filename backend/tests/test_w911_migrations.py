"""W9.1.1 migration-consistency tests (no live database).

These tests prove the lock-order correction migration
says what the W9.1.1 fix claims: the v2 cleanup body is
replaced with an order-first body (order -> reservations
-> listings, the same relative order
confirm_payment_capture uses), with the same signature,
result shape, tier rules, batch bound, and
service-role-only entry grants — and nothing else.
Like the W9.1 tests, they parse with pglast and assert
on file contents only. They do NOT prove the migration
applies to live or behaves correctly under Postgres
concurrency — there is no Postgres in this environment —
so apply-time behaviour and live concurrency proof are
reported honestly in the PR, not claimed here.
"""

from pathlib import Path

import pglast

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
W911 = MIGRATIONS / "20261102210000_w911_cleanup_lock_order.sql"
SIGNATURE = "public.backend_release_expired_reservations_v2(integer)"


def _text() -> str:
    return W911.read_text()


def test_w911_migration_file_exists_and_parses():
    assert W911.exists(), f"missing migration: {W911.name}"
    assert pglast.parse_sql(_text()), W911.name


def test_w911_replaces_only_the_private_v2_function():
    text = _text()
    assert (
        "create or replace function private.release_expired_reservations_v2("
        in text
    )
    # The public wrapper keeps its W9.1 definition and
    # signature; this file must not redefine it, must
    # not touch the v1 functions, and must not add any
    # other function.
    assert text.count("create or replace function") == 1
    assert (
        "create or replace function "
        "public.backend_release_expired_reservations_v2(" not in text
    )
    assert (
        "create or replace function private.release_expired_inventory_reservations("
        not in text
    )
    assert (
        "create or replace function public.backend_release_expired_reservations("
        not in text
    )


def test_w911_preserves_signature_and_result_shape():
    text = _text()
    assert "p_limit integer default 100" in text
    assert "returns jsonb" in text
    for field in (
        "'released'",
        "'orders_expired'",
        "'orders_preserved_reconciliation'",
    ):
        assert field in text, field
    assert "gateway_payment_id" not in text
    assert "gateway_order_id" not in text


def test_w911_private_is_definer_pinned_and_qualified():
    text = _text()
    assert "security definer" in text
    assert "set search_path = ''" in text
    for qualified in (
        "public.inventory_reservations",
        "public.orders",
        "public.listings",
        "public.inventory_events",
        "public.order_status_events",
        "private.payment_transactions",
    ):
        assert qualified in text, qualified


def test_w911_lock_order_is_order_first():
    text = _text()
    # The order claim (SKIP LOCKED, deterministic id
    # order) must textually precede every reservation
    # lock: the function locks order -> reservations ->
    # listings, matching confirm_payment_capture's
    # payment -> order -> reservations -> listings.
    assert "for update of o skip locked" in text
    assert "order by o.id" in text
    assert "for update of r skip locked" in text
    assert text.index("for update of o skip locked") < text.index(
        "for update of r skip locked"
    )
    # The W9.1 reservation-first cursor is gone: no
    # single cursor locks reservations before any order.
    assert "for update of r skip locked" in text
    assert text.index("limit p_limit") < text.index("for update of o skip locked")


def test_w911_hard_block_and_tiers_preserved():
    text = _text()
    assert (
        "p.status in ('authorized', 'captured', 'refunded', 'partially_refunded')"
        in text
    )
    assert "p.status in ('created'" not in text
    assert "p.status in ('failed'" not in text
    assert "p.status in ('reconciliation_required'" not in text
    assert "'reservation_expired_reconciliation_pending'" in text
    # The order-expire update still sets payment_status
    # to 'failed' only in the non-reconciliation branch,
    # and only counts/logs when it actually changed a
    # row (W9.1 counted even a zero-row update).
    assert (
        "update public.orders set status = 'expired', payment_status = 'failed'"
        in text
    )
    assert "get diagnostics v_updated = row_count" in text
    assert "if v_updated > 0 then" in text


def test_w911_batch_is_bounded_and_idempotent():
    text = _text()
    assert "p_limit < 1 or p_limit > 1000" in text
    assert "invalid_batch_limit" in text
    assert "limit p_limit" in text
    assert "v_released >= p_limit" in text
    assert "exit claim_loop" in text
    assert "r.status = 'active'" in text
    assert "r.expires_at <= now()" in text
    assert "o.status = 'pending_payment'" in text
    assert "r.order_id = v_order.id and r.status = 'active'" in text


def test_w911_grants_are_service_role_only():
    text = _text()
    for role in ("public", "anon", "authenticated"):
        assert f"revoke execute on function {SIGNATURE} from {role};" in text, role
    assert f"grant execute on function {SIGNATURE} to service_role;" in text


def test_w911_file_is_marked_not_applied():
    text = _text()
    assert "NOT APPLIED TO LIVE" in text
    assert "20261101200000" in text  # apply-order prerequisite


def test_w911_no_destructive_or_unrelated_statements():
    text = _text()
    for forbidden in (
        "drop ",
        "truncate ",
        "delete from",
        "create table",
        "alter table",
        "create policy",
        "drop policy",
    ):
        assert forbidden not in text.lower(), forbidden
    # Exactly: private fn replacement + 3 revokes + 1 grant.
    assert len(pglast.parse_sql(text)) == 5
