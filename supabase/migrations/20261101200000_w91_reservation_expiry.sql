-- SaveBite W9.1 — safe, bounded, idempotent release of expired
-- inventory reservations (Issue 2).
--
-- PROBLEM: the existing cleanup
-- (private.release_expired_inventory_reservations, exposed as
-- public.backend_release_expired_reservations) skips every
-- order that has a payment transaction in status 'created',
-- 'authorized', 'captured', or 'reconciliation_required'.
-- begin_payment_checkout creates a transaction in status
-- 'created' as soon as checkout starts, and an abandoned
-- checkout (dismissed Razorpay window, no webhook) never
-- moves that transaction out of 'created'. Nothing calls
-- the existing cleanup, and even if it ran, the 'created'
-- exclusion would leave the stock reserved forever: the
-- order stays pending_payment and the listings stay
-- reserved, permanently blocking inventory.
--
-- WHY NOT SIMPLY REMOVE 'created' FROM THE EXCLUSION:
-- the exclusion exists because a 'created' transaction
-- might still become a payment: the customer may be
-- mid-checkout, or a webhook may be delayed. Removing the
-- state from the exclusion without tracing the payment
-- lifecycle would risk releasing stock under a live
-- payment. The trace below is what makes the new
-- function safe, and it is the reason the new function
-- keeps most of the exclusion intact.
--
-- LIFECYCLE TRACE (baseline functions, verified):
-- - Reservations live ~5 minutes (create_order_reservation
--   sets expires_at = now() + 5 minutes; listings carry
--   reserved_quantity until release or consumption).
-- - begin_payment_checkout refuses an order unless ALL of
--   its reservations are live (status 'active' AND
--   expires_at > now()). A new checkout can therefore
--   never start on expired reservations.
-- - confirm_payment_capture refuses to confirm unless the
--   order is still pending_payment AND all reservations
--   are still live. A capture that arrives after expiry
--   (late webhook, dismissed-then-paid modal) is routed
--   to status 'reconciliation_required' with failure
--   RESERVATION_NOT_ACTIVE_OR_INCOMPLETE, gateway id
--   recorded — never silently confirmed, never silently
--   discarded, never oversold. The 5-minute TTL is the
--   grace period: cleanup only ever selects reservations
--   with expires_at <= now(), so it can never take stock
--   from a payment that could still confirm.
-- - mark_payment_failed refuses a captured payment, so a
--   late failure event can never overwrite a capture.
-- - Webhook events are recorded once per gateway event
--   id, so redelivery cannot double-confirm or
--   double-fail.
-- Consequence: once a reservation is time-expired, the
-- order can never confirm through any path. Releasing
-- its stock cannot change a would-be confirmation into
-- a loss — the webhook outcome is reconciliation either
-- way. What cleanup changes is stock availability and
-- order hygiene, not money.
--
-- TIER RULES (what the new function does per order):
-- - HARD BLOCK — never touched: any transaction in
--   'authorized' (money held at the provider),
--   'captured' (money confirmed), 'refunded', or
--   'partially_refunded' (money already moved). These
--   orders are skipped entirely; a human must look at
--   them. Note: no backend code ever writes
--   'authorized' today (it exists only as a schema
--   value); blocking it is conservative, not a
--   behaviour change.
-- - RELEASE + PRESERVE — transaction in
--   'reconciliation_required': the stock is freed
--   (the order can never confirm), but the order row
--   is left untouched, so payment_status stays
--   'reconciliation_required' for finance. The audit
--   event reason is
--   'reservation_expired_reconciliation_pending',
--   distinct from the normal release reason.
-- - RELEASE + EXPIRE — no transaction, or only
--   transactions in 'created' or 'failed': the stock
--   is freed, and once no active reservation remains
--   the order moves to 'expired' with payment_status
--   'failed' (the existing v1 behaviour). A late
--   webhook after this still lands in
--   'reconciliation_required' via confirm_payment_
--   capture, because confirm re-checks order status
--   and live reservations after acquiring its locks.
--
-- CONCURRENCY AND IDEMPOTENCY:
-- - One bounded batch per call (p_limit, default 100,
--   clamped 1-1000, same as v1). Repeated calls pick
--   up the remainder; already-expired rows are never
--   'active', so they are never processed twice, and
--   reserved_quantity is decremented exactly once per
--   reservation.
-- - Rows are claimed with FOR UPDATE ... SKIP LOCKED,
--   so concurrent workers claim disjoint sets.
-- - Interleavings with confirm converge: if confirm
--   holds the order/tx locks, cleanup's order update
--   waits and then no-ops (status no longer
--   pending_payment); if cleanup commits first,
--   confirm sees 'expired' or non-live reservations
--   and routes to reconciliation; if confirm is
--   mid-flight on still-live reservations, cleanup
--   skips its locked rows. No interleaving silently
--   confirms, oversells, or loses a payment.
--
-- WHAT THIS FILE ADDS (and does not change):
-- - private.release_expired_reservations_v2(p_limit)
--   returns jsonb {released, orders_expired,
--   orders_preserved_reconciliation}.
-- - public.backend_release_expired_reservations_v2,
--   plain SQL delegating to it (baseline backend_*
--   pattern). The v1 functions are left intact for
--   backward compatibility; the new worker operation
--   (backend/app/reservation_cleanup.py) calls v2.
-- - EXECUTE revoked from PUBLIC, anon, and
--   authenticated, granted only to service_role
--   (B1 pattern — the W7 default-privilege gap must
--   not recur). The application allowlist
--   (backend/app/supabase_client.py) additionally
--   restricts this RPC to the service-role client.
--
-- PREREQUISITES: baseline tables only
-- (inventory_reservations, orders, listings,
-- inventory_events, order_status_events,
-- private.payment_transactions). No W7/W8/B1 object
-- is required. Apply in timestamp order after
-- 20261101190000.
--
-- POSTCONDITIONS (verify at apply time):
-- - Both functions exist with the signatures below.
-- - has_function_privilege shows EXECUTE only for
--   service_role (and the owner) on the public
--   function; anon and authenticated must NOT hold it.
-- - No existing function, table, policy, or row is
--   modified by this file.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply
-- through the normal migration process; this file only
-- records the change. The live migration-history drift
-- (history table holds only the original 15 records)
-- is NOT repaired by this file.

