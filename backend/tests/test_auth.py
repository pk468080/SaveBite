import pytest

from app import auth
from app.config import Settings
from app.errors import ServiceUnavailableError
from app.schemas import AuthenticatedUser


@pytest.mark.asyncio
async def test_fetch_user_missing_config_raises_503():
    settings = Settings(supabase_url="", supabase_publishable_key="")
    with pytest.raises(ServiceUnavailableError):
        await auth.fetch_supabase_user("token", settings)


def test_me_requires_bearer_token(client):
    response = client.get("/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_returns_authenticated_identity(client, authed_client, authed_user):
    response = client.get(
        "/v1/me", headers={"Authorization": "Bearer test-bearer-token"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(authed_user.id)
    assert body["email"] == "test@example.com"
    assert body["platform_roles"] == ["super_admin"]
    # The raw token must never be serialised in a response.
    assert "test-bearer-token" not in response.text


def test_me_with_no_platform_roles(client, app, authed_user):
    from app.dependencies import get_current_user, get_user_client
    from tests.conftest import FakeSupabaseClient

    async def _user() -> AuthenticatedUser:
        return authed_user

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_user_client] = lambda: FakeSupabaseClient({})
    try:
        response = client.get(
            "/v1/me", headers={"Authorization": "Bearer test-bearer-token"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["platform_roles"] == []
