-- SaveBite W8 — EXECUTE grants for the W7 worker RPCs.
--
-- REQUIREMENT: the standalone notification worker calls
-- these two functions through the service-role client:
--   public.backend_process_notification_outbox(text, integer)
--   public.backend_enqueue_pickup_reminders(timestamptz, integer)
-- Both functions trust their caller (the processor can
-- claim, cancel, retry, and dead-letter any in-app job;
-- the reminder function trusts caller-supplied p_now and
-- p_window_minutes), so they must be executable by
-- service_role ONLY. The W7 delivery migration contains
-- no GRANT statements, and under Postgres defaults a
-- newly created function is executable by PUBLIC unless
-- revoked, so silence does not establish service-role-only
-- access. The application-level RPC allowlist constrains
-- only this repo's own backend/worker code, not direct
-- PostgREST /rpc/ callers.
--
-- This file revokes PUBLIC and grants service_role for
-- exactly these two functions. It grants nothing to
-- anon or authenticated, and it does not touch trigger
-- functions (not PostgREST-reachable) or the private
-- enqueue helper (not in the public schema exposed by
-- supabase/config.toml).
--
-- APPLY-TIME VERIFICATION (mandatory, before the worker
-- is pointed at these functions): run
-- has_function_privilege for anon, authenticated, and
-- service_role on both functions and confirm only
-- service_role holds EXECUTE. Apply in timestamp order
-- after the three W7 files.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply
-- through the normal migration process; this file only
-- records the change.

revoke execute on function public.backend_process_notification_outbox(text, integer) from public;
grant execute on function public.backend_process_notification_outbox(text, integer) to service_role;

revoke execute on function public.backend_enqueue_pickup_reminders(timestamptz, integer) from public;
grant execute on function public.backend_enqueue_pickup_reminders(timestamptz, integer) to service_role;
