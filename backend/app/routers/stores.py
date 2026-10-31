"""Store operating hours (Milestone 3).

Authorisation mirrors private.can_manage_store(store_id,
['store_manager']): merchant owners/admins are always allowed,
even with no store-staff row; a store_manager is allowed only
with an active merchant membership as well. See
rbac.can_manage_store_hours. The RPC enforces the same rule, so
this check is defence in depth, not a replacement for it.
"""

from __future__ import annotations

from datetime import time as _time
from uuid import UUID

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_user_client
from app.errors import AuthorizationError, NotFoundError
from app.rbac import can_manage_store_hours
from app.schemas import (
    AuthenticatedUser,
    StoreHoursEntry,
    StoreHoursResponse,
    StoreHoursUpdate,
    StoreHoursUpdateResponse,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(prefix="/v1/stores", tags=["stores"])


async def _require_hours_access(
    user: AuthenticatedUser,
    client: SupabaseRestClient,
    store_id: UUID,
) -> None:
    allowed, merchant_id = await can_manage_store_hours(user, client, store_id)
    if merchant_id is None:
        raise NotFoundError("Store not found")
    if not allowed:
        raise AuthorizationError("Store manager, merchant owner or admin required")


def _hours_from_rows(rows: list[dict]) -> list[StoreHoursEntry]:
    # model_construct, not validation: these are stored rows, and
    # the API's stricter input rule (opens_at < closes_at) must not
    # turn a stored row into a 500 on read. Times are parsed from
    # the PostgREST "HH:MM:SS" strings to time objects for serialisation.
    def _to_time(value: object) -> _time | None:
        if value is None:
            return None
        if isinstance(value, _time):
            return value
        return _time.fromisoformat(str(value))

    return [
        StoreHoursEntry.model_construct(
            weekday=row["weekday"],
            is_closed=row.get("is_closed", False),
            opens_at=_to_time(row.get("opens_at")),
            closes_at=_to_time(row.get("closes_at")),
        )
        for row in sorted(rows, key=lambda r: r["weekday"])
    ]


@router.get("/{store_id}/hours", response_model=StoreHoursResponse)
async def get_store_hours(
    store_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> StoreHoursResponse:
    await _require_hours_access(user, client, store_id)
    try:
        rows = await client.query(
            "store_hours",
            filters={"store_id": f"eq.{store_id}", "order": "weekday.asc"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return StoreHoursResponse(store_id=store_id, hours=_hours_from_rows(rows))


@router.put("/{store_id}/hours", response_model=StoreHoursUpdateResponse)
async def update_store_hours(
    store_id: UUID,
    payload: StoreHoursUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> StoreHoursUpdateResponse:
    await _require_hours_access(user, client, store_id)
    rpc_hours = [
        {
            "weekday": entry.weekday,
            "is_closed": entry.is_closed,
            "opens_at": entry.opens_at.strftime("%H:%M:%S") if entry.opens_at else None,
            "closes_at": entry.closes_at.strftime("%H:%M:%S")
            if entry.closes_at
            else None,
        }
        for entry in payload.hours
    ]
    try:
        processed = await client.rpc(
            "upsert_store_hours",
            {"p_store_id": str(store_id), "p_hours": rpc_hours},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    try:
        rows = await client.query(
            "store_hours",
            filters={"store_id": f"eq.{store_id}", "order": "weekday.asc"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    hours = _hours_from_rows(rows)
    processed_count = processed if isinstance(processed, int) else len(hours)
    return StoreHoursUpdateResponse(
        store_id=store_id, processed=processed_count, hours=hours
    )
