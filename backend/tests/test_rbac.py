from uuid import UUID

import pytest

from app.rbac import (
    get_merchant_roles,
    get_platform_roles,
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
        {"merchant_memberships": [{"role": "owner"}, {"role": "finance_viewer"}]}
    )
    roles = await get_merchant_roles(USER, fake, MERCHANT)
    assert MerchantMemberRole.owner in roles
    assert MerchantMemberRole.finance_viewer in roles


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
