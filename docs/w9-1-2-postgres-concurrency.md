# SaveBite W9.1.2 — PostgreSQL Concurrency Validation

Status: **complete — merged as PR #27 (main `12517546`).** All 15
concurrency tests passed on real PostgreSQL 16.15 and the full backend
suite was 423 passed at merge; nothing in the recorded test counts or
results below has been altered. What this document does NOT cover (live
PostgreSQL 17 execution, the webhook HTTP layer, real Razorpay provider
calls) is now tracked by W9.1.3 (`docs/w9-1-3-staging-validation.md`).

This document records a genuine PostgreSQL concurrency validation of the
W9.1 (`20261101200000`) and W9.1.1 (`20261102210000`) reservation-expiry
migrations. It is a reliability report, not a feature change: no merged
migration is modified by this task, and neither W9.1 nor W9.1.1 is
applied to production by it.

## 1. Stage A — dependency and bootstrap report (read before running)

### What was verified from the actual code (not from comments)

- **Payment confirmation lock order** (`private.confirm_payment_capture`,
  baseline): payment transaction `FOR UPDATE` → order `FOR UPDATE` →
  snapshot live-reservation count (a plain read, *not* locked) →
  transaction marked `captured` → reservation loop `FOR UPDATE` →
  listings (`reserved_quantity - qty`, `sold_quantity + qty`) →
  reservations to `consumed` → `sold` events → order `confirmed`.
  The live-count check is a snapshot read: it is *not* blocked by
  another transaction's reservation locks. That is exactly the
  false-confirmation mechanism W9.1.1 describes.
- **W9.1 cleanup lock order** (`private.release_expired_reservations_v2`
  as merged in W9.1): reservations `FOR UPDATE SKIP LOCKED` →
  listings → order (via the guarded `UPDATE ... WHERE status =
  'pending_payment'`, which takes the order lock late). Full inversion
  against confirmation on the (order, reservation) pair.
- **W9.1.1 cleanup lock order** (replacement body): orders claimed in
  id order with `FOR UPDATE SKIP LOCKED` → reservations `FOR UPDATE
  SKIP LOCKED` in `expires_at` order → listings. Same relative order
  as confirmation (cleanup has no payment-transaction step).
- **W9.1 comment correction**: the W9.1 header claim that
  "interleavings with confirm converge" is false for the
  confirm-mid-flight interleaving (confirm passes its snapshot live
  check, cleanup commits first, confirm's loop then skips the
  now-expired rows via EvalPlanQual and still confirms). W9.1.1's
  order-first lock is what closes it: with the order locked first,
  confirm either runs fully before cleanup or fully after it.
- **W9.1.1 wart fix**: W9.1 inserted the order-expiry event and
  counted the order as expired even when its guarded order `UPDATE`
  matched zero rows. W9.1.1 fires the event/counter only when
  `GET DIAGNOSTICS ROW_COUNT > 0`.
- **Idempotency**: confirm returns the order id with no side effects
  when the transaction is already `captured`; a captured payment can
  never be overwritten by `mark_payment_failed` (it raises). The
  webhook records the event first (`backend_record_payment_webhook_event`,
  unique per gateway event id), then confirms or fails; a confirm
  failure raises, so Razorpay redelivery re-runs the idempotent
  confirm. The webhook layer itself is backend code and is *not*
  executed by these database tests — only confirm's idempotency is.
- **Worker** (`backend/app/reservation_cleanup.py`): a thin driver
  calling `backend_release_expired_reservations_v2` once per pass with
  a bounded `p_limit` (default 100, clamped 1–1000 server-side). It
  holds no queue state and never touches payments. Concurrent workers
  claim disjoint work via `SKIP LOCKED`.
- **No hidden trigger behaviour**: the only triggers on the tested
  tables are `set_updated_at` (listings) and ledger immutability
  triggers (unrelated tables). Inventory counters are maintained by
  function code, not triggers.
- **Constraints that back the invariants**: `listings.reserved_quantity
  >= 0`, `listings.sold_quantity >= 0`, `reserved + sold <= total`,
  `inventory_reservations.quantity > 0`, one active reservation per
  order item (partial unique index), `available_quantity` generated
  as `total - reserved - sold`. A double release that drove reserved
  negative would violate a CHECK and abort the transaction.

### Why the baseline cannot be replayed verbatim

