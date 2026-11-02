# W9.1.1: Post-Merge Checkout and Database Concurrency Corrections

Branch: `fix/w9-1-1-checkout-lock-order` (from main `698f8308`).
PR only — do NOT merge, deploy, or apply migrations from this branch
without the project owner's explicit approval.

## Fix A — Countdown expiry must preserve active checkout state

Root cause (`apps/web/app/customer/checkout/page.tsx`,
`handleExpire` as merged in W9.1): the countdown handler
removed `ACTIVE_RESERVATION_KEY` from sessionStorage
BEFORE the backend order re-read ran, and then set phase
`"expired"` unconditionally — even when the backend said
the order was still `pending_payment` (early client
countdown, skewed clock) and even when the re-read
failed (unhandled rejection, no retry). A still-payable
customer lost the in-page recovery path; a failed re-read
left no way to retry the state refresh.

Fix (same file, plus `apps/web/lib/idempotency.ts`):

- `handleExpire` now touches nothing stored until the
  backend re-read resolves, and handles all four outcomes:
  - `pending_payment` → preserve reference AND key, stay
    in `reserved` with the Pay button, show a notice that
    the timer ran early. No second reservation is created.
  - Known terminal status → remove reference AND key,
    phase `expired` for `expired`, `not-payable` otherwise.
  - Unrecognized status → fail closed: preserve reference
    AND key, phase `not-payable` (no Pay button), no clear.
  - Re-read failure → preserve reference AND key, show a
    recoverable error, and show a "Retry status check"
    button that re-runs the re-read.
- New helper `isKnownTerminalOrderStatus` (only the seven
  known terminal statuses) is now the ONLY predicate that
  may authorize clearing a reference or key, at every
  clearing site in the page (stored-reference recovery,
  live-cart recovery, create-replay defense, verify
  handler, countdown expiry). `isTerminalOrderStatus`
  keeps its W9.1 display semantics (unknown shows as
  not-payable) and is unchanged — the W9.1 test that pins
  it still passes.
- The countdown stays hidden after an outcome is recorded
  (re-mounting it on a past expiry would re-fire the
  re-read in a loop). A later genuine expiry is then
  caught by the backend at Pay time and on refresh, both
  of which re-read the authoritative order state.

Tests: `apps/web/tests/checkout-countdown-expiry.test.tsx`
(9 tests: helper split, still-payable, read failure +
retry recovery, expired clear, confirmed clear, unknown
fail-closed, key stability). The mocked Playwright
checkout journey is unchanged (it covers the happy path;
the expiry branches are covered at component level with
mocked services, so the shared stub was not modified).

Known wart left alone (out of scope, noted): the entry
effect's `catch` blocks still drop `ACTIVE_RESERVATION_KEY`
on a failed initial refresh. The reservation KEY survives,
so a same-cart retry replays instead of duplicating, but
the no-cart refresh path loses its in-page recovery until
the customer re-enters from the order page.

## Fix B — SQL lock ordering

Root cause (`supabase/migrations/20261101200000_w91_reservation_expiry.sql`,
verified from the function bodies, not the comments):
`confirm_payment_capture` locks payment transaction ->
order -> reservations -> listings, while the W9.1 v2
cleanup locked reservations -> listings -> order. That
inversion breaks in two ways:

1. Deadlock: cleanup holds a reservation and waits on
   the order held by confirm; confirm holds the order
   and waits on the reservation. The v2 cursor's
   SKIP LOCKED only helps when confirm locked the
   reservation first.
2. False confirmation (worse): confirm passes its live
   check (a plain snapshot read, not blocked by v2's
   locks), marks the transaction captured, then blocks
   on the reservation loop. Cleanup commits first
   (stock released, order `expired`). Confirm's loop
   then skips the now-expired rows via EvalPlanQual and
   still sets the order `confirmed` with payment
   `captured` — money captured for stock that was
   released and never consumed. The W9.1 comment's
   "interleavings converge" claim is false for this
   interleaving.

Fix (new forward-only migration
`supabase/migrations/20261102210000_w911_cleanup_lock_order.sql`,
UNAPPLIED): `private.release_expired_reservations_v2`
is replaced with an order-first body. Lock order is now
order -> reservations -> listings, the same relative
order confirm uses. Orders are claimed in id order with
FOR UPDATE SKIP LOCKED (SKIP LOCKED is required: plain
FOR UPDATE would let two workers deadlock on
(order, listing) pairs). A mid-flight confirm holds its
order lock, so the pass skips that order; a later
confirm blocks on the order lock, then sees expired
reservations and routes to reconciliation. Signature,
result shape, tier rules, batch bound (at most `p_limit`
reservations, with an explicit loop exit), event reasons,
and service-role-only entry grants are all preserved;
the public wrapper is NOT redefined. One v2 wart is also
fixed: the order-status event and counter now fire only
when the expiry UPDATE actually changed a row
(`GET DIAGNOSTICS ROW_COUNT`).

No worker change: `backend/app/reservation_cleanup.py`
keeps calling the same RPC with the same signature.
Deadlock retry posture is unchanged and correct:
the function is a single transaction (abort rolls
everything back — no partial release, no false
confirmation), the worker retries on the next pass,
and a failed confirm is retried by Razorpay redelivery
(the webhook records the event first, then confirms,
and confirm is idempotent).

## Verification status (honest)

- Real PostgreSQL concurrency testing: NOT RUN. This
  environment has no Postgres binaries and no
  Docker/Podman, and live Supabase was not touched.
  What was verified instead: lock acquisition traced
  from the actual function bodies (confirm, checkout,
  mark-failed, v2 cleanup), the wait-cycle and
  false-confirmation interleavings reasoned from those
  bodies, and the new migration parsed + consistency-
  checked with pglast. What remains unverified until a
  staging database exists: live execution of the new
  function, the two-session deadlock interleaving, and
  duplicate-release behaviour under real concurrency.
- Residual risk: listings are updated in reservation
  order while confirm updates them in its own
  (unspecified) reservation order, so two transactions
  touching the same listings in opposite orders can
  still deadlock on listings alone. Consequence is
  bounded (atomic rollback + retry, as above), and
  running a single cleanup worker instance removes the
  worker-worker case. Eliminating it entirely would
  require changing `confirm_payment_capture`, which is
  out of scope here.
- Typecheck: `apps/web` `tsc --noEmit` passes.
  `packages/api-client` `tsc --noEmit` reports 2 errors
  in `tests/checkout-services.test.ts` — pre-existing on
  main (that package is untouched by this branch).
- GitHub Actions: not verified in this run (account was
  previously billing-locked; do not treat CI as green
  until a run is observed on the PR).

## Test counts (exact, this branch)

- Backend pytest: 408 passed (W9.1 baseline 398 + 10
  new W9.1.1 migration tests).
- Web vitest: 91 passed (W9.1 baseline 82 + 9 new
  countdown-expiry tests).
- api-client vitest: 23 passed (unchanged).
- Playwright: see the PR report (mocked suite).

## What this PR does NOT do

No live Supabase change, no migration applied, no
deployment, no merge, no W9.2, no migration-history
repair, no worker deployment, no new features. The
W9.1 migration file is untouched; the new migration
stays unapplied pending owner approval.
