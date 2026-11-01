-- Revoke worker RPC access from anon and authenticated.
--
-- ROOT CAUSE: Supabase default privileges grant EXECUTE on
-- newly created public-schema functions directly to the anon
-- and authenticated roles. The W8 grants file
-- (20261101131000) only revoked PUBLIC, which removes the
-- PUBLIC pseudo-role grant but not these direct grants, so
-- live verification showed anon and authenticated still
-- holding EXECUTE on both worker RPCs. This file removes
-- those direct grants, leaving service_role as the only
-- grantee besides the owner.
--
-- APPLY ORDER: apply this file in timestamp order after
-- the W7 and W8 files. It changes no table, trigger, or
-- function definition, only EXECUTE privileges.
--
-- MANDATORY APPLY-TIME VERIFICATION: run
-- has_function_privilege for anon, authenticated, and
-- service_role on both functions and confirm only
-- service_role holds EXECUTE.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply through
-- the normal migration process; this file only records the
-- change. Live remediation is handled separately.

revoke execute on function public.backend_process_notification_outbox(text, integer) from anon, authenticated;
revoke execute on function public.backend_enqueue_pickup_reminders(timestamptz, integer) from anon, authenticated;
