"""Environment configuration and secret validation.

No secret is hard-coded, logged, or committed. The service-role key and
the Razorpay webhook secret are optional at startup so that health
checks work in local development, but any operation that needs them
fails closed (see supabase_client.py and security.py) until they are
configured as deployment secrets.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_version: str = "v1"
    service_name: str = "savebite-api"
    service_version: str = "0.1.0"

    # Supabase — publishable key is the only key client-facing code may use.
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    # Server-only. Never expose to Expo / Next.js browser code, never log.
    supabase_service_role_key: SecretStr | None = None
    # Server-only. Required before any Razorpay webhook is accepted.
    razorpay_webhook_secret: SecretStr | None = None

    # CORS: empty means no CORS middleware. Never use "*" in production.
    allowed_origins: list[str] = []

    @field_validator("supabase_url")
    @classmethod
    def _validate_supabase_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not value.startswith("https://"):
            raise ValueError("SUPABASE_URL must use https")
        return value

    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)

    @property
    def service_role_configured(self) -> bool:
        return self.supabase_service_role_key is not None and bool(
            self.supabase_service_role_key.get_secret_value()
        )

    @property
    def webhook_secret_configured(self) -> bool:
        return self.razorpay_webhook_secret is not None and bool(
            self.razorpay_webhook_secret.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
