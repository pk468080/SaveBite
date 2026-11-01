# PROPOSAL — NOT APPLIED — REQUIRES EXPLICIT APPROVAL

> W7 UPDATE (2026-11-01): this proposal is SUPERSEDED by the
> W7 implementation, which the user approved as a milestone
> brief. W7 keeps the proposal's core (dedup_key + partial
> unique index, catalogue CHECK, preferences table, 15-minute
> or continuous worker) but changes the delivery design in
> three deliberate ways: (1) generation moved from a
> post-commit API call to database triggers that enqueue
> into private.notification_outbox in the SAME transaction
> as the business change, closing the crash-between-commit-
> and-emission loss window the proposal acknowledged;
> (2) preferences are typed boolean columns (with a database
> CHECK for mandatory categories) instead of a jsonb blob;
> (3) the worker is a standalone process calling
> backend_process_notification_outbox +
> backend_enqueue_pickup_reminders, rather than a cron-only
> design. The migrations live in supabase/migrations/
> (20261101120000, 20261101121000, 20261101122000) and are
> still NOT applied to live by the W7 PR. This document is
> kept as the audit record; do not apply it — apply the W7
> migrations instead, through the normal review process.

# Milestone 12: notification delivery infrastructure

Status: this document is a REVIEW PROPOSAL ONLY. Nothing
in it has been applied to the live Supabase project, and
nothing here is in `supabase/migrations/` — deliberately,
so it cannot be picked up by `supabase db push` by
accident. Applying any part of it requires a separate,
explicit user approval naming this proposal.

## 1. Why delivery is not live today (audit summary)

- `public.notifications` exists with columns id,
  user_id (FK auth.users, ON DELETE CASCADE),
  notification_type (free text, no CHECK),
  title, body, reference_type, reference_id,
  read_at, created_at. Policies: SELECT own and UPDATE
  own only. There is NO INSERT policy and NO DELETE
  policy, and no deduplication column or constraint.
- No function, trigger, or application code writes to
  `public.notifications` today.
- `private.notification_outbox` exists (channels push /
  email / sms / whatsapp; statuses pending / processing
  / sent / failed / cancelled; attempts; available_at;
  ready index on available_at) but nothing writes to it
  and nothing processes it. It is dormant infrastructure
  for FUTURE external channels and is not used for
  in-app delivery: the notifications table itself is the
  in-app delivery mechanism. M12 does not activate the
  outbox.
- No preferences table, no templates table, no cron or
  worker configuration exists in the repository, and
  SaveBite has no Render cron job or Supabase Cron
  configured.
- The service client may not write tables directly
  (enforced in code), and user-context inserts cannot
  create another user's notification. Therefore the
  only safe delivery path is a dedicated SECURITY
  DEFINER RPC called by the API layer through the
  service client, after a business operation succeeds.

## 2. Proposed change A — notification creation RPC + dedup

