-- W7: extend the dormant private notification outbox for in-app
-- delivery.
--
-- M12 left private.notification_outbox as dormant external-channel
-- infrastructure (channels push/email/sms/whatsapp, no writer, no
-- processor). W7 reuses this one table as the transactional outbox
-- for in-app notifications instead of creating a second queue:
--
-- - channel gains 'in_app'. Rows for the future external
--   channels are untouched by the W7 processor, which claims only
--   channel = 'in_app' rows, so a later external-channel
--   processor can coexist on this table.
-- - template_key carries the catalogue event type for in-app rows
--   (the table requires template_key NOT NULL).
-- - notification_type/title/body/reference_* mirror the row the
--   processor will insert into public.notifications, so delivery
--   needs no second lookup.
-- - dedup_key is the stable (event, source) key from
--   backend/app/notifications.py: dedup_key(). The partial unique
--   index makes retries and repeated scheduler runs safe: a
--   second enqueue with the same key is a no-op, never a
--   duplicate notification.
-- - claimed_by/claimed_at implement the worker claim with
--   expiry: a row stuck in 'processing' past the claim window
--   is reclaimable, so a crashed worker cannot lose jobs.
--
-- Status vocabulary is unchanged (pending/processing/sent/
-- failed/cancelled): a retryable failure returns the row to
-- 'pending' with a future available_at; a row that exhausts its
-- attempts stays 'failed' and is never reclaimed (the dead-
-- letter state); a preference-disabled row is 'cancelled'.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply through the
-- normal migration process; this file only records the change.

alter table private.notification_outbox
  add column notification_type text,
  add column title text,
  add column body text,
  add column reference_type text,
  add column reference_id uuid,
  add column dedup_key text,
  add column category text,
  add column claimed_by text,
  add column claimed_at timestamptz;

alter table private.notification_outbox
  drop constraint notification_outbox_channel_check;

alter table private.notification_outbox
  add constraint notification_outbox_channel_check
  check (channel = any (array['push'::text, 'email'::text, 'sms'::text, 'whatsapp'::text, 'in_app'::text]));

create unique index notification_outbox_dedup_key_idx
  on private.notification_outbox (dedup_key)
  where dedup_key is not null;

create index notification_outbox_processing_claim_idx
  on private.notification_outbox (claimed_at)
  where status = 'processing';
