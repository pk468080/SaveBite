import pytest

from app.config import Settings
from app.supabase_client import (
    BACKEND_RPCS,
    USER_CONTEXT_RPCS,
    RPCNotAllowedError,
    service_client,
    user_client,
)


def _settings(**overrides):
    defaults = {
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "publishable",
        "supabase_service_role_key": "service-role-secret",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_allowlist_contents_match_database_contract():
    assert USER_CONTEXT_RPCS == {
        "apply_merchant_application",
        "create_merchant_store",
        "upsert_store_hours",
        "create_order_reservation",
        "begin_payment_checkout",
        "issue_pickup_token",
        "verify_pickup_token",
        "request_refund",
    }
    assert BACKEND_RPCS == {
        "backend_attach_gateway_order",
        "backend_mark_payment_failed",
        "backend_confirm_payment_capture",
        "backend_record_payment_webhook_event",
        "backend_release_expired_reservations",
        "backend_review_merchant",
        "backend_review_store",
        "backend_update_refund_status",
        "backend_post_ledger_transaction",
        "backend_reverse_ledger_transaction",
    }


@pytest.mark.asyncio
async def test_service_client_may_not_query_tables():
    client = service_client(_settings())
    with pytest.raises(RPCNotAllowedError):
        await client.query("listings")


@pytest.mark.asyncio
async def test_service_client_rejects_user_context_rpcs():
    client = service_client(_settings())
    for name in sorted(USER_CONTEXT_RPCS):
        with pytest.raises(RPCNotAllowedError):
            await client.rpc(name, {})
    with pytest.raises(RPCNotAllowedError):
        await client.rpc("some_unknown_rpc", {})


@pytest.mark.asyncio
async def test_user_client_rejects_backend_rpcs():
    client = user_client(_settings(), "user-token")
    for name in sorted(BACKEND_RPCS):
        with pytest.raises(RPCNotAllowedError):
            await client.rpc(name, {})
    with pytest.raises(RPCNotAllowedError):
        await client.rpc("backend_anything_new", {})


@pytest.mark.asyncio
async def test_user_client_rejects_unknown_rpcs():
    client = user_client(_settings(), "user-token")
    with pytest.raises(RPCNotAllowedError):
        await client.rpc("drop_table", {})


def test_validate_rpc_allows_correct_client_types_without_network():
    # validate_rpc runs before any HTTP call, so these pass offline.
    service = service_client(_settings())
    for name in BACKEND_RPCS:
        service.validate_rpc(name)
    user = user_client(_settings(), "user-token")
    for name in USER_CONTEXT_RPCS:
        user.validate_rpc(name)


@pytest.mark.asyncio
async def test_user_client_rejects_private_table_query():
    client = user_client(_settings(), "user-token")
    with pytest.raises(ValueError):
        await client.query("private.payment_transactions")
