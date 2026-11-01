"""Central in-app notification catalogue and service (Milestone 12, activated in W7).

READ THIS FIRST — what is live and what is not (W7 state):

LIVE (backed by the database, once the W7 migrations are applied):
- Reading and read-state management of public.notifications
  through the user-context client (SELECT own + UPDATE own
  policies exist). List, unread count, detail, mark-one-read
  (idempotent), and mark-all-read are real API behavior.
- GENERATION through the transactional outbox: database
  triggers enqueue jobs into private.notification_outbox in the
  same transaction as the authoritative business change
  (payment capture/failure/reconciliation, collection, merchant
  application review, store activation). No route and no
  frontend code creates notifications; there is no INSERT
  policy on public.notifications and no general-purpose
  creation RPC for callers to abuse.
- DELIVERY by the standalone worker (app/notification_worker.py),
  which calls backend_enqueue_pickup_reminders and then
  backend_process_notification_outbox through the service-role
  client. Delivery is at-least-once per (event, recipient) with
  deduplication on dedup_key; concurrent workers claim disjoint
  job sets (FOR UPDATE SKIP LOCKED) and a crashed worker's jobs
  are reclaimed after the claim window. Exactly-once is NOT
  claimed: what is guaranteed is exactly-once user-visible
  effect (the dedup key prevents a second row), not
  exactly-once processing.
- PREFERENCES persistence in public.notification_preferences:
  GET returns the stored row (persisted=true) or documented
  defaults (persisted=false); PATCH validates and upserts the
  caller's own row. Mandatory categories (payment_updates,
  operational_alerts) can never be disabled, in code and by a
  database CHECK.
- PICKUP REMINDERS via the worker: eligible orders (confirmed /
  ready_for_pickup, payment captured, now inside
  [pickup_starts_at - window, pickup_starts_at)) are enqueued
  with dedup key pickup_reminder:{order_id}. No process-local
  timers; the worker loop or a scheduler calling it with --once
  is the only driver.

NOT LIVE — catalogued but with no active source, deliberately:
- reservation_created: notifying on an unpaid reservation is
  forbidden by the product rule, so no trigger emits it.
- reservation_expired: backend_release_expired_reservations has
  no caller/scheduler, so no authoritative expiry event exists.
- order_cancelled: no order-cancel route exists.
- Any refund event: request_refund has no route caller and
  backend_update_refund_status has no caller, so no refund
  transition can emit today. Adding any of these requires a
  real business trigger first, not a new notification type.
- External channels: outbox rows for push/email/sms/whatsapp
  remain dormant. The W7 processor claims channel='in_app'
  rows only. No email, SMS, push, or WhatsApp delivery exists.
- Worker DEPLOYMENT: the worker command exists and is
  documented, but no production worker or scheduler is
  configured by this milestone, and the W7 migrations are
  files in this PR, not applied to live. Until both land,
  no notification is delivered in production, and that must
  not be claimed otherwise.

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

# ---------------------------------------------------------------- worker
# Single source of truth for the W7 worker and its database
# contract. The SQL defaults mirror these values; keep them in
# sync when either side changes.

#: RPC that claims and delivers one bounded batch of outbox jobs.
WORKER_PROCESS_RPC = "backend_process_notification_outbox"
#: RPC that enqueues due pickup reminders. Idempotent.
WORKER_REMINDER_RPC = "backend_enqueue_pickup_reminders"
#: Reminder window: notify when pickup starts within this long.
REMINDER_WINDOW_MINUTES = 60
#: A 'processing' job older than this is reclaimable.
OUTBOX_CLAIM_EXPIRY_MINUTES = 10
#: Delivery attempts per job before it becomes dead-letter.
OUTBOX_MAX_ATTEMPTS = 5
#: Default jobs per processor call.
OUTBOX_DEFAULT_BATCH_SIZE = 50

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
    # True only when a real, existing workflow emits it today
    # (W7 database trigger, or the worker for reminders).
    # False means the event is catalogued but has no active
    # source yet — or is deliberately never emitted (see
    # reservation_created).
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
        # Deliberately never emitted: notifying on an unpaid
        # reservation is forbidden by the product rule.
        has_active_source=False,
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
        # Emitted by the W7 worker via
        # backend_enqueue_pickup_reminders, not by a trigger.
        has_active_source=True,
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
    free-form caller input. The returned dict mirrors the
    outbox job a W7 trigger enqueues (plus dedup_key, which
    the database stores for deduplication); this function
    itself writes nothing."""
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
