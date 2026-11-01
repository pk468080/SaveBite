-- W7: in-app notification delivery.
--
-- What this migration activates, and what it deliberately does not:
--
-- ACTIVATED (transactional outbox, same-transaction enqueue):
-- Business-state transitions enqueue in-app notification jobs
-- into private.notification_outbox IN THE SAME transaction as
-- the business change, so a notification can never be created
-- for a rolled-back operation, and a committed operation can
-- never lose its notification to a crash between the business
-- commit and a separate emission call (the failure mode of the
-- M12 post-commit proposal, which this supersedes).
--   orders.payment_status -> captured  : payment_captured
--     (customer) + new_paid_order (merchant recipients)
--   orders.payment_status -> failed    : payment_failed (customer)
--   orders.payment_status -> reconciliation_required
--     : payment_reconciliation_required (admin recipients)
--   orders.status -> collected         : pickup_completed
--     (customer) + merchant_pickup_completed (merchants)
--   merchants INSERT                  : merchant_application_submitted
--     (admin recipients)
--   merchants.status -> approved      : merchant_application_approved
--     (merchant) + merchant_application_reviewed (admins)
--   merchants.status -> rejected      : merchant_application_rejected
--     (merchant) + merchant_application_reviewed (admins)
--   stores.status -> active           : store_approved (merchant)
--   stores.status -> inactive         : store_deactivated (merchant)
--
-- DELIBERATELY NOT EMITTED (no authoritative trigger exists):
-- reservation_created (the W7 brief forbids notifying on an
-- unpaid reservation), reservation_expired (the expiry RPC
-- backend_release_expired_reservations has no caller/scheduler),
-- order_cancelled (no order-cancel route exists), and any refund
-- event (request_refund has no route caller and
-- backend_update_refund_status has no caller). Adding any of
-- these requires a real business trigger first, not a new
-- notification type alone.
--
-- DEDUPLICATION: every job carries dedup_key
-- '<event_type>:<source_id>'. A repeated webhook retry cannot
-- re-fire a trigger (the transition guard OLD vs NEW means the
-- second, no-op call changes nothing), and a repeated worker
-- delivery cannot duplicate a row (ON CONFLICT DO NOTHING on
-- the partial unique index). One documented limitation: a
-- second identical decision for the same entity (e.g. a
-- merchant approved, rejected, then approved again) reuses the
-- same dedup key, so only the first notification is kept; the
-- portal always shows the current status.
--
-- SECURITY: all functions below are SECURITY DEFINER with a
-- pinned empty search_path and fully qualified names. That is
-- required, not incidental: a merchant staff member verifying
-- a pickup acts under RLS and can only see their own rows, but
-- the collection trigger must resolve ALL merchant recipients
-- (owner/admin members + store managers/pickup operators).
-- Recipients are resolved only from authoritative database
-- relationships, never from request data. No function here
-- grants anything to authenticated users, and no INSERT policy
-- is added to public.notifications: only the service-role
-- worker (via backend_process_notification_outbox) and these
-- triggers can create notification rows.
--
-- APPLY-TIME CHECKS (do not guess these in this file):
-- - The notifications type CHECK below requires every existing
--   row to carry a catalogue type. That holds today because
--   nothing writes to the table; if rows with other types exist
--   at apply time, this migration fails loudly and must be
--   reviewed, not forced.
-- - Confirm EXECUTE on backend_process_notification_outbox and
--   backend_enqueue_pickup_reminders for the service role before
--   the worker is pointed at them.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply through the
-- normal migration process; this file only records the change.

-- --- 1. Deduplication + catalogue constraint on notifications ---

alter table public.notifications
  add column dedup_key text;

create unique index notifications_dedup_key_idx
  on public.notifications (dedup_key)
  where dedup_key is not null;

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

-- --- 2. Single enqueue helper (one job row per recipient) ---

create or replace function private.w7_enqueue_notification(
  p_user_id uuid,
  p_notification_type text,
  p_title text,
  p_body text,
  p_reference_type text,
  p_reference_id uuid,
  p_category text
)
returns void
language plpgsql
security definer
set search_path = ''
as $function$
begin
  insert into private.notification_outbox
    (user_id, channel, template_key, notification_type, title, body,
     reference_type, reference_id, dedup_key, category, payload)
  values
    (p_user_id, 'in_app', p_notification_type, p_notification_type,
     p_title, p_body, p_reference_type, p_reference_id,
     p_notification_type || ':' || p_reference_id::text, p_category,
     jsonb_build_object('event', p_notification_type))
  on conflict (dedup_key) where dedup_key is not null do nothing;
