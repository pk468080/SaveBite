"""Health and readiness.

GET /health is liveness only and never touches Supabase, so a load
balancer can use it even when the database is down.
GET /v1/health/ready is readiness: it checks Supabase Auth health and
reports whether the service-role key is configured (boolean only,
never the key). A failed Auth check returns 503, not a 200.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.errors import ServiceUnavailableError
from app.schemas import HealthResponse, ReadinessResponse

router = APIRouter()


async def check_supabase_auth_health(supabase_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{supabase_url}/auth/v1/health")
        return response.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/health", response_model=HealthResponse, tags=["health"])
async def liveness(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        service=settings.service_name, version=settings.service_version
    )


@router.get("/v1/health/ready", response_model=ReadinessResponse, tags=["health"])
async def readiness(settings: Settings = Depends(get_settings)) -> ReadinessResponse:
    checks: dict[str, str] = {
        "supabase_configured": "ok" if settings.supabase_configured else "missing",
        "service_role_configured": (
            "ok" if settings.service_role_configured else "missing"
        ),
    }
    if not settings.supabase_configured:
        checks["supabase_auth"] = "skipped"
        raise ServiceUnavailableError("Supabase is not configured")
    auth_ok = await check_supabase_auth_health(settings.supabase_url)
    checks["supabase_auth"] = "ok" if auth_ok else "unreachable"
    if not auth_ok:
        raise ServiceUnavailableError("Supabase Auth is unreachable")
    return ReadinessResponse(
        status="ready",
        service=settings.service_name,
        version=settings.service_version,
        checks=checks,
    )
