"""In-app notification APIs (Milestone 12).

What these endpoints do — and what they deliberately do
not do — follows the audit in app/notifications.py:

- READ + READ-STATE endpoints are real: the
  notifications table has SELECT-own and UPDATE-own
  policies, so a caller sees and modifies only their
  own rows. Every query filters user_id = the
  authenticated user, and every single-row operation
  re-checks ownership (a missing row and another
  user's row both return 404).
- GENERATION endpoints do not exist here: the table
  has no INSERT policy and no approved creation RPC,
  so no route creates notifications. The catalogue and
  service in app/notifications.py define what WILL be
  created once the proposed delivery RPC is approved;
  until then, claiming delivery would be false.
- PREFERENCES persistence does not exist: no
  preferences table exists. GET returns documented
  defaults (persisted=false); PATCH validates the
  payload (unknown categories and disabling mandatory
  categories are rejected with 422) and then returns
  501, because there is nowhere safe to store the
  result yet. Returning 200 without persisting would
  lie to the caller.
- No email, SMS, push, or WhatsApp delivery exists
  here. The private.notification_outbox is dormant
  external-channel infrastructure and is not touched.

Pagination is database-side (order/limit/offset) with
an id-only count query, matching the admin pattern.
Unread count uses a read_at IS NULL filter, never a
full-history fetch into Python.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_user, get_user_client
from app.errors import ApiError, NotFoundError
from app.notifications import (
    CATALOGUE,
    DEFAULT_PREFERENCES,
    MANDATORY_CATEGORIES,
    validate_preference_updates,
)
from app.schemas import (
    AuthenticatedUser,
    MarkAllReadResponse,
    MarkReadResponse,
    NotificationListResponse,
    NotificationPreferencesResponse,
    NotificationPreferencesUpdate,
    NotificationResponse,
    UnreadCountResponse,
)
from app.supabase_client import SupabaseRestClient
from app.upstream import translate_upstream_error

router = APIRouter(tags=["notifications"])

_NOTIFICATION_SELECT = (
    "id,user_id,notification_type,title,body,reference_type,reference_id,"
    "read_at,created_at"
)


def _parse_time(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _response(row: dict) -> NotificationResponse:
    read_at = _parse_time(row.get("read_at"))
    return NotificationResponse(
        id=UUID(str(row["id"])),
        notification_type=row["notification_type"],
        title=row["title"],
        body=row["body"],
        reference_type=row.get("reference_type"),
        reference_id=UUID(str(row["reference_id"]))
        if row.get("reference_id")
        else None,
        read_at=read_at,
        created_at=_parse_time(row["created_at"]),  # type: ignore[arg-type]
        is_read=read_at is not None,
    )


def _page_params(page: int, page_size: int) -> dict[str, str]:
    return {
        "order": "created_at.desc,id.desc",
        "limit": str(page_size),
        "offset": str((page - 1) * page_size),
    }


@router.get("/v1/notifications", response_model=NotificationListResponse)
async def list_notifications(
    unread_only: bool = Query(default=False),
    notification_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> NotificationListResponse:
    filters: dict[str, str] = {"user_id": f"eq.{user.id}"}
    if unread_only:
        filters["read_at"] = "is.null"
    if notification_type is not None:
        if notification_type not in CATALOGUE:
            raise ApiError(422, "VALIDATION_ERROR", "Unknown notification type")
        filters["notification_type"] = f"eq.{notification_type}"
    try:
        count_rows = await client.query("notifications", select="id", filters=filters)
        rows = await client.query(
            "notifications",
            select=_NOTIFICATION_SELECT,
            filters={**filters, **_page_params(page, page_size)},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return NotificationListResponse(
        items=[_response(r) for r in rows],
        total=len(count_rows),
        page=page,
        page_size=page_size,
    )


@router.get("/v1/notifications/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> UnreadCountResponse:
    try:
        rows = await client.query(
            "notifications",
            select="id",
            filters={"user_id": f"eq.{user.id}", "read_at": "is.null"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return UnreadCountResponse(unread_count=len(rows))


@router.get(
    "/v1/notifications/preferences",
    response_model=NotificationPreferencesResponse,
)
async def get_preferences(
    user: AuthenticatedUser = Depends(get_current_user),
) -> NotificationPreferencesResponse:
    _ = user
    return NotificationPreferencesResponse(
        preferences=dict(DEFAULT_PREFERENCES),
        mandatory_categories=sorted(MANDATORY_CATEGORIES),
        persisted=False,
    )


@router.patch("/v1/notifications/preferences")
async def update_preferences(
    payload: NotificationPreferencesUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    _ = user
    errors = validate_preference_updates(payload.preferences)
    if errors:
        raise ApiError(422, "VALIDATION_ERROR", "; ".join(errors))
    # Validated but not persisted: no preferences table
    # exists yet. Returning 200 here would falsely claim
    # the settings were saved.
    raise ApiError(
        501,
        "NOT_IMPLEMENTED",
        "Notification preferences storage is not yet configured; "
        "see the proposed preferences table in the milestone documentation.",
    )


@router.get("/v1/notifications/{notification_id}", response_model=NotificationResponse)
async def notification_detail(
    notification_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> NotificationResponse:
    try:
        rows = await client.query(
            "notifications",
            select=_NOTIFICATION_SELECT,
            filters={"id": f"eq.{notification_id}", "user_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Notification not found")
    return _response(rows[0])


@router.post(
    "/v1/notifications/{notification_id}/read", response_model=MarkReadResponse
)
async def mark_read(
    notification_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MarkReadResponse:
    """Mark one notification read. Idempotent: marking an
    already-read notification again succeeds and returns
    the existing read timestamp, never an error."""
    try:
        rows = await client.query(
            "notifications",
            select=_NOTIFICATION_SELECT,
            filters={"id": f"eq.{notification_id}", "user_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        raise NotFoundError("Notification not found")
    existing = rows[0]
    if existing.get("read_at") is not None:
        return MarkReadResponse(
            id=notification_id,
            read_at=_parse_time(existing["read_at"]),  # type: ignore[arg-type]
            already_read=True,
        )
    now = datetime.now(UTC)
    try:
        updated = await client.update(
            "notifications",
            {"read_at": now.isoformat()},
            {"id": f"eq.{notification_id}", "user_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if updated:
        read_at = _parse_time(updated[0].get("read_at"))
    else:
        # A concurrent mark-read won the race; re-read to
        # return the real timestamp instead of failing.
        rows = await client.query(
            "notifications",
            select="read_at",
            filters={"id": f"eq.{notification_id}", "user_id": f"eq.{user.id}"},
        )
        read_at = _parse_time(rows[0]["read_at"]) if rows else now
    return MarkReadResponse(
        id=notification_id,
        read_at=read_at,  # type: ignore[arg-type]
        already_read=False,
    )


@router.post("/v1/notifications/read-all", response_model=MarkAllReadResponse)
async def mark_all_read(
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> MarkAllReadResponse:
    """Mark all of the CALLER's unread notifications read.
    No user id is accepted from the request; the filter
    is always the authenticated user."""
    now = datetime.now(UTC)
    try:
        updated = await client.update(
            "notifications",
            {"read_at": now.isoformat()},
            {"user_id": f"eq.{user.id}", "read_at": "is.null"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return MarkAllReadResponse(updated_count=len(updated))
