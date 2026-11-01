"""In-app notification APIs (Milestone 12, activated in W7).

What these endpoints do — and what they deliberately do not do:

- READ + READ-STATE endpoints are real: the
  notifications table has SELECT-own and UPDATE-own
  policies, so a caller sees and modifies only their
  own rows. Every query filters user_id = the
  authenticated user, and every single-row operation
  re-checks ownership (a missing row and another
  user's row both return 404).
- GENERATION endpoints do not exist here: notifications
  are created only by W7 database triggers (same
  transaction as the business change) and delivered by
  the standalone worker. No route creates notifications,
  and the table has no INSERT policy for callers.
- PREFERENCES are persisted in
  public.notification_preferences, one row per user,
  readable and writable only by that user. GET returns
  the stored row (persisted=true) or documented defaults
  (persisted=false) when the user has never saved
  settings. PATCH validates (unknown categories and
  disabling mandatory categories are rejected with 422)
  and upserts the caller's own row.
- No email, SMS, push, or WhatsApp delivery exists
  here. The private.notification_outbox rows for those
  channels are untouched by these endpoints.

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

# Columns of public.notification_preferences, in the same
# order as DEFAULT_PREFERENCES, so GET/PATCH round-trip
# exactly the categories the catalogue defines.
_PREFERENCE_COLUMNS = (
    "user_id",
    "order_updates",
    "payment_updates",
    "pickup_reminders",
    "collection_confirmation",
    "new_paid_orders",
    "pickup_updates",
    "application_updates",
    "operational_alerts",
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
    client: SupabaseRestClient = Depends(get_user_client),
) -> NotificationPreferencesResponse:
    """Return the caller's stored preferences, or documented
    defaults (persisted=false) when they never saved any.
    The row is read through the user-context client under
    the own-row policy, so another user's row is
    unreachable here even if its id were guessed."""
    try:
        rows = await client.query(
            "notification_preferences",
            select=",".join(_PREFERENCE_COLUMNS),
            filters={"user_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if not rows:
        return NotificationPreferencesResponse(
            preferences=dict(DEFAULT_PREFERENCES),
            mandatory_categories=sorted(MANDATORY_CATEGORIES),
            persisted=False,
        )
    stored = rows[0]
    preferences = {
        column: bool(stored.get(column, DEFAULT_PREFERENCES[column]))
        for column in _PREFERENCE_COLUMNS
        if column != "user_id"
    }
    return NotificationPreferencesResponse(
        preferences=preferences,
        mandatory_categories=sorted(MANDATORY_CATEGORIES),
        persisted=True,
    )


@router.patch(
    "/v1/notifications/preferences",
    response_model=NotificationPreferencesResponse,
)
async def update_preferences(
    payload: NotificationPreferencesUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
    client: SupabaseRestClient = Depends(get_user_client),
) -> NotificationPreferencesResponse:
    """Validate and persist the caller's own preferences.
    Unknown categories and disabling a mandatory category
    are rejected with 422 before anything is written.
    The write is scoped to the caller's own row by the
    user_id filter and the own-row policy; no user id is
    accepted from the request body."""
    errors = validate_preference_updates(payload.preferences)
    if errors:
        raise ApiError(422, "VALIDATION_ERROR", "; ".join(errors))
    try:
        rows = await client.query(
            "notification_preferences",
            select=",".join(_PREFERENCE_COLUMNS),
            filters={"user_id": f"eq.{user.id}"},
        )
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    if rows:
        merged = {
            column: bool(rows[0].get(column, DEFAULT_PREFERENCES[column]))
            for column in _PREFERENCE_COLUMNS
            if column != "user_id"
        }
    else:
        merged = dict(DEFAULT_PREFERENCES)
    merged.update(payload.preferences)
    row = {"user_id": str(user.id), **merged}
    try:
        if rows:
            updated = await client.update(
                "notification_preferences",
                merged,
                {"user_id": f"eq.{user.id}"},
            )
            if not updated:
                # The row vanished between read and write
                # (account deletion cascade); fall back to
                # insert rather than reporting success
                # without a stored row.
                await client.insert("notification_preferences", row)
        else:
            await client.insert("notification_preferences", row)
    except Exception as exc:
        raise translate_upstream_error(exc) from exc
    return NotificationPreferencesResponse(
        preferences=merged,
        mandatory_categories=sorted(MANDATORY_CATEGORIES),
        persisted=True,
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