end;
$function$;

-- --- 3. Order transition trigger ---

create or replace function public.w7_enqueue_order_notifications()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_store_name text;
  v_recipient uuid;
begin
  if tg_op <> 'UPDATE' then
    return NEW;
  end if;
  select name into v_store_name from public.stores where id = NEW.store_id;

  if NEW.payment_status = 'captured'
     and OLD.payment_status is distinct from 'captured' then
    perform private.w7_enqueue_notification(
      NEW.customer_id, 'payment_captured', 'Payment successful',
      'Payment for order ' || NEW.order_number || ' was captured successfully.',
      'order', NEW.id, 'payment_updates');
    for v_recipient in
      select user_id from public.merchant_memberships
        where merchant_id = NEW.merchant_id
          and is_active is true and role in ('owner', 'admin')
      union
      select user_id from public.store_staff_memberships
        where store_id = NEW.store_id
          and is_active is true and role in ('store_manager', 'pickup_operator')
    loop
      perform private.w7_enqueue_notification(
        v_recipient, 'new_paid_order', 'New paid order',
        'A customer paid for order ' || NEW.order_number
          || ' at ' || coalesce(v_store_name, '') || '.',
        'order', NEW.id, 'new_paid_orders');
    end loop;
  end if;

  if NEW.payment_status = 'failed'
     and OLD.payment_status is distinct from 'failed' then
    perform private.w7_enqueue_notification(
      NEW.customer_id, 'payment_failed', 'Payment failed',
      'Payment for order ' || NEW.order_number
        || ' failed. Your reservation may expire if payment is not completed.',
      'order', NEW.id, 'payment_updates');
  end if;

  if NEW.payment_status = 'reconciliation_required'
     and OLD.payment_status is distinct from 'reconciliation_required' then
    for v_recipient in
      select user_id from public.platform_user_roles
        where role in ('operations_admin', 'super_admin')
          and revoked_at is null
    loop
      perform private.w7_enqueue_notification(
        v_recipient, 'payment_reconciliation_required',
        'Payment needs reconciliation',
        'Order ' || NEW.order_number
          || ' requires payment reconciliation. Investigate before taking further action.',
        'order', NEW.id, 'operational_alerts');
    end loop;
  end if;

  if NEW.status = 'collected'
     and OLD.status is distinct from 'collected' then
    perform private.w7_enqueue_notification(
      NEW.customer_id, 'pickup_completed', 'Pickup completed',
      'Your order ' || NEW.order_number || ' was collected successfully.',
      'order', NEW.id, 'collection_confirmation');
    for v_recipient in
      select user_id from public.merchant_memberships
        where merchant_id = NEW.merchant_id
          and is_active is true and role in ('owner', 'admin')
      union
      select user_id from public.store_staff_memberships
        where store_id = NEW.store_id
          and is_active is true and role in ('store_manager', 'pickup_operator')
    loop
      perform private.w7_enqueue_notification(
        v_recipient, 'merchant_pickup_completed', 'Pickup completed',
        'Order ' || NEW.order_number || ' was collected at '
          || coalesce(v_store_name, '') || '.',
        'order', NEW.id, 'pickup_updates');
    end loop;
  end if;

  return NEW;
end;
$function$;

create trigger w7_order_notifications
  after update on public.orders
  for each row execute function public.w7_enqueue_order_notifications();

-- --- 4. Merchant application trigger ---

create or replace function public.w7_enqueue_merchant_notifications()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_recipient uuid;
begin
  if tg_op = 'INSERT' then
    for v_recipient in
      select user_id from public.platform_user_roles
        where role in ('operations_admin', 'super_admin')
          and revoked_at is null
    loop
      perform private.w7_enqueue_notification(
        v_recipient, 'merchant_application_submitted',
        'New merchant application',
        'A new merchant application was submitted for review.',
        'merchant', NEW.id, 'operational_alerts');
    end loop;
    return NEW;
  end if;

  if tg_op = 'UPDATE' and OLD.status is distinct from NEW.status then
    if NEW.status = 'approved' then
      for v_recipient in
        select NEW.created_by
        union
        select user_id from public.merchant_memberships
          where merchant_id = NEW.id
            and is_active is true and role in ('owner', 'admin')
      loop
        perform private.w7_enqueue_notification(
          v_recipient, 'merchant_application_approved',
          'Merchant application approved',
          'Your merchant application for ' || NEW.display_name || ' was approved.',
          'merchant', NEW.id, 'application_updates');
      end loop;
    elsif NEW.status = 'rejected' then
      for v_recipient in
        select NEW.created_by
        union
        select user_id from public.merchant_memberships
          where merchant_id = NEW.id
            and is_active is true and role in ('owner', 'admin')
      loop
        perform private.w7_enqueue_notification(
          v_recipient, 'merchant_application_rejected',
          'Merchant application needs attention',
          'Your merchant application for ' || NEW.display_name
            || ' was not approved. Check the review notes.',
          'merchant', NEW.id, 'application_updates');
      end loop;
    else
      return NEW;
    end if;
    for v_recipient in
      select user_id from public.platform_user_roles
        where role in ('operations_admin', 'super_admin')
          and revoked_at is null
    loop
      perform private.w7_enqueue_notification(
        v_recipient, 'merchant_application_reviewed',
        'Merchant application reviewed',
        'A merchant application was reviewed.',
        'merchant', NEW.id, 'operational_alerts');
    end loop;
  end if;

  return NEW;
