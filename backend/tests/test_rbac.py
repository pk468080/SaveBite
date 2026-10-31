from uuid import UUID

import pytest

from app.errors import AuthorizationError
from app.rbac import (
    get_merchant_roles,
    get_platform_roles,
    get_store_roles,
    require_merchant_role,
    require_platform_role,
    reviewer_id_for,
    strip_caller_supplied_reviewer,
)
from app.schemas import AuthenticatedUser, MerchantMemberRole, PlatformRole
from tests.conftest import FakeSupabaseClient

USER = AuthenticatedUser(
    id=UUID("11111111-1111-4111-8111-111111111111"),
    email="test@example.com",
    token="tok",
)
MERCHANT = UUID("22222222-2222-4222-8222-222222222222")


@pytest.mark.asyncio
async def test_platform_roles_ignore_revoked_and_unknown():
    fake = FakeSupabaseClient(
        {
            "platform_user_roles": [
                {"role": "super_admin", "revoked_at": None},
                {"role": "not_a_role", "revoked_at": None},
            ]
        }
    )
    # The fake does not filter by revoked_at; get_platform_roles only
    # parses roles, so the unknown role is dropped and the valid one kept.
    roles = await get_platform_roles(USER, fake)
    assert roles == [PlatformRole.super_admin]


@pytest.mark.asyncio
async def test_merchant_roles_parsed():
    fake = FakeSupabaseClient(
        {
            "merchant_memberships": [
                {"role": "owner", "is_active": True},
                {"role": "finance_viewer", "is_active": True},
            ]
        }
    )
    roles = await get_merchant_roles(USER, fake, MERCHANT)
    assert MerchantMemberRole.owner in roles
    assert MerchantMemberRole.finance_viewer in roles


@pytest.mark.asyncio
async def test_revoked_platform_role_grants_nothing():
    fake = FakeSupabaseClient(
        {
            "platform_user_roles": [
                {"role": "super_admin", "revoked_at": "2026-10-31T00:00:00Z"},
            ]
        }
    )
    roles = await get_platform_roles(USER, fake)
    assert roles == []


@pytest.mark.asyncio
async def test_inactive_merchant_and_store_memberships_grant_nothing():
    fake = FakeSupabaseClient(
        {
            "merchant_memberships": [{"role": "owner", "is_active": False}],
            "store_staff_memberships": [{"role": "store_manager", "is_active": False}],
        }
    )
    assert await get_merchant_roles(USER, fake, MERCHANT) == []
    store_id = UUID("33333333-3333-4333-8333-333333333333")
    assert await get_store_roles(USER, fake, store_id) == []


@pytest.mark.asyncio
async def test_forbidden_when_required_platform_role_missing():
    fake = FakeSupabaseClient({"platform_user_roles": []})
    checker = require_platform_role(PlatformRole.super_admin)
    with pytest.raises(AuthorizationError):
        await checker(user=USER, client=fake)


@pytest.mark.asyncio
async def test_forbidden_when_required_merchant_role_missing():
    fake = FakeSupabaseClient({"merchant_memberships": []})
    checker = require_merchant_role(MerchantMemberRole.owner)
    with pytest.raises(AuthorizationError):
        await checker(merchant_id=MERCHANT, user=USER, client=fake)


@pytest.mark.asyncio
async def test_allowed_when_required_role_present():
    fake = FakeSupabaseClient(
        {"platform_user_roles": [{"role": "super_admin", "revoked_at": None}]}
    )
    checker = require_platform_role(PlatformRole.super_admin)
    result = await checker(user=USER, client=fake)
    assert result == USER


@pytest.mark.asyncio
async def test_merchant_and_store_queries_select_is_active():
    """The actual query must request role,is_active, not just role:
    the Python-side inactive check reads is_active, and PostgREST
    only returns selected columns."""
    fake = FakeSupabaseClient(
        {
            "merchant_memberships": [{"role": "owner", "is_active": True}],
            "store_staff_memberships": [{"role": "store_manager", "is_active": True}],
        }
    )
    await get_merchant_roles(USER, fake, MERCHANT)
    store_id = UUID("33333333-3333-4333-8333-333333333333")
    await get_store_roles(USER, fake, store_id)
    selects = {table: select for table, select, _ in fake.query_calls}
    assert selects["merchant_memberships"] == "role,is_active"
    assert selects["store_staff_memberships"] == "role,is_active"


@pytest.mark.asyncio
async def test_fake_respects_select_columns():
    """Realistic PostgREST response data: stored rows carry extra
    columns, but the fake must return only the selected ones."""
    fake = FakeSupabaseClient(
        {
            "merchant_memberships": [
                {
                    "role": "owner",
                    "is_active": True,
                    "merchant_id": str(MERCHANT),
                    "created_at": "2026-10-31T00:00:00Z",
                }
            ]
        }
    )
    rows = await fake.query("merchant_memberships", select="role,is_active")
    assert rows == [{"role": "owner", "is_active": True}]
    rows = await fake.query("merchant_memberships", select="role")
    assert rows == [{"role": "owner"}]


@pytest.mark.asyncio
async def test_inactive_memberships_filtered_with_realistic_data():
    """Inactive rows still grant nothing when the response contains
    only the selected role,is_active columns, as real PostgREST
    would return them."""
    fake = FakeSupabaseClient(
        {
            "merchant_memberships": [
                {
                    "role": "owner",
                    "is_active": False,
                    "merchant_id": str(MERCHANT),
                }
            ],
            "store_staff_memberships": [
                {
                    "role": "store_manager",
                    "is_active": False,
                    "store_id": "33333333-3333-4333-8333-333333333333",
                }
            ],
        }
    )
    assert await get_merchant_roles(USER, fake, MERCHANT) == []
    store_id = UUID("33333333-3333-4333-8333-333333333333")
    assert await get_store_roles(USER, fake, store_id) == []


def test_reviewer_id_is_always_the_authenticated_user():
    assert reviewer_id_for(USER) == str(USER.id)


def test_caller_supplied_reviewer_is_stripped():
    payload = {
        "p_merchant_id": str(MERCHANT),
        "p_reviewer_id": "attacker-supplied-id",
        "p_actor_user_id": "attacker-supplied-id",
        "p_new_status": "approved",
    }
    cleaned = strip_caller_supplied_reviewer(payload)
    assert "p_reviewer_id" not in cleaned
    assert "p_actor_user_id" not in cleaned
    assert cleaned["p_new_status"] == "approved"
    # Original payload is not mutated.
    assert payload["p_reviewer_id"] == "attacker-supplied-id"
