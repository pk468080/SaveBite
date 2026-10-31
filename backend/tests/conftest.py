"""Pytest fixtures for the SaveBite FastAPI foundation.

No test hits the live Supabase project and no test uses a real secret.
Auth and PostgREST calls are replaced with fakes via FastAPI dependency
overrides or monkeypatching, at the boundary functions in auth.py,
health.py and rbac.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.dependencies import get_current_user, get_user_client
from app.main import create_app
from app.schemas import AuthenticatedUser


def test_settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "supabase_url": "https://zehnhqcfawagxbactvne.supabase.co",
        "supabase_publishable_key": "test-publishable-key",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.fixture()
def app():
    return create_app(test_settings())


@pytest.fixture()
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def authed_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        id=UUID("11111111-1111-4111-8111-111111111111"),
        email="test@example.com",
        token="test-bearer-token",
    )


class FakeSupabaseClient:
    """Minimal fake for SupabaseRestClient.query / rpc."""

    def __init__(self, rows: dict[str, list[dict]] | None = None) -> None:
        self.rows = rows or {}
        self.rpc_calls: list[tuple[str, dict]] = []

    async def query(self, table: str, *, select: str = "*", filters=None):  # type: ignore[no-untyped-def]
        return self.rows.get(table, [])

    async def rpc(self, name: str, params: dict):  # type: ignore[no-untyped-def]
        self.rpc_calls.append((name, params))
        return {}


@pytest.fixture()
def authed_client(app, authed_user, monkeypatch):
    """Override auth + user client so /v1/me works without Supabase."""
    fake = FakeSupabaseClient(
        {"platform_user_roles": [{"role": "super_admin", "revoked_at": None}]}
    )

    async def _user() -> AuthenticatedUser:
        return authed_user

    def _client():  # type: ignore[no-untyped-def]
        return fake

    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_user_client] = _client
    yield fake
    app.dependency_overrides.clear()
