"""Environment configuration and secret validation.

No secret is hard-coded, logged, or committed. The service-role key and
the Razorpay webhook secret are optional at startup so that health
checks work in local development, but any operation that needs them
fails closed (see supabase_client.py and security.py) until they are
configured as deployment secrets.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_ORIGIN_RE = re.compile(r"^https?://[A-Za-z0-9._:-]+(:\d+)?(/.*)?$")


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
    # Razorpay (Milestone 6). key_id is public and may be returned
    # to the frontend; both secrets are server-only, never logged,
    # never returned, never committed. Test-mode keys (rzp_test_)
    # only in local development and tests.
    razorpay_key_id: str = ""
    razorpay_key_secret: SecretStr | None = None
    # Server-only. Required before any Razorpay webhook is accepted.
    razorpay_webhook_secret: SecretStr | None = None

    # CORS: empty means no CORS middleware. Never use "*" in production.
    # Accepted forms (consistent with backend/README.md):
    #   ALLOWED_ORIGINS=https://app.example.com
    #   ALLOWED_ORIGINS=https://a.example.com,https://b.example.com
    #   ALLOWED_ORIGINS=["https://a.example.com"]
    # A single plain URL, a comma-separated list, and a JSON list are
    # all parsed to the same list[str]. Anything else is rejected.
    # NoDecode is essential here: without it, pydantic-settings
    # JSON-decodes a complex field's environment value BEFORE field
    # validation, so a plain URL like "https://app.example.com" would
    # fail JSON decoding and a comma-separated list would never reach
    # the validator. With NoDecode, the raw environment string reaches
    # _parse_allowed_origins unchanged, which is what the
    # environment-source tests in tests/test_cors.py prove.
    allowed_origins: Annotated[list[str], NoDecode] = []

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: object) -> object:
        if value is None:
            return []
        if isinstance(value, list):
            raw = value
        elif isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        "ALLOWED_ORIGINS must be a URL, a comma-separated list, or a JSON list"
                    ) from exc
                if not isinstance(parsed, list):
                    raise ValueError("ALLOWED_ORIGINS JSON value must be a list")
                raw = parsed
            else:
                raw = [part.strip() for part in text.split(",")]
        else:
            raise ValueError("ALLOWED_ORIGINS must be a string or list")
        origins: list[str] = []
        for origin in raw:
            if not isinstance(origin, str) or not origin.strip():
                raise ValueError(
                    "ALLOWED_ORIGINS contains an empty or non-string origin"
                )
            origin = origin.strip()
            if origin == "*":
                origins.append(origin)
                continue
            if not _ORIGIN_RE.match(origin):
                raise ValueError(
                    f"ALLOWED_ORIGINS contains an invalid origin: {origin!r}"
                )
            origins.append(origin.rstrip("/"))
        return origins

    @model_validator(mode="after")
    def _reject_production_wildcard(self) -> Settings:
        if self.environment == "production" and "*" in self.allowed_origins:
            raise ValueError(
                "ALLOWED_ORIGINS must not contain '*' when ENVIRONMENT=production"
            )
        return self

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
    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id) and (
            self.razorpay_key_secret is not None
            and bool(self.razorpay_key_secret.get_secret_value())
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