The consolidated baseline (`20261031060000_remote_schema_baseline.sql`)
is a *tracking copy*, not one of the 15 original live migrations
(see `supabase/migrations/README.md`). Three defects block a verbatim
replay in a vanilla PostgreSQL database, and the bootstrap script
(`backend/tests/pg_bootstrap.py`) handles each explicitly — the
repository file itself is never edited:

1. **Missing `auth` schema.** Four foreign keys reference
   `auth.users(id)` (`orders.customer_id`, `audit_logs.actor_user_id`,
   `commission_rules.created_by`, `idempotency_records.actor_user_id`,
   `notification_outbox.user_id`). The script pre-creates a minimal
   `auth.users (id uuid primary key)` table. Functions calling
   `auth.uid()` (for example `begin_payment_checkout`) are created
   but never executed by these tests, and would fail loudly if called.
2. **Corrupted policy statements.** All 41 `CREATE POLICY` statements
   carry an introspection artifact in the role list
   (`to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, }`),
   which is not valid PostgreSQL. The script strips exactly those 41
   statements (and refuses to run if the count differs). The tested
   functions are `SECURITY DEFINER` and run as the table owner, so
   row-level policies cannot change their behaviour; policy
   correctness lives in the original 15 live migrations and is out of
   scope here.
3. **PostGIS types.** Two columns use the `geography` type
   (`stores.location`, `platform_service_areas.boundary`). The script
   requires the PostGIS extension and fails clearly if it is missing,
   rather than silently building a reduced schema.

Additionally, the W9.1/W9.1.1 migrations issue `REVOKE`/`GRANT`
against `anon`, `authenticated` and `service_role`, so those roles are
pre-created (`NOLOGIN`) before the migrations run.

### Valid bootstrap sequence (reproducible)

1. Start a disposable PostgreSQL server (own `initdb` cluster, socket
   only, local trust auth) or point at an existing server.
2. `(Re)create` the target database (this script drops it — never
   point it at a shared or production database).
3. Pre-steps: `auth` schema + `auth.users`, roles
   (`anon`/`authenticated`/`service_role`), extensions
   (`pgcrypto`, `postgis`).
4. Apply the baseline with the 41 policy statements stripped.
5. Apply W9.1 (`20261101200000`), then W9.1.1 (`20261102210000`), in
   timestamp order.
6. Verify: both v2 functions exist with the expected signatures, the
   public wrapper resolves to the private function, `anon` and
   `authenticated` lack `EXECUTE` on the worker RPC while
   `service_role` holds it, and the required tables/constraints exist.

Commands:

```sh
# Disposable server (default paths; needs initdb + a non-root OS user):
python3 backend/tests/pg_bootstrap.py \
    --pgdata /tmp/savebite-pgtest/data \
    --socket-dir /tmp/savebite-pgtest/sock --port 54399

# Existing server instead:
python3 backend/tests/pg_bootstrap.py --existing-dsn \
    "host=127.0.0.1 port=5432 dbname=savebite_pgtest user=pgtest"

# Teardown when done:
python3 backend/tests/pg_bootstrap.py --teardown \
    --pgdata /tmp/savebite-pgtest/data --socket-dir /tmp/savebite-pgtest/sock
```

## 2. Test execution

```sh
# Install the test driver (not a repo dependency change):
pip install "psycopg[binary]"

# Run only the concurrency module (needs a bootstrapped database):
SAVEBITE_PG_TEST_DSN="host=/tmp/savebite-pgtest/sock port=54399 \
    dbname=savebite_pgtest user=pgtest" \
    python -m pytest backend/tests/test_pg_concurrency.py -v

# Run the full backend suite (W9.1.1 baseline: 408 passed):
cd backend && python -m pytest -q
```

FAIL-CLEARLY RULE: if psycopg is missing, if the database is
unreachable, or if it was not bootstrapped, the concurrency module
fails loudly. It never substitutes a mock, a fake, or SQLite. To run
the rest of the suite without PostgreSQL, exclude the file explicitly
(`pytest --ignore=backend/tests/test_pg_concurrency.py`); that is a
deliberate exclusion, not a pass.

## 3. Concurrency scenarios

Deterministic coordination uses a test-only trigger (installed in the
disposable database only, never in a migration) that pauses a session
mid-function on an advisory lock held by the test driver, while the
driver observes the waiting backend in `pg_stat_activity` / `pg_locks`.
No test depends on `sleep` timing to create a race.

