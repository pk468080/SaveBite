import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

# The configured SaveBite website origin. This is the
# origin the production backend allows; the preflight
# tests below must use exactly it, never "*".
WEBSITE_ORIGIN = "https://savebite-gilt.vercel.app"


def _preflight_client() -> TestClient:
    settings = _settings(environment="production", allowed_origins=[WEBSITE_ORIGIN])
    return TestClient(create_app(settings))


def _settings(**overrides):
    defaults = {
        "supabase_url": "https://example.supabase.co",
        "supabase_publishable_key": "k",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def test_single_plain_origin_string_matches_readme():
    settings = _settings(allowed_origins="https://app.example.com")
    assert settings.allowed_origins == ["https://app.example.com"]


def test_comma_separated_origins():
    settings = _settings(allowed_origins="https://a.example.com, https://b.example.com")
    assert settings.allowed_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_json_list_origins():
    settings = _settings(allowed_origins='["https://a.example.com"]')
    assert settings.allowed_origins == ["https://a.example.com"]


def test_list_input_unchanged():
    settings = _settings(allowed_origins=["https://a.example.com"])
    assert settings.allowed_origins == ["https://a.example.com"]


def test_empty_origins_means_no_cors():
    settings = _settings(allowed_origins="")
    assert settings.allowed_origins == []


def test_invalid_origin_rejected():
    with pytest.raises(ValidationError):
        _settings(allowed_origins="not-a-url")
    with pytest.raises(ValidationError):
        _settings(allowed_origins="https://a.example.com, not-a-url")


def test_wildcard_allowed_outside_production():
    settings = _settings(environment="development", allowed_origins="*")
    assert settings.allowed_origins == ["*"]


def test_wildcard_rejected_in_production():
    with pytest.raises(ValidationError):
        _settings(environment="production", allowed_origins="*")
    with pytest.raises(ValidationError):
        _settings(
            environment="production",
            allowed_origins=["https://a.example.com", "*"],
        )


# --- Environment-source tests ---
# These construct Settings() with NO arguments, so the values must
# come from the environment. This is the proof the direct-construction
# tests above cannot give: without NoDecode, pydantic-settings would
# JSON-decode ALLOWED_ORIGINS before validation and the plain-URL and
# comma-separated forms would fail here.


def test_env_single_plain_origin(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    settings = Settings()
    assert settings.allowed_origins == ["https://app.example.com"]


def test_env_comma_separated_origins(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.example.com,https://b.example.com")
    settings = Settings()
    assert settings.allowed_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_env_json_list_origins(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", '["https://a.example.com"]')
    settings = Settings()
    assert settings.allowed_origins == ["https://a.example.com"]


def test_env_invalid_origin_rejected(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("ALLOWED_ORIGINS", "not-a-url")
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("ALLOWED_ORIGINS", '["not-a-url"]')
    with pytest.raises(ValidationError):
        Settings()
    monkeypatch.setenv("ALLOWED_ORIGINS", '{"not": "a list"}')
    with pytest.raises(ValidationError):
        Settings()


def test_env_production_wildcard_rejected(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "*")
    with pytest.raises(ValidationError):
        Settings()


# --- W9.1: actual CORS preflight ---
# The frontend sends Idempotency-Key on reservation and
# checkout POSTs (packages/api-client). Before W9.1 the
# allowlist omitted it, so browsers blocked those calls
# at preflight. These tests issue a real OPTIONS
# preflight through the middleware stack, not a config
# assertion, and pin the production origin restriction.


def test_preflight_permits_idempotency_key_for_website_origin():
    client = _preflight_client()
    response = client.options(
        "/v1/orders/reservations",
        headers={
            "Origin": WEBSITE_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization, content-type, idempotency-key"
            ),
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == WEBSITE_ORIGIN
    allowed = response.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "content-type" in allowed
    assert "idempotency-key" in allowed


def test_preflight_denies_unlisted_origin():
    client = _preflight_client()
    response = client.options(
        "/v1/orders/reservations",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "authorization, content-type, idempotency-key"
            ),
        },
    )
    assert "access-control-allow-origin" not in response.headers
