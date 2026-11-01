"""W8 production-configuration tests (no live service).

Interactive API docs must be disabled in production so the
route surface is not exposed to unauthenticated probing,
while staying available in development for debugging.
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings(environment: str) -> Settings:
    return Settings(
        supabase_url="https://zehnhqcfawagxbactvne.supabase.co",
        supabase_publishable_key="test-publishable-key",
        environment=environment,  # type: ignore[arg-type]
    )


def test_docs_disabled_in_production():
    app = create_app(_settings(environment="production"))
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    # The API itself still answers in production.
    assert client.get("/health").status_code == 200


def test_docs_enabled_in_development():
    app = create_app(_settings(environment="development"))
    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
