import pytest
from pydantic import ValidationError

from app.config import Settings


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
