"""Standardised error handling.

Every error response uses one envelope:
    {"error": {"code": "...", "message": "...", "request_id": "..."}}
No stack trace, token or secret is ever included in a response body.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import get_request_id

logger = logging.getLogger("savebite.errors")


class ApiError(Exception):
    """Application error with an explicit HTTP status and error code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class AuthenticationError(ApiError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(401, "UNAUTHORIZED", message)


class AuthorizationError(ApiError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(403, "FORBIDDEN", message)


class NotFoundError(ApiError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(404, "NOT_FOUND", message)


class ServiceUnavailableError(ApiError):
    def __init__(self, message: str = "Service unavailable") -> None:
        super().__init__(503, "SERVICE_UNAVAILABLE", message)


class BadGatewayError(ApiError):
    def __init__(self, message: str = "Upstream service error") -> None:
        super().__init__(502, "BAD_GATEWAY", message)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": get_request_id(),
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Do not echo raw request values: validation errors can contain
        # user input. Field names and error types are enough to debug.
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "type": err["type"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "request_id": get_request_id(),
                    "details": details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception: %s", type(exc).__name__)
        return error_response(500, "INTERNAL_ERROR", "Internal server error")
