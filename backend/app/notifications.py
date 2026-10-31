"""Central in-app notification catalogue and service (Milestone 12).

READ THIS FIRST — what is live and what is not:

LIVE in this milestone (backed by the existing database):
- Reading and read-state management of public.notifications
  through the user-context client (SELECT own + UPDATE own
  policies exist). List, unread count, detail, mark-one-read
  (idempotent), and mark-all-read are real API behavior.
- This catalogue: stable event types, titles, bodies, and
  deep-link metadata, enforced in one place so no route
  handler invents its own strings.
- Pure recipient-resolution and eligibility rules, tested
  without a database: who SHOULD receive each event, given
  verified membership/role data.
- Preference defaults and validation rules.

NOT LIVE — catalogued and proposed, never claimed as working:
- Notification GENERATION (inserting rows). The notifications
  table has NO INSERT policy, so a user-context client cannot
  insert rows, and the service client may not write tables
  directly. No approved RPC exists for notification creation,
  and no function or trigger writes to notifications today.
  Generation therefore requires the proposed
  backend_create_notification RPC (see
  docs/proposals/milestone-12-notification-delivery.md).
  Until it is approved and applied, no route handler creates
  notifications, and no event in the catalogue is delivered.
  Wiring generation calls into payment/pickup/review routes
  before the RPC exists would fail at RLS and must not be
  done — the service below builds payloads and resolves
  recipients, but no live code path calls it to write.
- Preferences PERSISTENCE. No preferences table exists, so
  GET returns documented defaults (marked persisted=false)
  and PATCH validates then returns 501 until the proposed
  table is approved.
- Pickup REMINDERS. No scheduler exists in the repository
  (no cron config, no worker, no Render cron job for
  SaveBite). reminder_due() is pure eligibility logic for
  a future scheduler; no reminder job runs or is claimed.
- The private.notification_outbox (push/email/sms/whatsapp)
  is DORMANT infrastructure for future external channels.
  It is not used for in-app notifications (the notifications
  table IS the in-app delivery mechanism) and no code writes
  to it today. M12 is in-app only; email, SMS, push, and
  WhatsApp are out of scope.

Delivery guarantee, stated honestly: once the proposed RPC
exists, delivery is at-least-once per (event, recipient)
with deduplication on dedup_key — a retried emission with
the same key returns the existing row instead of creating
a second one. Exactly-once is NOT claimed: a crash between
the business commit and the notification call can still
lose a notification, and the recovery for that case is a
reconciliation scan over order_status_events (proposed,
not built). A notification is never created for a business
operation that failed, because emission happens only after
the business call succeeds, in the same request — and
never from a frontend callback.

Content rules: titles/bodies contain only order numbers,
store names, and statuses — never customer emails, phones,
addresses, payment secrets, signatures, tokens, webhook
payloads, or merchant documents. Deep links are navigation
hints only (resource type + id); the destination API
independently verifies permission.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# ---------------------------------------------------------------- catalogue


@dataclass(frozen=True)
class NotificationEvent:
    event_type: str
    audience: str  # customer | merchant | admin
    category: str
    title: str
    body_template: str
    reference_type: str
    mandatory: bool = False
    # True only when a real, existing workflow can emit it
    # today (once the delivery RPC exists). False means the
    # event is catalogued but has no active source yet.
    has_active_source: bool = True


CATALOGUE: dict[str, NotificationEvent] = {
    # Customer events
    "reservation_created": NotificationEvent(
        "reservation_created",
        "customer",
        "order_updates",
        "Reservation created",
        "Your reservation for order {order_number} is confirmed. Complete payment before it expires.",
        "order",
    ),
    "payment_captured": NotificationEvent(
        "payment_captured",
        "customer",
        "payment_updates",
        "Payment successful",
        "Payment for order {order_number} was captured successfully.",
        "order",
        mandatory=True,
    ),
    "payment_failed": NotificationEvent(
        "payment_failed",
        "customer",
        "payment_updates",
        "Payment failed",
        "Payment for order {order_number} failed. Your reservation may expire if payment is not completed.",
        "order",
        mandatory=True,
    ),
    "reservation_expired": NotificationEvent(
        "reservation_expired",
        "customer",
        "order_updates",
        "Your reservation has expired",
        "Your reservation for order {order_number} expired before payment was completed.",
        "order",
    ),
    "pickup_reminder": NotificationEvent(
        "pickup_reminder",
        "customer",
        "pickup_reminders",
        "Pickup reminder",
        "Your pickup for order {order_number} at {store_name} starts soon.",
        "order",
        has_active_source=False,
    ),
    "pickup_completed": NotificationEvent(
        "pickup_completed",
        "customer",
        "collection_confirmation",
        "Pickup completed",
        "Your order {order_number} was collected successfully.",
        "order",
    ),
    "order_cancelled": NotificationEvent(
        "order_cancelled",
        "customer",
        "order_updates",
        "Order cancelled",
        "Your order {order_number} was cancelled.",
        "order",
        has_active_source=False,
    ),
    # Merchant events
    "new_paid_order": NotificationEvent(
        "new_paid_order",
        "merchant",
        "new_paid_orders",
        "New paid order",
        "A customer paid for order {order_number} at {store_name}.",
        "order",
    ),
    "merchant_application_approved": NotificationEvent(
        "merchant_application_approved",
        "merchant",
        "application_updates",
        "Merchant application approved",
        "Your merchant application for {merchant_name} was approved.",
        "merchant",
    ),
    "merchant_application_rejected": NotificationEvent(
        "merchant_application_rejected",
        "merchant",
        "application_updates",
        "Merchant application needs attention",
        "Your merchant application for {merchant_name} was not approved. Check the review notes.",
        "merchant",
    ),
    "store_approved": NotificationEvent(
        "store_approved",
        "merchant",
        "application_updates",
        "Store approved",
        "Your store {store_name} was activated.",
        "store",
    ),
    "store_deactivated": NotificationEvent(
        "store_deactivated",
        "merchant",
        "application_updates",
        "Store deactivated",
        "Your store {store_name} was deactivated.",
        "store",
    ),
    "merchant_pickup_completed": NotificationEvent(
        "merchant_pickup_completed",
        "merchant",
        "pickup_updates",
        "Pickup completed",
        "Order {order_number} was collected at {store_name}.",
        "order",
    ),
    # Admin events
    "payment_reconciliation_required": NotificationEvent(
        "payment_reconciliation_required",
        "admin",
        "operational_alerts",
        "Payment needs reconciliation",
        "Order {order_number} requires payment reconciliation. Investigate before taking further action.",
        "order",
        mandatory=True,
    ),
    "merchant_application_submitted": NotificationEvent(
        "merchant_application_submitted",
        "admin",
        "operational_alerts",
        "New merchant application",
        "A new merchant application was submitted for review.",
        "merchant",
    ),
    "merchant_application_reviewed": NotificationEvent(
        "merchant_application_reviewed",
        "admin",
        "operational_alerts",
        "Merchant application reviewed",
        "A merchant application was reviewed.",
        "merchant",
    ),
}

# ---------------------------------------------------------------- preferences

PREFERENCE_CATEGORIES: dict[str, list[str]] = {
    "customer": [
        "order_updates",
        "payment_updates",
        "pickup_reminders",
        "collection_confirmation",
    ],
    "merchant": ["new_paid_orders", "pickup_updates", "application_updates"],
    "admin": ["operational_alerts"],
}

# Mandatory categories can never be disabled: payment
# integrity for customers, reconciliation alerts for admins.
MANDATORY_CATEGORIES = {"payment_updates", "operational_alerts"}

DEFAULT_PREFERENCES: dict[str, bool] = {
    "order_updates": True,
    "payment_updates": True,
    "pickup_reminders": True,
    "collection_confirmation": True,
    "new_paid_orders": True,
    "pickup_updates": True,
    "application_updates": True,
    "operational_alerts": True,
}


def validate_preference_updates(updates: dict[str, bool]) -> list[str]:
    """Return error messages for invalid preference updates.
    Unknown categories are rejected; mandatory categories
    may not be turned off. An empty list means valid."""
    errors: list[str] = []
    known = set(DEFAULT_PREFERENCES)
    for key, value in updates.items():
        if key not in known:
            errors.append(f"Unknown preference category: {key}")
        elif key in MANDATORY_CATEGORIES and value is False:
            errors.append(f"Preference category cannot be disabled: {key}")
    return errors


# ---------------------------------------------------------------- service


def dedup_key(event_type: str, source_id: str, window: str | None = None) -> str:
    """Stable deduplication key for one (event, source,
    window) triple. Retries reuse the same key, so a
    retried emission cannot create a duplicate row. A
    random id per retry would defeat this and must never
    be used."""
    if window:
        return f"{event_type}:{source_id}:{window}"
    return f"{event_type}:{source_id}"


def build_notification(
    event_type: str,
    user_id: str,
    reference_id: str | None,
    context: dict[str, str],
) -> dict:
    """Render one notification payload from the catalogue.
    Raises ValueError for an unknown event type — event
    types must come from the catalogue, never from
    free-form caller input. The returned dict is the row
    the proposed delivery RPC would insert (plus
    dedup_key, which the RPC stores for deduplication);
    this function itself writes nothing."""
    event = CATALOGUE.get(event_type)
    if event is None:
        raise ValueError(f"Unknown notification event type: {event_type}")
    body = event.body_template.format(
        **{
            k: context.get(k, "")
            for k in ("order_number", "store_name", "merchant_name")
        }
    )
    return {
        "user_id": user_id,
        "notification_type": event_type,
        "title": event.title,
        "body": body,
        "reference_type": event.reference_type,
        "reference_id": reference_id,
        "dedup_key": dedup_key(event_type, reference_id or user_id),
    }


def resolve_merchant_recipients(
    merchant_memberships: list[dict], store_staff: list[dict], store_id: str
) -> list[str]:
    """Merchant recipients for a store event, from verified
    membership data (never from the request): merchant
    owner/admin members, plus store staff with role
    store_manager or pickup_operator. finance_viewer and
    inventory_manager do not receive operational pickup/
    order alerts. Returns deduplicated user ids."""
    recipients: set[str] = set()
    for membership in merchant_memberships:
        if membership.get("is_active") is not False and membership.get("role") in (
            "owner",
            "admin",
        ):
            recipients.add(str(membership["user_id"]))
    for staff in store_staff:
        if (
            str(staff.get("store_id")) == str(store_id)
            and staff.get("is_active") is not False
            and staff.get("role") in ("store_manager", "pickup_operator")
        ):
            recipients.add(str(staff["user_id"]))
    return sorted(recipients)


def resolve_admin_recipients(platform_roles: list[dict]) -> list[str]:
    """Admin recipients from verified platform roles
    (M11 gate): operations_admin and super_admin only.
    support_agent, finance_admin, and compliance_admin
    are excluded here for the same verification reason
    as M11 — they cannot be verified through the
    user-context query until the approved fix lands.
    platform_roles rows carry user_id, role, revoked_at;
    revoked rows are ignored twice (query + here)."""
    recipients: set[str] = set()
    for row in platform_roles:
        if row.get("revoked_at") is not None:
            continue
        if row.get("role") in ("operations_admin", "super_admin"):
            recipients.add(str(row["user_id"]))
    return sorted(recipients)


def reminder_due(order: dict, now: datetime, window_minutes: int) -> bool:
    """Pure pickup-reminder eligibility for a future
    scheduler. True only when: the order is confirmed or
    ready_for_pickup, payment is captured, it is not
    collected/cancelled/expired, and now is inside the
    reminder window (pickup_starts_at - window <= now <
    pickup_starts_at). Comparisons use absolute instants;
    the store timezone affects display only, never
    eligibility. No reminder is due after collection, for
    unpaid orders, or outside the window."""
    if order.get("status") not in ("confirmed", "ready_for_pickup"):
        return False
    if order.get("payment_status") != "captured":
        return False
    starts_raw = order.get("pickup_starts_at")
    if starts_raw is None:
        return False
    starts = (
        starts_raw
        if isinstance(starts_raw, datetime)
        else datetime.fromisoformat(str(starts_raw).replace("Z", "+00:00"))
    )
    return starts - timedelta(minutes=window_minutes) <= now < starts
