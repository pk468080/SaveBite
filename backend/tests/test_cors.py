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