end;
$function$;

create trigger w7_merchant_notifications
  after insert or update on public.merchants
  for each row execute function public.w7_enqueue_merchant_notifications();

-- --- 5. Store activation trigger ---

create or replace function public.w7_enqueue_store_notifications()
returns trigger
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_recipient uuid;
begin
  if tg_op <> 'UPDATE' or OLD.status is distinct from NEW.status then
    if NEW.status = 'active' then
      for v_recipient in
        select created_by from public.merchants where id = NEW.merchant_id
        union
        select user_id from public.merchant_memberships
          where merchant_id = NEW.merchant_id
            and is_active is true and role in ('owner', 'admin')
        union
        select user_id from public.store_staff_memberships
          where store_id = NEW.id
            and is_active is true and role in ('store_manager', 'pickup_operator')
      loop
        perform private.w7_enqueue_notification(
          v_recipient, 'store_approved', 'Store approved',
          'Your store ' || NEW.name || ' was activated.',
          'store', NEW.id, 'application_updates');
      end loop;
    elsif NEW.status = 'inactive' then
      for v_recipient in
        select created_by from public.merchants where id = NEW.merchant_id
        union
        select user_id from public.merchant_memberships
          where merchant_id = NEW.merchant_id
            and is_active is true and role in ('owner', 'admin')
        union
        select user_id from public.store_staff_memberships
          where store_id = NEW.id
            and is_active is true and role in ('store_manager', 'pickup_operator')
      loop
        perform private.w7_enqueue_notification(
          v_recipient, 'store_deactivated', 'Store deactivated',
          'Your store ' || NEW.name || ' was deactivated.',
          'store', NEW.id, 'application_updates');
      end loop;
    end if;
  end if;

  return NEW;
end;
$function$;

create trigger w7_store_notifications
  after update on public.stores
  for each row execute function public.w7_enqueue_store_notifications();

-- --- 6. Outbox processor (called by the worker, service role only) ---
--
-- Claims a bounded batch of due 'in_app' jobs with FOR UPDATE
-- SKIP LOCKED, so concurrent workers claim disjoint sets. A row
-- stuck in 'processing' past a 10-minute claim window is
-- reclaimable, so a crashed worker cannot lose jobs. Each job
-- runs in its own subtransaction: one bad payload retries or
-- dies without rolling back the rest of the batch.
-- Preference check happens here, at delivery: a category the
-- recipient disabled is skipped (row -> 'cancelled'), never
-- delivered. Mandatory categories (payment_updates,
-- operational_alerts) are always delivered. Delivery itself is
-- idempotent: the notifications insert uses ON CONFLICT on the
-- dedup key, so reprocessing a job cannot duplicate a row.
-- Retry: bounded exponential backoff (about 1, 2, 4, 8 minutes,
-- capped at 30), at most 5 attempts; the 5th failure leaves the
-- row 'failed', which the claim query never reclaims: that is
-- the dead-letter state. Only counts are returned; no payloads
-- or personal data leave the database through this function.

