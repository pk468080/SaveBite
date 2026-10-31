import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import ServiceUnavailableError
from app.supabase_client import service_client


def test_http_supabase_url_rejected():
    with pytest.raises(ValidationError):
        Settings(
            supabase_url="http://insecure.example.com",
            supabase_publishable_key="k",
        )


def test_service_client_fails_closed_without_key():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="k",
        supabase_service_role_key=None,
    )
    assert settings.service_role_configured is False
    with pytest.raises(ServiceUnavailableError):
        service_client(settings)


def test_service_role_key_is_not_serialised():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="k",
        supabase_service_role_key="secret-value",
    )
    dumped = settings.model_dump()
    # SecretStr must not leak its value through model_dump.
    assert "secret-value" not in str(dumped)


def test_allowed_origins_default_empty():
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="k",
    )
    assert settings.allowed_origins == []