create or replace function private.release_expired_reservations_v2(p_limit integer default 100)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_reservation record;
  v_released integer := 0;
  v_orders_expired integer := 0;
  v_orders_preserved integer := 0;
  v_has_reconciliation boolean;
begin
  if p_limit < 1 or p_limit > 1000 then raise exception 'invalid_batch_limit' using errcode = '22023'; end if;

  for v_reservation in
    select r.id, r.order_id, r.listing_id, r.quantity
    from public.inventory_reservations r
    join public.orders o on o.id = r.order_id
    where r.status = 'active'
      and r.expires_at <= now()
      and o.status = 'pending_payment'
      and not exists (
        select 1 from private.payment_transactions p
        where p.order_id = o.id
          and p.status in ('authorized', 'captured', 'refunded', 'partially_refunded')
      )
    order by r.expires_at
    for update of r skip locked
    limit p_limit
  loop
    update public.listings set reserved_quantity = reserved_quantity - v_reservation.quantity
    where id = v_reservation.listing_id;
    update public.inventory_reservations set status = 'expired', released_at = now()
    where id = v_reservation.id;

    select exists (
      select 1 from private.payment_transactions p
      where p.order_id = v_reservation.order_id and p.status = 'reconciliation_required'
    ) into v_has_reconciliation;

    insert into public.inventory_events(
      listing_id, order_id, reservation_id, event_type, quantity_delta, actor_user_id, reason
    ) values (
      v_reservation.listing_id, v_reservation.order_id, v_reservation.id,
      'reservation_released', v_reservation.quantity, null,
      case when v_has_reconciliation
        then 'reservation_expired_reconciliation_pending'
        else 'reservation_expired_after_payment_failure_or_no_payment' end
    );

    if not exists (
      select 1 from public.inventory_reservations r
      where r.order_id = v_reservation.order_id and r.status = 'active'
    ) then
      if v_has_reconciliation then
        -- Stock freed, order row preserved: finance must
        -- still see payment_status reconciliation_required.
        v_orders_preserved := v_orders_preserved + 1;
      else
        update public.orders set status = 'expired', payment_status = 'failed'
        where id = v_reservation.order_id and status = 'pending_payment';
        insert into public.order_status_events(order_id, from_status, to_status, actor_type, reason)
        values (v_reservation.order_id, 'pending_payment', 'expired', 'system', 'reservation_expired');
        v_orders_expired := v_orders_expired + 1;
      end if;
    end if;
    v_released := v_released + 1;
  end loop;
  return jsonb_build_object(
    'released', v_released,
    'orders_expired', v_orders_expired,
    'orders_preserved_reconciliation', v_orders_preserved
  );
end;
$function$;

create or replace function public.backend_release_expired_reservations_v2(p_limit integer default 100)
returns jsonb
language sql
set search_path = ''
as $function$
  select private.release_expired_reservations_v2($1);
$function$;

revoke execute on function public.backend_release_expired_reservations_v2(integer) from public;
revoke execute on function public.backend_release_expired_reservations_v2(integer) from anon;
revoke execute on function public.backend_release_expired_reservations_v2(integer) from authenticated;
grant execute on function public.backend_release_expired_reservations_v2(integer) to service_role;