create or replace function public.backend_process_notification_outbox(
  p_worker_id text,
  p_batch_size integer default 50
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  job record;
  v_pref record;
  v_enabled boolean;
  v_processed integer := 0;
  v_delivered integer := 0;
  v_skipped integer := 0;
  v_retried integer := 0;
  v_dead integer := 0;
begin
  if p_batch_size < 1 then
    p_batch_size := 1;
  elsif p_batch_size > 200 then
    p_batch_size := 200;
  end if;

  for job in
    select * from private.notification_outbox
    where channel = 'in_app'
      and ((status = 'pending' and available_at <= now())
        or (status = 'processing'
          and claimed_at < now() - interval '10 minutes'))
    order by created_at
    limit p_batch_size
    for update skip locked
  loop
    v_processed := v_processed + 1;
    begin
      update private.notification_outbox
        set status = 'processing', claimed_by = p_worker_id, claimed_at = now()
        where id = job.id;

      select * into v_pref
        from public.notification_preferences
        where user_id = job.user_id;
      v_enabled := case job.category
        when 'order_updates' then coalesce(v_pref.order_updates, true)
        when 'payment_updates' then true
        when 'pickup_reminders' then coalesce(v_pref.pickup_reminders, true)
        when 'collection_confirmation' then coalesce(v_pref.collection_confirmation, true)
        when 'new_paid_orders' then coalesce(v_pref.new_paid_orders, true)
        when 'pickup_updates' then coalesce(v_pref.pickup_updates, true)
        when 'application_updates' then coalesce(v_pref.application_updates, true)
        when 'operational_alerts' then true
        else true
      end;

      if not v_enabled then
        update private.notification_outbox
          set status = 'cancelled', last_error = 'preference_disabled',
            claimed_by = null, claimed_at = null
          where id = job.id;
        v_skipped := v_skipped + 1;
      else
        insert into public.notifications
          (user_id, notification_type, title, body,
           reference_type, reference_id, dedup_key)
        values
          (job.user_id, job.notification_type, job.title, job.body,
           job.reference_type, job.reference_id, job.dedup_key)
        on conflict (dedup_key) where dedup_key is not null do nothing;

        update private.notification_outbox
          set status = 'sent', sent_at = now(), last_error = null,
            claimed_by = null, claimed_at = null
          where id = job.id;
        v_delivered := v_delivered + 1;
      end if;
    exception when others then
      if job.attempts + 1 >= 5 then
        update private.notification_outbox
          set status = 'failed', attempts = job.attempts + 1,
            last_error = left(sqlerrm, 500),
            claimed_by = null, claimed_at = null
          where id = job.id;
        v_dead := v_dead + 1;
      else
        update private.notification_outbox
          set status = 'pending', attempts = job.attempts + 1,
            available_at = now() + least(
              power(2, job.attempts + 1) * interval '30 seconds',
              interval '30 minutes'),
            last_error = left(sqlerrm, 500),
            claimed_by = null, claimed_at = null
          where id = job.id;
        v_retried := v_retried + 1;
      end if;
    end;
  end loop;

  return jsonb_build_object(
    'processed', v_processed,
    'delivered', v_delivered,
    'skipped', v_skipped,
    'retried', v_retried,
    'dead', v_dead
  );
end;
$function$;

-- --- 7. Pickup reminder enqueue (called by the worker/scheduler) ---
--
-- Mirrors app/notifications.py: reminder_due() exactly: only
-- confirmed/ready_for_pickup orders with payment captured, where
-- now falls inside [pickup_starts_at - window, pickup_starts_at).
-- Comparisons use absolute instants; the store timezone affects
-- display only, never eligibility. Collected, cancelled,
-- expired, unpaid, and past-window orders are never enqueued.
-- Re-running is safe: a cancelled job does not block a later
-- re-enqueue (so re-enabling reminders can still deliver), but
-- any live job or delivered notification with the same dedup
-- key does. Returns the number of jobs enqueued.

create or replace function public.backend_enqueue_pickup_reminders(
  p_now timestamptz,
  p_window_minutes integer default 60
)
returns integer
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_count integer := 0;
begin
  insert into private.notification_outbox
    (user_id, channel, template_key, notification_type, title, body,
     reference_type, reference_id, dedup_key, category, payload)
  select
    o.customer_id, 'in_app', 'pickup_reminder', 'pickup_reminder',
    'Pickup reminder',
    'Your pickup for order ' || o.order_number || ' at ' || s.name || ' starts soon.',
    'order', o.id, 'pickup_reminder:' || o.id, 'pickup_reminders',
    jsonb_build_object('event', 'pickup_reminder')
  from public.orders o
  join public.stores s on s.id = o.store_id
  where o.status in ('confirmed', 'ready_for_pickup')
    and o.payment_status = 'captured'
    and o.pickup_starts_at - make_interval(mins => p_window_minutes) <= p_now
    and p_now < o.pickup_starts_at
    and not exists (
      select 1 from private.notification_outbox j
      where j.dedup_key = 'pickup_reminder:' || o.id
        and j.status <> 'cancelled'
    )
    and not exists (
      select 1 from public.notifications n
      where n.dedup_key = 'pickup_reminder:' || o.id
    )
  on conflict (dedup_key) where dedup_key is not null do nothing;

  get diagnostics v_count = row_count;
  return v_count;
end;
$function$;