- **Test 1 — cleanup first.** Cleanup pauses after acquiring the
  order lock; confirmation is observed blocked on the order lock;
  cleanup commits (stock released, order expired); confirmation then
  routes to `reconciliation_required`, never to `confirmed`. A second
  confirm is a no-op.
- **Test 2 — confirmation first.** Confirmation pauses holding the
  order lock; cleanup returns zero work without blocking (SKIP
  LOCKED); confirmation commits (reservations consumed, counters
  correct); a later cleanup touches nothing.
- **Test 3 — two workers, one order, 25 repetitions.** Exactly one
  worker releases each reservation; no duplicate events; reserved
  quantity never negative; exactly one order-expiry event.
- **Test 4 — duplicate cleanup, rollback, induced failure.** Repeated
  cleanup is a zero-work no-op; a rolled-back cleanup leaves zero
  partial effects; a trigger-induced failure on the second release
  aborts the whole batch, and a retry then succeeds exactly once.
- **Test 5 — bounded batch.** One order with 5 expired reservations:
  `p_limit=2` releases 2, then 2, then 1 + order expiry. Multiple
  orders share one budget. `p_limit=0` and `p_limit=1001` raise
  `invalid_batch_limit` (SQLSTATE 22023).
- **Test 6 — payment tiers.** `authorized` / `captured` / `refunded` /
  `partially_refunded` are never touched; `reconciliation_required`
  releases stock but preserves the order row and finance flag; no
  transaction, `created`-only, or `failed`-only release and expire.
- **Test 7 — listing contention.** Two cleanups on two orders sharing
  two listings in opposite expiry order, paused on their first listing
  update, then released together. If PostgreSQL reports a deadlock
  (40P01), the aborted transaction must have rolled back fully and a
  retry must complete safely; single-worker (sequential) operation is
  recorded as the exposure reducer.

## 4. Invariants (checked from database state after every scenario)

- `reserved_quantity >= 0`, `sold_quantity >= 0`,
  `available = total - reserved - sold` (generated column).
- `reserved_quantity` equals the sum of `active` reservation
  quantities for the listing; `sold_quantity` equals the sum of
  `consumed` reservation quantities.
- At most one `reservation_released` event and at most one `sold`
  event per reservation; at most one `pending_payment → expired`
  event per order.
- No expired order with a captured payment; no confirmed order
  without a captured payment.
- `released_at` set exactly when status is `expired`;
  `consumed_at` set exactly when status is `consumed`.
- All changes atomic on rollback (verified by Test 4).

The SQL for these checks lives in `assert_invariants` in
`backend/tests/test_pg_concurrency.py`.

## 5. Results

Run on real PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), disposable
cluster, database bootstrapped exactly as in §1 (baseline with the
four documented deviations, then W9.1, then W9.1.1). Full backend
suite: **423 passed** (408 pre-existing + 15 new), zero regressions.
Ruff check and ruff format are clean on both new files.

| Test | Result on real PostgreSQL |
| ---- | ------------------------- |
| test_00 signatures, wrapper resolution, grants | passed |
| Test 1 cleanup-first → confirm reconciles | passed |
| Test 2 confirm-first → cleanup skips (SKIP LOCKED) | passed |
| Test 3 two workers, same order, 25 iterations | passed |
| Test 4 duplicate cleanup, rollback, induced failure + retry | passed |
| Test 5 bounded batch (limits 2, 3, 1000, 0, 1001) | passed |
| Test 6 payment tiers (8 cases) | passed |
| Test 7 listing-lock contention | passed, deadlock reproduced 3/3 runs |

No test is reported as passed on anything other than real PostgreSQL.
Every scenario ends with `assert_invariants` checks against database
state (counters, events, order/payment status), not just the returned
JSON.

### Finding 1 — the W9.1.1 order-first lock closes the false confirmation

