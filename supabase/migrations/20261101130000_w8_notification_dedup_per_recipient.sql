-- SaveBite W8 — per-recipient notification dedup keys.
--
-- BACKGROUND (read before applying):
-- The W7 delivery migration (20261101122000) defines
-- private.w7_enqueue_notification with a dedup key built as
--   p_notification_type || ':' || p_reference_id::text
-- with no user component, while the order/merchant/store
-- triggers call it once per recipient. The partial unique
-- indexes on private.notification_outbox (dedup_key) and
-- public.notifications (dedup_key) therefore drop every
-- recipient after the first for the same event + entity:
-- the second insert hits ON CONFLICT DO NOTHING and is
-- silently lost, contradicting the W7 header claim of
-- "one job row per recipient". Single-recipient events
-- (payment_captured, payment_failed, pickup_completed,
-- pickup_reminder) are unaffected.
--
-- FIX (this file only, no W7 file is edited in place):
-- The key now embeds the recipient:
--   type || ':' || reference_id || ':' || user_id
-- The existing single-column partial unique indexes keep
-- working unchanged, because the key itself is now unique
-- per recipient. The processor copies job.dedup_key into
-- public.notifications, so delivery-side dedup follows
-- the same key. The already-documented same-recipient
-- repeat limitation (e.g. approve -> reject -> approve
-- reuses one key) is unchanged by this fix.
--
-- APPLY ORDER (mandatory): apply the three W7 files and
-- this file in timestamp order, in one release, BEFORE
-- the notification worker is started. The W7 migrations
-- are not applied to live yet, so no live row carries an
-- old-format key; do not start the worker between the W7
-- files and this file.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply
-- through the normal migration process; this file only
-- records the change.

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
     p_notification_type || ':' || p_reference_id::text || ':' || p_user_id::text,
     p_category,
     jsonb_build_object('event', p_notification_type))
  on conflict (dedup_key) where dedup_key is not null do nothing;
end;
$function$;
