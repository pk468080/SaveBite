"""SaveBite FastAPI application entry point.

Create the app with create_app() so tests can inject settings and
dependency overrides without importing a global singleton. The app
does not connect to the database at startup: health checks must work
even when Supabase is down, and every database access happens
per-request through the authenticated clients in dependencies.py.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.errors import register_error_handlers
from app.logging_config import configure_logging, new_request_id, request_id_var
from app.routers import (
    admin,
    dashboard,
    health,
    listings,
    marketplace,
    me,
    merchants,
    orders,
    payments,
    pickups,
    reviews,
    stores,
)

logger = logging.getLogger("savebite.main")


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings.log_level)

    app = FastAPI(
        title="SaveBite API",
        version=app_settings.service_version,
        description=(
            "SaveBite surplus-food marketplace API. Customer pickup only; "
            "no delivery in MVP. See docs/architecture.md for boundaries."
        ),
    )

    if app_settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.allowed_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        )

    @app.middleware("http")
    async def _request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        incoming = request.headers.get("X-Request-Id", "")
        try:
            request_id = str(uuid.UUID(incoming)) if incoming else new_request_id()
        except ValueError:
            request_id = new_request_id()
        token = request_id_var.set(request_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "%s %s -> %s in %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            time.monotonic() - started,
        )
        return response

    # Make the settings object passed to create_app() the one that
    # Depends(get_settings) returns. Without this, a test app built
    # with test settings would still read the global cached settings
    # (which may have no Supabase URL) in its routes.
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: app_settings

    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(merchants.router)
    app.include_router(stores.router)
    app.include_router(listings.router)
    app.include_router(marketplace.router)
    app.include_router(payments.router)
    app.include_router(orders.router)
    app.include_router(pickups.router)
    app.include_router(reviews.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)

    @app.get("/", include_in_schema=False)
    async def _root() -> dict[str, str]:
        return {
            "service": app_settings.service_name,
            "version": app_settings.service_version,
            "health": "/health",
            "ready": "/v1/health/ready",
        }

    return app


app = create_app()
