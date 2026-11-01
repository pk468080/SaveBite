-- SaveBite B1 — server-only lookup for Razorpay checkout retry recovery.
--
-- PROBLEM (W8 blocker B1): begin_payment_checkout reuses a payment
-- transaction by idempotency key but returns no gateway order id.
-- Checkout therefore always created a new Razorpay order, and
-- backend_attach_gateway_order rejected the second order with
-- gateway_order_id_conflict (22023 -> HTTP 422) whenever the
-- first order had already been attached — a lost checkout
-- response, or a modal dismissed and retried with the same
-- idempotency key. The customer was never charged by the
-- orphaned order (it stays unpaid), but the original gateway
-- order id could not be recovered.
--
-- This migration adds ONE narrow lookup, used by the checkout
-- router BEFORE it creates a Razorpay order:
--   public.backend_get_gateway_order_for_payment_transaction(
--     p_payment_transaction_id uuid, p_order_id uuid) returns jsonb
-- It returns exactly five fields — payment_transaction_id,
-- order_id, gateway, gateway_order_id (null when nothing is
-- attached yet), and status — and nothing else: no payment
-- ids, signatures, webhook payloads, or unrelated private
-- columns. The row must match BOTH the transaction id and
-- the order id and be a razorpay transaction; anything else
-- raises payment_transaction_not_found (P0002), so a caller
-- cannot probe another order's transactions.
--
-- SECURITY: the private implementation is SECURITY DEFINER
-- (it must read private.payment_transactions, which no
-- PostgREST role can read directly) and the public wrapper
-- is plain SQL delegating to it, following the established
-- backend_* pattern from the baseline. Both pin an empty
-- search_path and use fully qualified names. EXECUTE on the
-- public function is revoked from PUBLIC, anon, and
-- authenticated, and granted only to service_role. The
-- application allowlist (backend/app/supabase_client.py)
-- additionally restricts this RPC to the service-role
-- client; the user-context client rejects any backend_*
-- name before any HTTP call.
--
-- APPLY-TIME VERIFICATION (mandatory, before checkout
-- retries are relied on): run has_function_privilege for
-- anon, authenticated, and service_role on this function
-- and confirm only service_role holds EXECUTE. Apply in
-- timestamp order after the W7 and W8 files. The W7/W8
-- files themselves are still pending their own approved
-- process; this file does not apply them.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply
-- through the normal migration process; this file only
-- records the change.

create or replace function private.get_gateway_order_for_payment_transaction(
  p_payment_transaction_id uuid,
  p_order_id uuid
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_payment private.payment_transactions%rowtype;
begin
  select * into v_payment
    from private.payment_transactions
   where id = p_payment_transaction_id
     and order_id = p_order_id
     and gateway = 'razorpay';
  if not found then
    raise exception 'payment_transaction_not_found' using errcode = 'P0002';
  end if;
  return jsonb_build_object(
    'payment_transaction_id', v_payment.id,
    'order_id', v_payment.order_id,
    'gateway', v_payment.gateway,
    'gateway_order_id', v_payment.gateway_order_id,
    'status', v_payment.status
  );
end;
$function$;

create or replace function public.backend_get_gateway_order_for_payment_transaction(
  p_payment_transaction_id uuid,
  p_order_id uuid
)
returns jsonb
language sql
set search_path = ''
as $function$
  select private.get_gateway_order_for_payment_transaction($1, $2);
$function$;

revoke execute on function public.backend_get_gateway_order_for_payment_transaction(uuid, uuid) from public;
revoke execute on function public.backend_get_gateway_order_for_payment_transaction(uuid, uuid) from anon;
revoke execute on function public.backend_get_gateway_order_for_payment_transaction(uuid, uuid) from authenticated;
grant execute on function public.backend_get_gateway_order_for_payment_transaction(uuid, uuid) to service_role;