Test 1 proves the exact interleaving W9.1 left open: cleanup paused
holding the order lock, confirmation observed queued behind cleanup's
transaction (ungranted transactionid ShareLock on cleanup's xid),
cleanup committed (stock released, order expired), and confirmation
then routed to `reconciliation_required` with
`RESERVATION_NOT_ACTIVE_OR_INCOMPLETE` — never to `confirmed`. A
second confirm was a no-op. No confirmed-plus-released state exists
after the run. Test 2 proves the mirror: confirmation holding the
order lock, cleanup returning zero work without blocking, then
confirmation committing (reservations consumed, counters exact) and a
later cleanup touching nothing.

### Finding 2 — the residual listing-order deadlock is real, and bounded

Test 7 reproduces the W9.1.1-documented residual risk deterministically
(3/3 runs): two cleanups on two orders sharing two listings in
opposite expiry order, each paused holding one listing's row lock,
then released together → PostgreSQL aborts exactly one worker with
40P01. The aborted worker left zero partial effects (no release
events, order still `pending_payment`), and a retry completed both
orders exactly once (2 release events + 1 expiry event each, shared
listings reserved back to 0). Consequence is therefore bounded as
W9.1.1 states: atomic rollback, no corrupt state, safe retry via the
next worker pass. Single-worker operation removes the exposure
entirely (no second transaction to form the cycle). Eliminating the
risk entirely would require changing `confirm_payment_capture`'s
listing order, which is out of scope here and needs its own proposal.

### Finding 3 — one cleanup call claims all currently-eligible orders

While building Test 7, the first attempt (both workers started
together) showed the first caller releasing both orders while the
second found no work. That is correct batch behaviour — the claim
cursor locks the whole eligible set — not a defect, but it matters
for operations: concurrent workers partition work by "first caller
takes the currently-eligible set", and a second worker starting at
the same moment is not a correctness problem, only a no-op. Test 7
stages eligibility (second order expired only after the first worker
is paused) to force the two-transaction overlap deterministically.

### Test-harness lessons (not product defects)

- `pg_stat_activity` reads inside one open transaction do not
  reflect backends that connected after that transaction's first
  `pg_stat_activity` read. Observer connections in these tests run
  in autocommit (one transaction per poll) for that reason.
- A session waiting on a `FOR UPDATE` row lock appears in `pg_locks`
  as an ungranted transactionid ShareLock on the holder's xid, not
  as an ungranted tuple lock. Test 1 asserts the xid match, which is
  the precise proof of queueing behind the holder.
- `pg_current_xact_id()` returns `xid8`, not `bigint`; the barrier
  table uses `xid8`.
- `pg_get_function_identity_arguments` omits defaults; signature
  checks use `pg_get_function_arguments`.
- `confirm_payment_capture` returns a UUID object via psycopg, while
  fixtures use string ids; comparisons normalise with `str()`.

### What was not tested here

- The webhook HTTP layer (signature verification, event recording,
  Razorpay fetch): backend code, not executed here. Only
  `confirm_payment_capture`'s idempotency and reconciliation routing
  are proven at the database level.
- Row-level policies: not replayable from the tracking copy (see §1).
- `begin_payment_checkout` (requires `auth.uid()`): never executed;
  fixtures insert rows directly.
- Live Supabase PostgreSQL 17: tested here on 16.15. The exercised
  mechanics (`FOR UPDATE SKIP LOCKED`, EvalPlanQual re-checks,
  advisory locks, deadlock detection) are stable across these
  versions, but the version gap is stated, not hidden.

## 6. Known limitations

- Test PostgreSQL version may differ from live Supabase PostgreSQL 17
  (actual version recorded in §5: PostgreSQL 16.15). The tested mechanics
  (`FOR UPDATE SKIP LOCKED`, EvalPlanQual re-checks, advisory locks,
  deadlock detection) behave the same across supported versions, but
  the version gap is stated, not hidden.
- The webhook HTTP layer (signature verification, event recording,
  Razorpay fetch) is backend code and is not executed here; only
  `confirm_payment_capture`'s idempotency and reconciliation routing
  are proven at the database level.
- Row-level policies are not replayed (see §1): the tracking copy's
  policy statements are corrupted, and the tested functions are
  `SECURITY DEFINER`, so policy behaviour is out of scope.
- `begin_payment_checkout` (which requires `auth.uid()`) is not
  executed; fixtures insert orders and reservations directly, which is
  valid because neither tested function depends on it.
- The residual listing-order deadlock (W9.1.1) is investigated by
  Test 7; see Finding 2 in §5.

## 7. What this task does not change

- No merged migration file is modified.
- Neither W9.1 nor W9.1.1 is applied to production or staging.
- No worker or scheduler is deployed or started.
- No live Supabase resource, secret, environment variable, or
  configuration is changed.
- The W9.1.1 staging-migration decision stays separate and needs its
  own approval; this task's PR (#27) was merged by the owner, which
  merges the validation code and documentation only — it does not apply
  any migration or deploy anything.
