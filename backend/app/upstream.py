"""Translate Supabase/PostgREST upstream errors into API errors.

PostgREST returns HTTP 400 for most PostgreSQL errors, with the PG
code in the JSON body (e.g. 42501 for access denied, 22023 for a
check/validation error, P0002 for not-found). Mapping must therefore
look at the body code first, then at the HTTP status. Unknown
upstream failures become 502, never a 500 that hides the boundary,
and never a response that echoes a token, key, or raw SQL.
"""

from __future__ import annotations

import httpx

from app.errors import (
    ApiError,
    AuthorizationError,
    BadGatewayError,
    NotFoundError,
)


def translate_upstream_error(exc: Exception) -> ApiError:
    if isinstance(exc, ApiError):
        return exc
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        body: dict = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}
        pg_code = str(body.get("code", ""))
        message = str(body.get("message", "") or "Upstream service error")
        if pg_code == "42501" or "access_denied" in message:
            return AuthorizationError("Forbidden")
        if pg_code == "P0002" or "not_found" in message:
            return NotFoundError("Not found")
        if pg_code == "22023" or response.status_code in (400, 422):
            # DB validation errors (business_name_required,
            # invalid_latitude, hours_*, ...) are client errors.
            return ApiError(422, "VALIDATION_ERROR", message)
        if response.status_code in (401, 403):
            return AuthorizationError("Forbidden")
        if response.status_code == 404:
            return NotFoundError("Not found")
        return BadGatewayError("Upstream service error")
    if isinstance(exc, httpx.HTTPError):
        return BadGatewayError("Upstream service error")
    return BadGatewayError("Upstream service error")
