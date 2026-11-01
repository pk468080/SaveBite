"""W9.1 migration-consistency tests (no live database).

These tests prove the reservation-expiry migration file says
what the W9.1 fix claims: a new tiered, bounded, idempotent
v2 cleanup that frees stock for abandoned checkouts without
ever touching money states, with service-role-only EXECUTE.
Like the B1 tests, they parse with pglast and assert on
file contents only. They do NOT prove the migration
applies to live or behaves correctly under Postgres
concurrency — there is no Postgres in this environment —
so apply-time behaviour (including the
has_function_privilege check) and live concurrency proof
are reported honestly in the PR, not claimed here.
"""

from pathlib import Path

import pglast

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
EXPIRY = MIGRATIONS / "20261101200000_w91_reservation_expiry.sql"
SIGNATURE = "public.backend_release_expired_reservations_v2(integer)"


def _text() -> str:
    return EXPIRY.read_text()


def test_w91_migration_file_exists_and_parses():
    assert EXPIRY.exists(), f"missing migration: {EXPIRY.name}"
    assert pglast.parse_sql(_text()), EXPIRY.name


def test_w91_v2_signatures_and_return_shape():
    text = _text()
    assert "create or replace function private.release_expired_reservations_v2(" in text
    assert (
        "create or replace function "
        "public.backend_release_expired_reservations_v2(" in text
    )
    assert "p_limit integer default 100" in text
    assert "returns jsonb" in text
    # Exactly the three counters — no order ids, amounts,
    # or payment fields leak through the RPC result.
    for field in (
        "'released'",
        "'orders_expired'",
        "'orders_preserved_reconciliation'",
    ):
        assert field in text, field
    assert "gateway_payment_id" not in text
    assert "gateway_order_id" not in text


def test_w91_private_is_definer_pinned_and_qualified():
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


def test_w91_hard_block_never_touches_money_states():
    text = _text()
    # The exclusion is exactly these four money states.
    # 'created' and 'failed' must NOT be in it: that is
    # the whole fix (abandoned checkouts hold 'created'
    # forever), and 'reconciliation_required' must NOT be
    # in it either: it has its own preserve branch below.
    assert (
        "p.status in ('authorized', 'captured', 'refunded', 'partially_refunded')"
        in text
    )
    assert "p.status in ('created'" not in text
    assert "p.status in ('failed'" not in text
    assert "p.status in ('reconciliation_required'" not in text


def test_w91_reconciliation_orders_preserve_the_finance_flag():
    text = _text()
    assert "if v_has_reconciliation then" in text
    assert "'reservation_expired_reconciliation_pending'" in text
    # The order-expire update (which sets payment_status
    # to 'failed') must live in the else branch, so it
    # can never overwrite a reconciliation flag.
    else_pos = text.index("if v_has_reconciliation then")
    expire_pos = text.index(
        "update public.orders set status = 'expired', payment_status = 'failed'"
    )
    assert expire_pos > else_pos
    assert "where id = v_reservation.order_id and status = 'pending_payment'" in text


def test_w91_batch_is_bounded_and_concurrency_safe():
    text = _text()
    assert "p_limit < 1 or p_limit > 1000" in text
    assert "invalid_batch_limit" in text
    assert "for update of r skip locked" in text
    assert "limit p_limit" in text
    assert "order by r.expires_at" in text
    # Only already-expired, still-active rows are ever
    # selected, so a second run can never re-process a
    # released row, and only pending_payment orders close.
    assert "r.status = 'active'" in text
    assert "r.expires_at <= now()" in text
    assert "o.status = 'pending_payment'" in text
    assert "r.order_id = v_reservation.order_id and r.status = 'active'" in text


def test_w91_v1_functions_are_not_redefined():
    text = _text()
    assert (
        "create or replace function private.release_expired_inventory_reservations("
        not in text
    )
    assert (
        "create or replace function public.backend_release_expired_reservations("
        not in text
    )


def test_w91_grants_are_service_role_only():
    text = _text()
    for role in ("public", "anon", "authenticated"):
        assert f"revoke execute on function {SIGNATURE} from {role};" in text, role
    assert f"grant execute on function {SIGNATURE} to service_role;" in text


def test_w91_file_is_marked_not_applied():
    text = _text()
    assert "NOT APPLIED TO LIVE" in text
    assert "20261101190000" in text  # apply-order prerequisite


def test_w91_no_destructive_or_unrelated_statements():
    text = _text()
    for forbidden in ("drop ", "truncate ", "delete from", "create table"):
        assert forbidden not in text.lower(), forbidden
    # Exactly: private fn, public fn, 3 revokes, 1 grant.
    assert len(pglast.parse_sql(text)) == 6
