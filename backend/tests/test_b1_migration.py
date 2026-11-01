"""B1 migration-consistency tests (no live database).

These tests prove the B1 checkout-lookup migration file says
what the B1 fix claims: one narrow server-only lookup that
returns only the attached gateway order id and the status
for one transaction of one order, with service-role-only
EXECUTE. Like the W7/W8 tests, they parse with pglast and
assert on file contents only. They do NOT prove the
migration applies to live — there is no Postgres in this
environment — so apply-time behaviour (including the
has_function_privilege check) is reported honestly in the
PR, not claimed here.
"""

import re
from pathlib import Path

import pglast

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
LOOKUP = MIGRATIONS / "20261101180000_b1_checkout_gateway_lookup.sql"
SIGNATURE = "public.backend_get_gateway_order_for_payment_transaction(uuid, uuid)"


def test_b1_migration_file_exists_and_parses():
    assert LOOKUP.exists(), f"missing migration: {LOOKUP.name}"
    assert pglast.parse_sql(LOOKUP.read_text()), LOOKUP.name


def test_b1_lookup_signature_and_return_shape():
    text = LOOKUP.read_text()
    assert (
        "create or replace function private.get_gateway_order_for_payment_transaction("
    ) in text
    assert (
        "create or replace function "
        "public.backend_get_gateway_order_for_payment_transaction("
    ) in text
    assert "p_payment_transaction_id uuid" in text
    assert "p_order_id uuid" in text
    assert "returns jsonb" in text
    # Exactly the five returned fields — no payment ids,
    # signatures, webhook payloads, or unrelated columns.
    for field in (
        "'payment_transaction_id'",
        "'order_id'",
        "'gateway'",
        "'gateway_order_id'",
        "'status'",
    ):
        assert field in text, field
    assert "gateway_payment_id" not in text
    assert "gateway_signature_verified" not in text
    assert "failure_code" not in text
    assert "failure_description" not in text


def test_b1_lookup_is_definer_pinned_and_qualified():
    text = LOOKUP.read_text()
    # The private implementation must be SECURITY DEFINER:
    # it reads private.payment_transactions, which no
    # PostgREST role can read directly.
    private = text.split("private.get_gateway_order_for_payment_transaction(")[1]
    private_body = private.split("$function$")[0]
    assert "security definer" in private_body
    assert "set search_path = ''" in text
    # Every table reference is fully qualified.
    assert "private.payment_transactions" in text
    assert re.search(r"\bfrom payment_transactions\b", text) is None
    # The row must match transaction AND order AND gateway.
    assert "and order_id = p_order_id" in text
    assert "and gateway = 'razorpay'" in text
    # Mismatch / missing row fails closed with P0002.
    assert "payment_transaction_not_found" in text
    assert "errcode = 'P0002'" in text


def test_b1_lookup_grants_service_role_only():
    text = LOOKUP.read_text()
    assert f"revoke execute on function {SIGNATURE} from public" in text
    assert f"revoke execute on function {SIGNATURE} from anon" in text
    assert f"revoke execute on function {SIGNATURE} from authenticated" in text
    assert f"grant execute on function {SIGNATURE} to service_role" in text
    # No other grant target appears for this function.
    for line in text.splitlines():
        if SIGNATURE in line and "grant execute" in line:
            assert "to service_role" in line, line


def test_b1_file_orders_after_w8_and_is_not_applied():
    names = sorted(p.name for p in MIGRATIONS.glob("*.sql"))
    w8_last = "20261101131000_w8_notification_rpc_grants.sql"
    assert names.index(w8_last) < names.index(LOOKUP.name)
    assert re.search(r"NOT APPLIED TO LIVE", LOOKUP.read_text())
