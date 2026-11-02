-- SaveBite W9.1.1 — correct the v2 cleanup lock order
-- (Issue: lock-order inversion with payment confirmation).
--
-- ROOT CAUSE (verified from the function bodies, not
-- from the W9.1 comments — the W9.1 comment's claim
-- that "interleavings with confirm converge" is FALSE
-- for one interleaving, see below):
--
-- confirm_payment_capture (baseline) locks, in order:
--   payment transaction -> order -> reservations ->
--   listings.
-- The W9.1 v2 cleanup locked, in order:
--   reservations (cursor, FOR UPDATE SKIP LOCKED) ->
--   listings -> order.
-- That is a full inversion on the (order,
-- reservation) pair, so two interleavings break:
--
-- 1. DEADLOCK. Cleanup locks reservation R, then waits
--    on order O held by confirm; confirm holds O, then
--    waits on R. Postgres aborts one transaction with
--    deadlock_detected. The W9.1 cursor's SKIP LOCKED
--    only helps when confirm locked R BEFORE the cursor
--    ran; it does nothing for the reverse order.
--
-- 2. FALSE CONFIRMATION (worse). Confirm locks the
--    payment transaction and the order, passes its
--    live-reservation count check (a plain snapshot
--    read — v2's reservation locks do not block it),
--    marks the transaction captured, then blocks on the
--    reservation loop's FOR UPDATE. Cleanup commits
--    first: stock released, order set to 'expired'.
--    Confirm's loop then resumes, but EvalPlanQual
--    re-checks each waited row against status='active'
--    and skips the now-expired rows — the loop runs
--    ZERO times, and confirm still sets the order to
--    'confirmed' with payment 'captured'. Result: money
--    captured for an order whose stock was released and
--    never consumed. The order lock is what makes
--    confirm's live check atomic with cleanup: with the
--    order locked first, confirm either runs fully
--    before cleanup (cleanup then skips: order no
--    longer pending_payment, reservations consumed) or
--    fully after it (confirm's live check sees expired
--    reservations and routes to reconciliation).
--
-- THE FIX (this file, and nothing else):
-- private.release_expired_reservations_v2 is replaced
-- with an order-first body. The lock order becomes:
--   order -> reservations -> listings,
-- the same relative order confirm uses (cleanup has no
-- payment-transaction step). Orders are claimed in id
-- order with FOR UPDATE SKIP LOCKED — SKIP LOCKED is
-- REQUIRED, not incidental: a plain FOR UPDATE here
-- would let two workers deadlock on (order, listing)
-- pairs. A confirm mid-flight on an order holds that
-- order's lock, so this pass skips the whole order
-- instead of waiting; a confirm arriving later blocks
-- on the order lock until this pass commits, then sees
-- expired reservations and reconciles. No wait cycle
-- can form on (order, reservation) or (order, listing)
-- between the two operations.
--
-- WHAT IS PRESERVED EXACTLY (v2 semantics):
-- - Same function name and signature, same jsonb
--   result shape {released, orders_expired,
--   orders_preserved_reconciliation}.
-- - Same tier rules: HARD BLOCK on 'authorized',
--   'captured', 'refunded', 'partially_refunded'
--   (re-checked per order, not just at claim time);
--   RELEASE + PRESERVE for 'reconciliation_required'
--   (order row untouched, finance flag kept);
--   RELEASE + EXPIRE for no transaction or only
--   'created'/'failed' transactions.
-- - Same bounded batch: at most p_limit reservations
--   released per call (p_limit clamped 1-1000, same
--   exception). The candidate snapshot keeps v2's
--   oldest-first order (expires_at) and limit; the
--   loop additionally exits once the budget is spent,
--   because one order may hold more reservations than
--   its candidate rows. Repeated calls pick up the
--   remainder; released rows are never 'active', so
--   they are never processed twice.
-- - Same event reasons and order-status event.
-- - Same worker: backend/app/reservation_cleanup.py
--   keeps calling backend_release_expired_reservations_v2
--   unchanged; the public wrapper below is NOT
--   redefined, only its entry-point grants are
--   re-asserted (service-role-only, B1/W7 pattern).
--
-- WHAT IS ALSO CORRECTED (v2 wart, same file):
-- v2 inserted the order_status_events row and counted
-- the order as expired even when its guarded order
-- UPDATE touched zero rows (possible in v2 precisely
-- because v2 held no order lock). The expiry event
-- and counter now fire only when the UPDATE actually
-- changed a row (GET DIAGNOSTICS ROW_COUNT).
--
-- RESIDUAL RISK (documented, not fixed here):
-- Listings are updated in reservation order, while
-- confirm updates them in its own (unspecified)
-- reservation order, so two transactions touching the
-- SAME listings in opposite orders can still deadlock
-- on listings alone. That deadlock aborts one whole
-- transaction (atomic rollback: no partial release,
-- no false confirmation) and is recovered by retry —
-- the cleanup worker retries on the next pass, and a
-- failed confirm is retried by Razorpay redelivery
-- (the webhook records the event first, then confirms,
-- and confirm is idempotent). Eliminating it entirely
-- would require changing confirm_payment_capture's
-- loop order, which is out of scope for this fix and
-- riskier than the inversion it would remove.
-- Running a single cleanup worker instance removes
-- even the worker-worker listing contention.
--
-- PREREQUISITES: the W9.1 migration
-- 20261101200000_w91_reservation_expiry.sql must be
-- applied first (it creates the v2 functions and the
-- public wrapper). Apply in timestamp order.
--
-- POSTCONDITIONS (verify at apply time):
-- - private.release_expired_reservations_v2 has the
--   signature below; the public wrapper signature is
--   unchanged (this file does not redefine it).
-- - has_function_privilege shows EXECUTE only for
--   service_role (and the owner) on the public
--   function; anon and authenticated must NOT hold it.
-- - No existing table, policy, or other function is
--   modified by this file.
--
-- NOT APPLIED TO LIVE by this PR. Review and apply
-- through the normal migration process; this file only
-- records the change.

create or replace function private.release_expired_reservations_v2(p_limit integer default 100)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
  v_order record;
  v_reservation record;
  v_released integer := 0;
  v_orders_expired integer := 0;
  v_orders_preserved integer := 0;
  v_has_reconciliation boolean;
  v_updated integer;
begin
  if p_limit < 1 or p_limit > 1000 then raise exception 'invalid_batch_limit' using errcode = '22023'; end if;

  <<claim_loop>>
  for v_order in
    select o.id
    from public.orders o
    where o.id in (
      select r.order_id
      from public.inventory_reservations r
      where r.status = 'active'
        and r.expires_at <= now()
      order by r.expires_at
      limit p_limit
    )
    and o.status = 'pending_payment'
    and not exists (
      select 1 from private.payment_transactions p
      where p.order_id = o.id
        and p.status in ('authorized', 'captured', 'refunded', 'partially_refunded')
    )
    order by o.id
    for update of o skip locked
  loop
    -- The order lock is held, so no confirm can be
    -- mid-flight on this order's reservations (confirm
    -- locks the order before its reservations). Re-check
    -- the protected-transaction exclusion anyway: a
    -- transaction may have become protected between the
    -- claim snapshot and this loop.
    if exists (
      select 1 from private.payment_transactions p
      where p.order_id = v_order.id
        and p.status in ('authorized', 'captured', 'refunded', 'partially_refunded')
    ) then
      continue;
    end if;

    select exists (
      select 1 from private.payment_transactions p
      where p.order_id = v_order.id and p.status = 'reconciliation_required'
    ) into v_has_reconciliation;

    for v_reservation in
      select r.id, r.listing_id, r.quantity
      from public.inventory_reservations r
      where r.order_id = v_order.id
        and r.status = 'active'
        and r.expires_at <= now()
      order by r.expires_at
      for update of r skip locked
    loop
      -- Bounded batch: one order may hold more expired
      -- reservations than its candidate rows, so stop
      -- at the budget instead of releasing past it.
      if v_released >= p_limit then
        exit claim_loop;
      end if;

      update public.listings set reserved_quantity = reserved_quantity - v_reservation.quantity
      where id = v_reservation.listing_id;
      update public.inventory_reservations set status = 'expired', released_at = now()
      where id = v_reservation.id;

      insert into public.inventory_events(
        listing_id, order_id, reservation_id, event_type, quantity_delta, actor_user_id, reason
      ) values (
        v_reservation.listing_id, v_order.id, v_reservation.id,
        'reservation_released', v_reservation.quantity, null,
        case when v_has_reconciliation
          then 'reservation_expired_reconciliation_pending'
          else 'reservation_expired_after_payment_failure_or_no_payment' end
      );

      v_released := v_released + 1;
    end loop;

    if not exists (
      select 1 from public.inventory_reservations r
      where r.order_id = v_order.id and r.status = 'active'
    ) then
      if v_has_reconciliation then
        -- Stock freed, order row preserved: finance must
        -- still see payment_status reconciliation_required.
        v_orders_preserved := v_orders_preserved + 1;
      else
        update public.orders set status = 'expired', payment_status = 'failed'
        where id = v_order.id and status = 'pending_payment';
        get diagnostics v_updated = row_count;
        -- W9.1.1: only log and count the expiry when the
        -- update actually changed a row. (With the order
        -- lock held this cannot be zero, but the guard
        -- keeps the function correct in any context.)
        if v_updated > 0 then
          insert into public.order_status_events(order_id, from_status, to_status, actor_type, reason)
          values (v_order.id, 'pending_payment', 'expired', 'system', 'reservation_expired');
          v_orders_expired := v_orders_expired + 1;
        end if;
      end if;
    end if;
  end loop;
  return jsonb_build_object(
    'released', v_released,
    'orders_expired', v_orders_expired,
    'orders_preserved_reconciliation', v_orders_preserved
  );
end;
$function$;

revoke execute on function public.backend_release_expired_reservations_v2(integer) from public;
revoke execute on function public.backend_release_expired_reservations_v2(integer) from anon;
revoke execute on function public.backend_release_expired_reservations_v2(integer) from authenticated;
grant execute on function public.backend_release_expired_reservations_v2(integer) to service_role;
