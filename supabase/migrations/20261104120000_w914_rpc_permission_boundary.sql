-- SaveBite W9.1.4 — RPC permission boundary correction.
--
-- DEFECT (found in W9.1.3, docs/w9-1-3-staging-validation.md §3):
-- Every public backend_* wrapper is LANGUAGE sql, SECURITY INVOKER,
-- with a pinned empty search_path, and its body is a single call to a
-- private.* function. An invoker wrapper therefore requires the CALLER
-- to hold USAGE on schema private AND EXECUTE on the private function.
-- No migration in the chain grants USAGE ON SCHEMA private to anyone,
-- so a real PostgREST call to a backend_* wrapper failed with
-- 403 "permission denied for schema private" — before any function
-- body ran. The one-line fix tested in W9.1.3's disposable database
-- (GRANT USAGE ON SCHEMA private TO service_role) is NOT sufficient
-- on its own, and is NOT what this migration does: it would leave
-- the second, wider defect in place — every private function keeps
-- PostgreSQL's default PUBLIC EXECUTE privilege, because no migration
-- ever revoked it. The missing USAGE grant was, until now, the only
-- thing stopping anon/authenticated from calling private functions
-- directly (in any context where they hold schema USAGE, or via a
-- future grant). This migration fixes both defects together, with
-- explicit per-function grants only.
--
-- DESIGN (hybrid Option A, no wrapper conversion — see
-- docs/w9-1-4-rpc-permission-boundary.md §5 for the full evaluation):
-- * Keep every public wrapper SECURITY INVOKER, with its existing
--   owner, signature, return type, pinned empty search_path and body.
--   This file contains NO CREATE OR REPLACE FUNCTION and changes no
--   business logic, no RLS policy, and no trigger. Converting wrappers
--   to SECURITY DEFINER was rejected: the private implementations are
--   already SECURITY DEFINER with auth.uid() checks, so conversion
--   would not change nested authorisation, but it would collapse the
--   two-layer gate (wrapper EXECUTE + private EXECUTE + schema USAGE)
--   into a single wrapper gate, and would let a future loosening of a
--   wrapper grant silently expose definer execution. Invoker wrappers
--   keep the existing authorisation model exactly as tested.
-- * Grant USAGE ON SCHEMA private ONLY to authenticated and
--   service_role — the two roles that call invoker public wrappers
--   whose bodies reference private.*. NEVER to PUBLIC, and NEVER to
--   anon (see the anon/RLS note below).
-- * Revoke EXECUTE on EVERY private function from PUBLIC, anon,
--   authenticated and service_role, then re-grant EXECUTE only on the
--   exact private functions each caller path provably needs:
--     - service_role: the 12 private implementations behind the 14
--       public backend_* wrappers (the two W7 processor functions are
--       public DEFINER functions with no private implementation, and
--       the v2 wrapper's implementation is counted once).
--     - authenticated: the 8 private implementations behind the 8
--       user-context wrappers, plus the 5 private RLS helper functions
--       that RLS policies call for authenticated table reads
--       (can_manage_store, can_view_order, has_platform_role,
--       is_merchant_member, is_store_public).
--     - anon: EXECUTE on 3 read-only, STABLE, SECURITY DEFINER RLS
--       helpers only (can_manage_store, has_platform_role,
--       is_store_public), which the public-catalogue RLS policies
--       (listings, stores, store_hours, listing_images) call for
--       anonymous reads. Anon gets NO schema USAGE and NO EXECUTE on
--       any business function. See the RLS note: this works because
--       RLS policy evaluation invokes a SECURITY DEFINER helper as
--       its owner; the disposable PG 17 tests in
--       backend/tests/test_w914_rpc_permission_boundary.py prove an
--       anonymous catalogue read still succeeds with USAGE denied
--       and prove it fails again if those three EXECUTE grants are
--       removed (test_anon_rls_helpers_required). If a future
--       PostgreSQL/Supabase behaviour change ever makes anon reads
--       require USAGE, the correct fix is a separate, reviewed
--       decision — not a silent USAGE grant in this file.
-- * Deliberately NO grant to any application role on:
--     - private.w7_enqueue_notification — called only by the
--       SECURITY DEFINER trigger functions and the DEFINER outbox
--       processor, which run as their owner; a direct grant is not
--       needed and would expose the outbox writer.
--     - private.prevent_posted_ledger_entry_mutation and
--       private.prevent_posted_ledger_transaction_mutation — trigger
--       functions; PostgreSQL invokes trigger functions as the table
--       owner and does not check EXECUTE on them.
--     - private.handle_new_auth_user — the auth.users trigger
--       function; invoked by the auth system, not by application
--       roles, and not attached to any application table in this
--       migration chain (see docs §3).
--     - Any other private function for a role that has no wrapper or
--       RLS path to it (e.g. service_role gets no EXECUTE on the
--       customer/merchant implementations, and authenticated gets no
--       EXECUTE on the server-only implementations).
-- * Public wrappers are re-asserted to their intended grantees:
--     - user-context wrappers (8): authenticated ONLY (revoked from
--       PUBLIC, anon and service_role — the backend's service-role
--       client is forbidden by app code from calling user-context
--       RPCs, and the database now enforces the same separation).
--     - backend_* wrappers (14): service_role ONLY (revoked from
--       PUBLIC, anon and authenticated; re-asserted for the four
--       wrappers already restricted by W7/W8/B1/W9.1, so this file
--       does not depend on their grant state).
--     - public trigger functions (w7_enqueue_*, set_updated_at):
--       revoked from PUBLIC, anon, authenticated and service_role.
--       Trigger invocation does not check EXECUTE, so triggers keep
--       firing; direct RPC-style invocation of a trigger function
--       is no longer possible. Proven by Test 8 in the test module.
-- * Default privileges: DELIBERATELY NOT CHANGED. This was tested
--   on disposable PostgreSQL 17.11 and PROVEN ineffective:
--   ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE EXECUTE ON
--   FUNCTIONS FROM PUBLIC creates no pg_default_acl row and leaves
--   a subsequently created private function PUBLIC-executable
--   (has_function_privilege('anon', ...) = true), because default
--   grants are unioned with the built-in PUBLIC grant and a REVOKE
--   in default privileges only removes grants stored in the default
--   ACL itself. The only removal that works is an explicit
--   REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC on each function,
--   which is exactly what §2 does for every existing function.
--   Therefore every future migration that creates a private
--   function MUST include its own explicit REVOKE FROM PUBLIC
--   (and, where needed, explicit GRANTs), exactly as W8/B1/W9.1
--   already do for public wrappers. A default-privileges clause
--   that claims otherwise would be security theatre and is
--   omitted on purpose. See Test 10 in
--   backend/tests/test_w914_rpc_permission_boundary.py, which
--   asserts this behaviour rather than hiding it.
--
-- PRECONDITIONS (all must hold before applying; the migration fails
-- loudly otherwise, which is the intended behaviour — do not force):
-- * Applied in timestamp order after every earlier migration in
--   supabase/migrations/, i.e. after the baseline tracking copy's
--   live equivalents, W7, W8, B1, W9.1 and W9.1.1. Every function
--   named below must already exist with exactly the signature shown;
--   a GRANT/REVOKE on a missing function errors and aborts the file.
-- * Roles anon, authenticated and service_role exist (Supabase
--   default roles; in a disposable database they are created by
--   backend/tests/pg_bootstrap.py pre-steps).
-- * Run as the function owner (in Supabase, postgres) or a superuser:
--   only the owner/superuser may revoke PUBLIC grants on a function.
-- * This file is forward-only. It does not edit, replay or repair
--   any earlier migration, and it does not touch the consolidated
--   baseline tracking copy (20261031060000), which must never be
--   replayed against a live database.
--
-- POSTCONDITIONS (verify after applying; see docs §11 for commands):
-- * has_schema_privilege('service_role','private','USAGE') = true;
--   has_schema_privilege('authenticated','private','USAGE') = true;
--   has_schema_privilege('anon','private','USAGE') = false;
--   has_schema_privilege('PUBLIC','private','USAGE') = false.
-- * has_function_privilege matches the matrix in docs §7 for every
--   private function and every public wrapper (owner always true).
-- * No function owner, security mode, search_path, signature, return
--   type or body has changed (this file contains no function
--   definition at all — verified by Test 9 in the test module).
-- * No RLS policy, trigger or table has changed.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply through the
-- normal migration process (staging first, with its own approval);
-- this file only records the change. Never run supabase db push
-- from this branch, and never apply it to production on the basis
-- of disposable-database evidence alone.

-- --- 1. Schema USAGE: only the two wrapper-calling roles. ---

revoke usage on schema private from public;
revoke usage on schema private from anon;
grant usage on schema private to authenticated;
grant usage on schema private to service_role;

-- --- 2. Private functions: revoke everything, then grant exactly. ---

revoke execute on all functions in schema private from public;
revoke execute on all functions in schema private from anon;
revoke execute on all functions in schema private from authenticated;
revoke execute on all functions in schema private from service_role;

-- 2a. service_role: private implementations behind backend_* wrappers.

grant execute on function private.attach_gateway_order(uuid, text) to service_role;
grant execute on function private.confirm_payment_capture(uuid, text, numeric, boolean) to service_role;
grant execute on function private.mark_payment_failed(uuid, text, text) to service_role;
grant execute on function private.post_ledger_transaction(text, uuid, text, character, jsonb) to service_role;
grant execute on function private.record_payment_webhook_event(text, text, text, jsonb, boolean) to service_role;
grant execute on function private.release_expired_inventory_reservations(integer) to service_role;
grant execute on function private.reverse_ledger_transaction(uuid, text, uuid) to service_role;
grant execute on function private.review_merchant_application(uuid, public.merchant_status, public.verification_status, text, uuid) to service_role;
grant execute on function private.review_store_activation(uuid, boolean, uuid, text) to service_role;
grant execute on function private.update_refund_status(uuid, public.refund_status, uuid, text, text, text) to service_role;
grant execute on function private.get_gateway_order_for_payment_transaction(uuid, uuid) to service_role;
grant execute on function private.release_expired_reservations_v2(integer) to service_role;

-- 2b. authenticated: private implementations behind user-context wrappers.

grant execute on function private.apply_merchant_application(text, text, public.merchant_business_type, text, text) to authenticated;
grant execute on function private.begin_payment_checkout(uuid, text) to authenticated;
grant execute on function private.create_merchant_store(uuid, text, text, text, text, text, text, text, text, double precision, double precision, text, text) to authenticated;
grant execute on function private.create_order_reservation(uuid, jsonb, text, text) to authenticated;
grant execute on function private.issue_pickup_token(uuid) to authenticated;
grant execute on function private.request_order_refund(uuid, text, text) to authenticated;
grant execute on function private.upsert_store_hours(uuid, jsonb) to authenticated;
grant execute on function private.verify_pickup_token(uuid, text) to authenticated;

-- 2c. authenticated + anon: read-only RLS helper functions only.
-- These are STABLE, SECURITY DEFINER, and check auth.uid() against
-- authoritative membership/role tables; they return a boolean and
-- expose no row data themselves. Authenticated needs all five (its
-- table policies call can_view_order and is_merchant_member too);
-- anon needs only the three its public-catalogue policies call.

grant execute on function private.can_manage_store(uuid, public.merchant_member_role[]) to authenticated;
grant execute on function private.can_manage_store(uuid, public.merchant_member_role[]) to anon;
grant execute on function private.can_view_order(uuid) to authenticated;
grant execute on function private.has_platform_role(public.platform_role[]) to authenticated;
grant execute on function private.has_platform_role(public.platform_role[]) to anon;
grant execute on function private.is_merchant_member(uuid, public.merchant_member_role[]) to authenticated;
grant execute on function private.is_store_public(uuid) to authenticated;
grant execute on function private.is_store_public(uuid) to anon;

-- --- 3. Public wrappers: re-assert intended grantees. ---

-- 3a. User-context wrappers: authenticated only.

revoke execute on function public.apply_merchant_application(text, text, public.merchant_business_type, text, text) from public, anon, service_role;
grant execute on function public.apply_merchant_application(text, text, public.merchant_business_type, text, text) to authenticated;

revoke execute on function public.create_merchant_store(uuid, text, text, text, text, text, text, text, text, double precision, double precision, text, text) from public, anon, service_role;
grant execute on function public.create_merchant_store(uuid, text, text, text, text, text, text, text, text, double precision, double precision, text, text) to authenticated;

revoke execute on function public.upsert_store_hours(uuid, jsonb) from public, anon, service_role;
grant execute on function public.upsert_store_hours(uuid, jsonb) to authenticated;

revoke execute on function public.create_order_reservation(uuid, jsonb, text, text) from public, anon, service_role;
grant execute on function public.create_order_reservation(uuid, jsonb, text, text) to authenticated;

revoke execute on function public.begin_payment_checkout(uuid, text) from public, anon, service_role;
grant execute on function public.begin_payment_checkout(uuid, text) to authenticated;

revoke execute on function public.issue_pickup_token(uuid) from public, anon, service_role;
grant execute on function public.issue_pickup_token(uuid) to authenticated;

revoke execute on function public.verify_pickup_token(uuid, text) from public, anon, service_role;
grant execute on function public.verify_pickup_token(uuid, text) to authenticated;

revoke execute on function public.request_refund(uuid, text, text) from public, anon, service_role;
grant execute on function public.request_refund(uuid, text, text) to authenticated;

-- 3b. Server-only backend_* wrappers: service_role only.
-- (The four already restricted by W7/W8/B1/W9.1 are re-asserted here
-- so this file is complete on its own and idempotent.)

revoke execute on function public.backend_attach_gateway_order(uuid, text) from public, anon, authenticated;
grant execute on function public.backend_attach_gateway_order(uuid, text) to service_role;

revoke execute on function public.backend_confirm_payment_capture(uuid, text, numeric, boolean) from public, anon, authenticated;
grant execute on function public.backend_confirm_payment_capture(uuid, text, numeric, boolean) to service_role;

revoke execute on function public.backend_mark_payment_failed(uuid, text, text) from public, anon, authenticated;
grant execute on function public.backend_mark_payment_failed(uuid, text, text) to service_role;

revoke execute on function public.backend_post_ledger_transaction(text, uuid, text, character, jsonb) from public, anon, authenticated;
grant execute on function public.backend_post_ledger_transaction(text, uuid, text, character, jsonb) to service_role;

revoke execute on function public.backend_record_payment_webhook_event(text, text, text, jsonb, boolean) from public, anon, authenticated;
grant execute on function public.backend_record_payment_webhook_event(text, text, text, jsonb, boolean) to service_role;

revoke execute on function public.backend_release_expired_reservations(integer) from public, anon, authenticated;
grant execute on function public.backend_release_expired_reservations(integer) to service_role;

revoke execute on function public.backend_reverse_ledger_transaction(uuid, text, uuid) from public, anon, authenticated;
grant execute on function public.backend_reverse_ledger_transaction(uuid, text, uuid) to service_role;

revoke execute on function public.backend_review_merchant(uuid, public.merchant_status, public.verification_status, text, uuid) from public, anon, authenticated;
grant execute on function public.backend_review_merchant(uuid, public.merchant_status, public.verification_status, text, uuid) to service_role;

revoke execute on function public.backend_review_store(uuid, boolean, uuid, text) from public, anon, authenticated;
grant execute on function public.backend_review_store(uuid, boolean, uuid, text) to service_role;

revoke execute on function public.backend_update_refund_status(uuid, public.refund_status, uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.backend_update_refund_status(uuid, public.refund_status, uuid, text, text, text) to service_role;

revoke execute on function public.backend_process_notification_outbox(text, integer) from public, anon, authenticated;
grant execute on function public.backend_process_notification_outbox(text, integer) to service_role;

revoke execute on function public.backend_enqueue_pickup_reminders(timestamptz, integer) from public, anon, authenticated;
grant execute on function public.backend_enqueue_pickup_reminders(timestamptz, integer) to service_role;

revoke execute on function public.backend_get_gateway_order_for_payment_transaction(uuid, uuid) from public, anon, authenticated;
grant execute on function public.backend_get_gateway_order_for_payment_transaction(uuid, uuid) to service_role;

revoke execute on function public.backend_release_expired_reservations_v2(integer) from public, anon, authenticated;
grant execute on function public.backend_release_expired_reservations_v2(integer) to service_role;

-- 3c. Public trigger functions: no application role may call them
-- directly. Trigger invocation itself does not check EXECUTE, so
-- all triggers keep firing (proven by the Test 8 tests).

revoke execute on function public.w7_enqueue_order_notifications() from public, anon, authenticated, service_role;
revoke execute on function public.w7_enqueue_merchant_notifications() from public, anon, authenticated, service_role;
revoke execute on function public.w7_enqueue_store_notifications() from public, anon, authenticated, service_role;
revoke execute on function public.set_updated_at() from public, anon, authenticated, service_role;

-- --- 4. Future functions: NO default-privileges clause, on purpose.
-- See the header note: ALTER DEFAULT PRIVILEGES cannot remove the
-- built-in PUBLIC EXECUTE grant in PostgreSQL 17 (proven on the
-- disposable cluster). Future migrations must revoke explicitly. ---
