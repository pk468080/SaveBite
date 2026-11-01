-- W7: persistent notification preferences.
--
-- M12 returned documented defaults from GET (persisted=false) and
-- 501 from PATCH because no preferences table existed. This table
-- gives PATCH somewhere safe to store per-user settings, one row
-- per user, with one boolean column per M12 preference category
-- (see backend/app/notifications.py: DEFAULT_PREFERENCES).
--
-- Mandatory categories (payment_updates for customers,
-- operational_alerts for admins) can never be disabled: the API
-- validator rejects disabling them, and the CHECK below enforces
-- the same rule at the database level so no writer can bypass it.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply through the
-- normal migration process; this file only records the change.

create table public.notification_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  order_updates boolean not null default true,
  payment_updates boolean not null default true,
  pickup_reminders boolean not null default true,
  collection_confirmation boolean not null default true,
  new_paid_orders boolean not null default true,
  pickup_updates boolean not null default true,
  application_updates boolean not null default true,
  operational_alerts boolean not null default true,
  updated_at timestamptz not null default now(),
  constraint notification_preferences_mandatory_check
    check (payment_updates is true and operational_alerts is true)
);

alter table public.notification_preferences enable row level security;

create policy notification_preferences_select_own
  on public.notification_preferences for select
  to authenticated
  using ((user_id = (select auth.uid())));

create policy notification_preferences_insert_own
  on public.notification_preferences for insert
  to authenticated
  with check ((user_id = (select auth.uid())));

create policy notification_preferences_update_own
  on public.notification_preferences for update
  to authenticated
  using ((user_id = (select auth.uid())))
  with check ((user_id = (select auth.uid())));

create trigger notification_preferences_set_updated_at
  before update on public.notification_preferences
  for each row execute function public.set_updated_at();