```sql
-- Add a stable deduplication key. A retried emission
-- with the same key must not create a second row.
alter table public.notifications
  add column dedup_key text;

create unique index notifications_dedup_key_idx
  on public.notifications (dedup_key)
  where dedup_key is not null;

-- Constrain event types to the M12 catalogue so no
-- caller can invent arbitrary types.
alter table public.notifications
  add constraint notifications_type_check
  check (notification_type in (
    'reservation_created', 'payment_captured',
    'payment_failed', 'reservation_expired',
    'pickup_reminder', 'pickup_completed',
    'order_cancelled', 'new_paid_order',
    'merchant_application_approved',
    'merchant_application_rejected',
    'store_approved', 'store_deactivated',
    'merchant_pickup_completed',
    'payment_reconciliation_required',
    'merchant_application_submitted',
    'merchant_application_reviewed'
  ));

-- SECURITY DEFINER so the function, not the caller,
-- is trusted to write rows for other users. The caller
-- must still be the API service role; the function
-- validates the event type via the CHECK above and
-- returns the existing row on a dedup-key conflict.
create or replace function public.backend_create_notification(
  p_user_id uuid,
  p_notification_type text,
  p_title text,
  p_body text,
  p_reference_type text,
  p_reference_id uuid,
  p_dedup_key text
) returns uuid
language plpgsql security definer
set search_path = public, pg_temp
as $$
declare
  v_id uuid;
begin
  insert into public.notifications
    (user_id, notification_type, title, body,
     reference_type, reference_id, dedup_key)
  values
    (p_user_id, p_notification_type, p_title, p_body,
     p_reference_type, p_reference_id, p_dedup_key)
  on conflict (dedup_key) where dedup_key is not null
    do nothing
  returning id into v_id;
  if v_id is null then
    select id into v_id
    from public.notifications
    where dedup_key = p_dedup_key;
  end if;
  return v_id;
end;
$$;

-- The API service client is the only caller. Grant
-- execution to the service role only; never to
-- authenticated users (a user-context caller must not
-- be able to create notifications for other users).
-- (Exact grant statement to be confirmed against the
-- live role model at approval time; do not guess it
-- in this proposal.)
```

Wiring, AFTER this RPC is applied and verified (not
before): the API layer calls backend_create_notification
through the service client, only after the business
operation succeeds, from: reservation creation
(reservation_created, customer), payment verify/webhook
capture (payment_captured, customer + new_paid_order,
merchant recipients), payment failure webhook
(payment_failed, customer), pickup verification
(pickup_completed, customer + merchant_pickup_completed,
merchant recipients), merchant/store review actions
(application/store events, merchant owner + admin
recipients). Recipients are resolved from verified
data (order.customer_id; merchant memberships + store
staff; platform roles via the M11 gate), never from
request fields. Emission failures must be logged with
the dedup key and must never roll back the business
operation that already succeeded; the recovery is a
reconciliation scan over order_status_events (to be
designed at that time, not claimed now).

## 3. Proposed change B — preferences table

```sql
create table public.notification_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  preferences jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.notification_preferences
  enable row level security;

create policy notification_preferences_select_own
  on public.notification_preferences for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy notification_preferences_upsert_own
  on public.notification_preferences for all
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));
```

Until this is applied, GET returns documented defaults
with persisted=false and PATCH validates then returns
501. Mandatory categories (payment_updates for
customers, operational_alerts for admins) can never be
disabled, enforced in code today and to be enforced by
the API after storage exists.

## 4. Proposed change C — reminder scheduler (deployment)

No code change is proposed for scheduling until a
scheduler exists. The requirement, when approved:

- A scheduled job (Supabase Cron / pg_cron, or a
  Render cron job calling an authenticated backend
  endpoint) that runs every 15 minutes and, for each
  order in status confirmed/ready_for_pickup with
  payment_status captured and pickup_starts_at within
  the next 2 hours (and, separately, the next 30
  minutes), emits pickup_reminder with dedup key
  `pickup_reminder:{order_id}:2h` or
  `pickup_reminder:{order_id}:30min` — only if no
  notification with that key exists.
- The job must use the same delivery RPC (change A)
  and must never emit for collected, cancelled, or
  expired orders, unpaid orders, or orders whose
  pickup window has passed.
- Until a scheduler is configured and verified, no
  reminder job runs and no reminder delivery is
  claimed. The eligibility logic (app/notifications.py
  reminder_due) is pure and tested, but unactivated.

## 5. Explicitly NOT proposed here

- No RLS bypass, no service-role table access, no
  private-schema access from the API.
- No INSERT policy on notifications for authenticated
  users (that would let any caller forge rows for
  other users only if the policy were miswritten; the
  RPC path keeps creation server-controlled).
- No outbox activation, no email/SMS/push/WhatsApp
  delivery, no promotional notifications.
- No change to order/payment state machines, no
  refund execution, no admin role promotion.
- No retention cleanup job (retention policy is an
  open product decision; unread and operationally
  relevant records must not be deleted without an
  approved rule).
