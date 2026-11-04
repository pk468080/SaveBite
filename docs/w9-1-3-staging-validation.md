# SaveBite W9.1.3 — PostgreSQL 17 and Razorpay Test-Mode Staging Validation

Status: **complete for disposable-environment validation — see the
acceptance table in §9.** All Stage D (10) and Stage E (4) tests passed
on real PostgreSQL 17.11 through the real FastAPI handler and real
PostgREST; the W9.1.2 concurrency suite re-ran 15/15 on the same PG 17
cluster; the full backend suite is 437 passed with zero regressions.
Real Razorpay test-API work remains BLOCKED (§6) — nothing in this
document claims a provider result.

Base: main `12517546` (PR #27, W9.1.2, merged by the owner). Branch:
`test/w9-1-3-staging-validation`. New test module:
`backend/tests/test_w913_webhook_races.py` (10 webhook tests + 4 race
scenarios). Companion correction: `docs/w9-1-2-postgres-concurrency.md`
status label reconciled with the merged PR #27 (counts and results in
that document are unchanged).

## 1. Stage A — staging environment readiness matrix

Read-only audit of the repo, deployment config, Supabase config, and
Razorpay integration. No staging environment exists in the repo.

| Item | State | Evidence |
| ---- | ----- | -------- |
| Staging Supabase project (ref / URL) | MISSING | `supabase/config.toml` links only the production project `zehnhqcfawagxbactvne`; no staging ref, URL, or credential anywhere in the repo |
| Staging DB credentials via an approved secret store | MISSING | No staging credential exists to check; real secrets live only in deployment env and are never hunted, pasted, or read from Vercel by this task |
| Razorpay test-mode credentials configured | MISSING | No test key id/secret in the repo; prior state (2026-11-01) is unchanged: test keys + webhook unconfigured |
| Backend staging URL | MISSING | Only production `https://backend-delta-rose-95.vercel.app` is referenced |
| Frontend staging URL | MISSING | Only production `https://savebite-gilt.vercel.app` is referenced |
| Test-mode webhook endpoint configured | MISSING | No staging endpoint exists to register in the Razorpay dashboard; dashboard settings were not touched |
| Staging background workers / scheduled jobs | MISSING | Workers exist only as code (`backend/app/reservation_cleanup.py`, `backend/app/notification_worker.py`); none deployed or scheduled anywhere |
| Env vars separated staging vs production | MISSING | `backend/app/config.py` defines an `environment` enum value `"staging"` and W8 docs describe staging as a future prerequisite — that is the only staging reference; `.env.example` carries placeholders only |
| Production Supabase accidentally in scope? | NO | The audit verified every Supabase reference resolves to the production project and STOPPED before connecting: no production connection was made for testing |

Consequence: Stage C real-provider parts and Stage F are BLOCKED (see
§6). That is a finding, not a failure to work around: no key was hunted
in any dashboard, nobody was asked to paste a secret, and no Vercel env
value was read.

## 2. Stage B — PostgreSQL 17 validation

Disposable local PostgreSQL 17 via the free PGDG repository
(`apt.postgresql.org`, `noble-pgdg`) plus `postgresql-17-postgis-3`
(PostGIS needed for the baseline's `geography` columns). Free software,
not paid infrastructure.

Bootstrap (W9.1.2 script, unchanged): the consolidated baseline is a
tracking copy, not replayable verbatim — the script pre-creates the
`auth` schema stub, strips the corrupted `to {, a, n, o, n, …}` role
lists from all 41 `CREATE POLICY` statements, applies foreign keys in a
second phase, and iterates Phase 1 until clean; then applies W9.1
(`20261101200000`) and W9.1.1 (`20261102210000`) verbatim, in order.

```bash
# Install (first run used PGDG; a later VM restore wiped /usr and the
# install was repeated from scratch — see §8)
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg
chmod 644 /usr/share/keyrings/postgresql.gpg   # apt drops to _apt; without this, NO_PUBKEY
echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt noble-pgdg main" \
  > /etc/apt/sources.list.d/pgdg.list
apt-get update
apt-get install -y postgresql-17 postgresql-17-postgis-3

# Bootstrap a disposable PG 17 cluster (PATH pinned so the script's
# binary lookup picks 17, not 16, when both are installed)
PATH=/usr/lib/postgresql/17/bin:$PATH python3 backend/tests/pg_bootstrap.py \
  --pgdata /tmp/savebite-pgtest17/data --socket-dir /tmp/savebite-pgtest17/sock \
  --port 54400

# Teardown when done
python3 backend/tests/pg_bootstrap.py --teardown \
  --pgdata /tmp/savebite-pgtest17/data --socket-dir /tmp/savebite-pgtest17/sock
```

Final verification (post-restore rerun, same commands): cluster
`PostgreSQL 17.11 (Ubuntu 17.11-1.pgdg24.04+2)`; bootstrap OK with all
four functions present and worker-RPC grants correct (anon false,
authenticated false, service_role true). The complete W9.1.2
concurrency suite re-ran against this PG 17 cluster: **15 passed in
2.9s** (first run, pre-restore: 15 passed in 3.1s on the same 17.11
build, including the listing-lock deadlock scenario). PG 17 vs PG
16.15 comparison: same 15 tests, same outcomes — no version-specific
differences found. This closes the W9.1.2 version gap for the
concurrency suite; live Supabase PG 17 itself remains untested (no
production contact, by rule).

Verified: `private.release_expired_reservations_v2`,
`public.backend_release_expired_reservations_v2`,
`private.confirm_payment_capture`,
`public.backend_confirm_payment_capture` all present; worker RPC
EXECUTE granted to service_role only (anon/authenticated false on the
public wrappers). The one gap found is §3, not a grant on the wrappers.

## 3. Finding — public wrappers unusable via PostgREST (blocking defect)

While building the Stage D harness, the first real PostgREST call to a
`backend_*` wrapper failed with 403 `permission denied for schema
private`. Root cause, verified from the migration files and live grants
in the disposable database:

- Every public `backend_*` wrapper is `LANGUAGE sql` with
  `SECURITY INVOKER` (`prosecdef = false` for all of them). A wrapper
  body that references `private.*` therefore requires the CALLER to
  hold `USAGE` on schema `private`.
- No migration grants `USAGE ON SCHEMA private` to anyone (grep over
  all `supabase/migrations/*.sql` finds nothing).
- `service_role` holds `EXECUTE` on the public wrappers and on the
  private functions, but `USAGE` on `private` is false — so the chain
  fails at name resolution before any function body runs.

Why it stayed latent: every prior test bypassed PostgREST (direct
psycopg as superuser, or `FakeSupabaseClient`), and production has
never run a real payment (Razorpay unconfigured, zero orders, worker
undeployed), so no `backend_*` RPC has ever succeeded through the
production PostgREST path either. Live grant state was NOT checked —
connecting to production is forbidden for this task — so the report
states the migration-chain fact, not a live fact.

Impact if unaddressed: the webhook handler's record/confirm/mark_failed
calls, the verify endpoint's confirm call, and both workers' RPC calls
would ALL fail through PostgREST in any environment (staging or
production) until fixed. This blocks the staging migration
independently of W9.1.1's lock fix.

Proposed forward-only fix (NOT applied anywhere except the disposable
test database, NOT added as a migration file in this branch — it needs
its own review and approval):

```sql
-- Proposed migration (separate PR, separate approval):
-- The backend's server identity needs schema USAGE so its already-
-- granted EXECUTE on backend_* wrappers can resolve private.* calls.
GRANT USAGE ON SCHEMA private TO service_role;
```

Safety note: grant to `service_role` ONLY, never to `PUBLIC`, `anon`,
or `authenticated`. Both `anon` and `authenticated` currently hold
`EXECUTE` on the private functions (PostgreSQL's default `PUBLIC`
grant, never revoked by any migration) — the missing `USAGE` is the only
thing stopping their direct private calls today, so a broad `USAGE`
grant would open that path. Follow-up hardening to consider separately
(not part of this proposal): `REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA
private FROM PUBLIC` while keeping the `service_role` grants, so the
entry control does not rest on a missing `USAGE` grant alone.

The Stage D/E tests apply this single `GRANT` in the disposable test
database only (fixture `pg17_session`, asserted after applying). That
is a documented test-environment deviation: the tests prove the
handler, races, and tiers through the real PostgREST path *given* the
proposed fix, and the failure without it is itself the defect report.

## 4. Stage C — Razorpay test-mode integration audit (code inspection)

Traced reservation → payment transaction → Razorpay order → gateway
association → server-side verification → provider fetch → DB
confirmation → webhook recording → duplicate/late/invalid handling,
from the actual code (`backend/app/routers/payments.py`,
`backend/app/razorpay_client.py`, `backend/app/supabase_client.py`,
baseline `private.confirm_payment_capture` /
`private.mark_payment_failed` /
`private.record_payment_webhook_event`).

What the code does (all verified by reading, then exercised by Stage D
where the harness allows):

- The backend talks to the database ONLY via Supabase PostgREST RPCs.
  The service-role client may call only `backend_*` names
  (`validate_rpc` allowlist); user-context clients may call only
  user-context RPCs; unknown names are rejected before any HTTP call.
- Webhook authentication is the HMAC-SHA256 of the RAW body, verified
  before anything is parsed, recorded, or acted on (missing/invalid →
  401, nothing processed, provider never consulted — proven by D2/D3).
- Event recording happens BEFORE acting, via
  `backend_record_payment_webhook_event`, which is idempotent on
  `(gateway, gateway_event_id)` (`ON CONFLICT DO UPDATE` no-op) and
  refuses unsigned events (`signature_verified` must be true, else
  42501). A crash between record and act is therefore recovered by
  redelivery (proven by D4/D10/E_D).
- `payment.captured` resolves through the provider FIRST
  (`get_payment`, then `get_order` for the transaction id from order
  notes, falling back to provider-fetched payment notes ONLY — never
  frontend-supplied notes). Checks, in order: provider `order_id` must
  equal webhook `order_id` (else 422); status must be `captured` (else
  422); currency must be INR (else 422); amount must be a positive int
  (else 422); transaction mapping must exist (else 422). Only then is
  `backend_confirm_payment_capture` called. Signature alone never
  proves capture (proven by D9).
- `confirm_payment_capture` semantics (baseline, read from the body):
  signature must be verified (else 42501); locks transaction `FOR
  UPDATE`, then order `FOR UPDATE`; already-captured → return order id,
  no-op (idempotent); amount mismatch → transaction AND order
  `payment_status` → `reconciliation_required` with failure code
  `AMOUNT_MISMATCH`, order STATUS unchanged, and the handler still
  returns `processed=True` (the confirm returned an order id) — so the
  reconciliation verdict lives in DB state, not in the HTTP flag
  (proven by D6; assertions check DB state, not `processed=False`);
  order not `pending_payment`, zero items, or live reservations ≠ items
  → `reconciliation_required` +
  `RESERVATION_NOT_ACTIVE_OR_INCOMPLETE`, order STATUS unchanged
  (proven by E_A/E_C); success → transaction `captured`, reservations
  consumed (`reserved → sold`), `sold` events, order `confirmed` +
  status event (proven by D1).
- `payment.failed` resolves the transaction through provider order
  notes only, then `backend_mark_payment_failed`. A captured
  transaction raises `captured_payment_cannot_be_failed` (P0001); the
  handler translates that to HTTP 200 with `processed=False` and
  `reason="already_captured"` — handled, not retried, and the capture
  is never overwritten (proven by D5). A failed event on a pending
  transaction marks it `failed` and sets order `payment_status` to
  `failed` only while the order is still `pending_payment` with no
  other live transaction (proven by D5 first half).
- Other events (including `order.paid`) are recorded but intentionally
  ignored — no second confirmation path.
- The verify endpoint (`POST /v1/payments/verify`) resolves through
  Razorpay's API FIRST, then checks the checkout signature over the
  provider-confirmed order id (never over a frontend-supplied id).
  Verify-endpoint tests are NOT in this module (webhook scope only).
- `RazorpayClient` base URL is `https://api.razorpay.com/v1`, auth is
  key id + key secret; provider failures surface as `BadGatewayError`
  (502). Amount conversion is `paise_to_rupees` (Decimal, never float;
  `Decimal(paise)/100` quantised to 0.01) and `rupees_to_paise` on the
  way out.
- `Settings.supabase_url` validation REQUIRES `https://`, so a local
  `http://` PostgREST URL cannot pass through normal `Settings`
  construction — the test Settings are built via `model_construct`
  (validation bypassed) for that reason only.
- Checkout retry (B1) was covered by W9.1.1 and is not re-tested here:
  the gateway-order lookup RPC is called before any create, attached +
  `created` orders are re-issued, non-attachable statuses fail before
  any provider order, and a create timeout is never auto-retried.

Real-provider sub-checks that could NOT run (no credentials): the
actual `https://api.razorpay.com/v1` calls, test-mode order creation,
and any genuine provider-delivered webhook. Those are BLOCKED (§6), and
the provider side of every Stage D/E test is the scripted fake
described in §5 — labelled as such in the test module, never presented
as a provider response.

## 5. Stage D/E — webhook tests and payment/expiry races

Harness (all real except the provider): real FastAPI app via
`TestClient`, real PostgREST 12.2.3 (binary, started by the test
fixture), real PostgreSQL 17, real `SupabaseRestClient` service client
(JWT with role `service_role`, minted per session with a throwaway
secret via stdlib HMAC). The provider is `FakeRazorpay` (canned
`get_payment` / `get_order` dicts + a call log + transient-failure
injection). Every webhook request is LOCALLY GENERATED and HMAC-signed
with a throwaway per-session secret — never a genuine
Razorpay-delivered webhook.

Test module: `backend/tests/test_w913_webhook_races.py`.
Helpers (fixtures, barrier, observation, invariants) are imported from
the W9.1.2 suite; fixtures are defined fresh in this module. Run
prerequisites: a bootstrapped PG 17 cluster (§2) + a PostgREST binary
at `/tmp/postgrest/postgrest` (or `SAVEBITE_POSTGREST_BIN`) + the DSN
in `SAVEBITE_PG_TEST_DSN` (default: the PG 17 socket above). The module
REFUSES a non-17 server and FAILS CLEARLY when the binary, the cluster,
or a free port is missing — never silently mocked.

Final result (post-restore rerun): **14/14 passed in 4.2s** — all 10
Stage D tests and all 4 Stage E scenarios green on real PostgreSQL
17.11 through the real handler + real PostgREST. The first run's 4
failures were all harness/test bugs, diagnosed and fixed, never product
defects: two wrong test expectations (cleanup's intermediate order
state; the failed-after-captured response field) and two race scenarios
that timed out on pause detection (the barrier-fired row is invisible
while its transaction is uncommitted — see the harness note below).
Full backend suite after the rerun: **437 passed** (423 at W9.1.2 + 14
new), zero regressions; Ruff check + format clean on the new module.

### Stage D — webhook security + reliability (10 tests)

| Test | What it proves (DB state asserted, not just HTTP) |
| ---- | ---- |
| D1 valid signature | 200 `processed=True`; provider `get_payment` + `get_order` called; 1 event row; order confirmed/captured; reservations consumed; listing 100/0/2/98; 1 sold event; 1 confirmed order event; invariants |
| D2 invalid signature | 401; 0 event rows; provider never consulted; order/tx/reservations/listing untouched |
| D3 modified payload after signing | 401; 0 event rows; provider never consulted; state untouched (raw-body handling correct) |
| D4 duplicate delivery ×2 | Both 200 `processed=True`; exactly 1 event row, 1 capture, 1 sold event, 1 confirmed event; no double consumption |
| D5 out-of-order / delayed | Failed on pending tx → tx `failed`, order `payment_status failed`; failed AFTER capture → HTTP 200, `processed=False`, `reason="already_captured"`, capture untouched, no regression |
| D6 wrong amount | Provider ₹50 vs order ₹100 → order `pending_payment` + `payment_status reconciliation_required`, tx `reconciliation_required`/`AMOUNT_MISMATCH`, reservations still active, no sold event, no confirm. Note: handler returns `processed=True` here by design (confirm returned an order id) — assertions check DB state |
| D7 wrong currency (USD) | 200 `processed=False`; event recorded but not acted on; state untouched |
| D8 gateway-order mismatch | Webhook order ≠ provider order → 200 `processed=False`; wrong transaction cannot be confirmed; state untouched |
| D9 provider verification | Payload claims captured + valid signature, provider says `created` → 200 `processed=False`, no confirm; call log proves `get_payment` ran (signature alone never confirms) |
| D10 retry after transient failure | First delivery: provider fetch fails → 200 `processed=False`, no state change, event row recorded (record-before-act). Redelivery: 200 `processed=True`, exactly 1 event row, 1 capture, 1 sold event |

### Stage E — payment + reservation races (4 scenarios)

Barrier technique (from W9.1.2, test-only triggers in the disposable
DB only): a session is paused mid-function on an advisory lock held by
the driver; the waiter is observed in `pg_stat_activity`/`pg_locks`
(ungranted transactionid ShareLock on the holder's xid). No test
depends on sleep timing.

| Scenario | Setup | Result asserted |
| ---- | ---- | ---- |
| E_A cleanup-wins-first | Expired reservations; cleanup paused holding the order lock; captured webhook submitted during cleanup; confirm observed queued on cleanup's transaction | Cleanup commits (order expired, stock released); confirm routes to reconciliation (`RESERVATION_NOT_ACTIVE_OR_INCOMPLETE`); order never confirmed; released stock never sold/consumed twice |
| E_B confirmation-wins-first | Live reservations; webhook confirm paused mid-function (barrier on consume) holding the order lock; cleanup runs during the pause | Cleanup returns promptly with zero work (no blocking); confirm then consumes exactly once; later cleanup touches nothing |
| E_C late captured payment | Expire + release first, then validly signed captured notification | Reconciled, never falsely confirmed, no inventory resurrection or duplicate movement; listing stays 100/0/0/100 |
| E_D duplicate captured ×3 | Same event id + body three times, sequential | Exactly 1 event row, 1 financial transition, 1 inventory consumption, 1 confirmed order event |

Precision note on E_B: the order is live, so it is not cleanup-eligible
in the first place — E_B proves the HTTP-handler variant (confirm
holding the lock, cleanup not blocking, exactly-once consumption).
Eligible-order skipping via `SKIP LOCKED` is proven by the W9.1.2 suite
(Test 3, two workers on one order) re-run on PG 17 in Stage B.

### Harness notes (not product defects)

- The sandbox's proxy environment breaks httpx client construction:
  its `NO_PROXY` list contains bare IPv6 entries that httpx cannot
  parse as URL patterns (`InvalidURL: Invalid port`). The `api_client`
  fixture removes the proxy variables for each test and restores them
  afterwards. Production (Vercel) has no such proxy environment.
- Standalone PostgREST serves at its root (`/rpc/...`), while the app's
  client targets Supabase's layout (`/rest/v1/rpc/...`). The fixture
  starts a test-only stdlib reverse proxy that strips the `/rest/v1`
  prefix — the routing Supabase's Kong layer performs in production.
  An early 404 with an empty body was this path mismatch, not a
  product failure; an early 502 was the proxy-env `InvalidURL`,
  translated by the handler's upstream-error mapping (any non-`ApiError`
  becomes 502 "Upstream service error" — correct behaviour for a real
  upstream failure, misleading only as a test symptom).
- PostgREST request logs are block-buffered when redirected to a file;
  absence of lines in a live log file proves nothing until the process
  exits and flushes. (This misled one debugging pass; the direct
  `curl` reproduction settled it.)
- Pause detection must use `pg_stat_activity`, never the
  `test_barrier_fired` row: that INSERT is part of the paused
  transaction itself, so it stays invisible to observers until the
  transaction commits. Polling the row while paused times out (this
  exact mistake failed two race scenarios on the first run; the fix
  mirrors W9.1.2's `wait_blocked` on the session's Lock wait).
- Two test-expectation corrections made during the run (test bugs, not
  product bugs): the v2 cleanup's RELEASE+EXPIRE tier sets an expired,
  never-paid order to (`expired`, `failed`) — not (`expired`,
  `created`) — and the failed-after-captured webhook response is
  `processed=False` with `reason="already_captured"`, not an
  `already_captured: true` field.

## 6. Stage F — real provider test-mode checkout: BLOCKED

Not run. Precise missing pieces, in order:

1. No valid Razorpay test-mode credentials exist (no key id/secret
   configured anywhere; nothing was created, and no dashboard setting
   was changed — dashboard changes need explicit owner approval, which
   this task does not hold).
2. No approved non-production environment exists (no staging Supabase,
   no staging backend/frontend URL, no externally accessible staging
   webhook endpoint). Provisioning a tunnel or changing dashboard
   settings to create one was STOPPED per the task rules rather than
   worked around.
3. Therefore: no test-mode Razorpay order was created through the
   backend flow, no approved test payment was completed, no genuine
   provider-delivered webhook was received, and no webhook signature
   was validated against a provider signature.

What stands in place of Stage F: Stage D/E's locally generated
HMAC-signed requests (throwaway secret) through the real handler +
real PostgREST + real PG 17, with the provider side scripted. Those
prove handler logic, idempotency, and race behaviour — they do NOT
prove the provider integration. Stating this plainly: locally generated
signed requests are NOT genuine provider-delivered webhooks, and no
result in this document claims otherwise.

## 7. Stage G — operational safety (verify or document only)

No worker was deployed or started. Findings are from code inspection
(`backend/app/reservation_cleanup.py`,
`backend/app/notification_worker.py`, `backend/app/routers/admin.py`,
`backend/app/routers/payments.py`, `backend/app/errors.py`) plus the
race/idempotency proofs in §5.

| Requirement | Verdict | Evidence |
| ---- | ---- | ---- |
| Single cleanup-worker instance while listing-lock contention remains | REQUIRED AT DEPLOYMENT, NOT CODE-ENFORCED | The worker code does not take a lock or lease; its docstring says concurrent workers are safe (disjoint sets via `SKIP LOCKED`, released rows never re-processed — true for correctness). But W9.1.2 Test 7 proves two workers CAN deadlock (40P01, bounded rollback, retry). So: correctness-safe concurrent, deadlock-prone concurrent — deploy exactly one instance until the listing-order fix lands |
| Cleanup failures observable | YES, VIA LOGS + EXIT CODES | Loop mode logs every failed pass (`logger.error` with exception type + message, no ids/amounts/keys); `--once` exits 1 on RPC failure so a scheduler can alert; every pass logs its counts |
| Worker retries bounded + safe | YES (BOUNDED PASS, IDEMPOTENT RETRY) | Each pass is one bounded RPC call (batch clamped 1–1000 server-side); retries re-run the same idempotent RPC; a partially processed batch is picked up by the next pass because only `active` rows are selected; `--once` does not retry internally (caller/scheduler decides) |
| Duplicate execution cannot corrupt inventory | PROVEN | W9.1.2 (SKIP LOCKED partition, duplicate/rollback/retry exact) + W9.1.3 D4/E_D (webhook duplicates exactly once) + E_B (exactly-once consumption); release only ever touches `active` rows |
| Reconciliation-required payments visible for admin review | YES | Admin dashboard exposes `reconciliation_required_count`; the admin orders list (`GET /v1/admin/orders`) accepts a `payment_status` filter, so the exact reconciliation queue is listable for review |
| Webhook errors logged without exposing secrets | YES | Handler errors go through `translate_upstream_error` (no token/key/SQL echo); the app's unhandled-error log records only the exception type; request logs record method/path/status/request id only; the webhook secret and signatures are never logged; the raw payload is stored in `private.payment_webhook_events` (audit, DB-only, not logs) |
| Worker health + last-success timestamps monitorable | PARTIAL — GAP | No heartbeat row, health endpoint, or persisted last-success timestamp exists for either worker. Observability is logs + `--once` exit codes only. At staging deployment, alerting must be built on log/scheduler signals, or a heartbeat record added (future work, not this task) |
| A failed cleanup/webhook cannot silently produce inconsistent inventory | YES, WITH ONE OPS NOTE | Cleanup batches and webhook confirms are each a single atomic RPC transaction (abort = zero partial effects, proven W9.1.2 Test 4 + §5 races); failures surface as 5xx/502 or `processed=False` + logs. NOTE: a transient webhook failure returns HTTP 200 with `processed=False`, so Razorpay will NOT auto-retry it — recovery needs manual redelivery or a later event. Monitor `processed=False` bursts and the recorded event rows; the recorded event is the audit trail, not a retry |

## 8. Environment notes (reproduction hazards encountered)

- Sandbox apt is VERY slow (a single `apt-get update` took ~10 minutes
  on the first run). Do not mistake slowness for a hang. The
  `userConfirmationStatus: timed_out` flag on exec results is a red
  herring; commands succeed despite it.
- The PGDG keyring file must be world-readable (`chmod 644
  /usr/share/keyrings/postgresql.gpg`) or apt reports NO_PUBKEY for
  `7FCC7D46ACCC4CF8` (apt drops privileges to user `_apt`).
- Do not pipe a long apt install through `tail` — it hides progress
  and invites a premature kill (this happened once on the first run;
  the key + source list had in fact completed).
- `fuser` on apt's lock file does not reliably report the holder; wait
  on the holder PID (`kill -0 <pid>`) instead.
- A VM restore during this task wiped `/usr` (PostgreSQL 16 + 17) and
  `/tmp` (clusters, PostgREST binary) while `~/workspace` survived.
  The PG 17 install and the disposable cluster were rebuilt from
  scratch afterwards; the branch, the test module, and this document
  survived because they live in the workspace. Disposable paths must
  always be treated as rebuildable, never as durable.
- The runtime gates egress to some hosts: the standard `apt-get
  update` stalled on a pending approval for `deb.nodesource.com`
  (a source the VM image ships, unrelated to this task). The
  workaround used here was a restricted sources dir (Ubuntu +
  PGDG only) with alternate lists/cache dirs
  (`-o Dir::Etc::sourceparts=/tmp/apt-src.d
  -o Dir::Etc::sourcelist=/tmp/apt-src-empty
  -o Dir::State::lists=/tmp/apt-lists2 -o Dir::Cache=/tmp/apt-cache2`),
  which completed without that gate; the final packages
  (`postgresql-17` 17.11, `postgresql-17-postgis-3` 3.7.0) are confirmed
  installed via dpkg.
- `/tmp` here is a 512MB tmpfs. The restricted update's partial
  downloads (232MB) filled it completely, which then failed a later
  install step with "No space left on device" — free the partial dirs
  before installing, and keep disposable apt dirs small or outside
  `/tmp` when possible.
- PostgREST 12.2.3 binary (verified for this run):
  `https://github.com/PostgREST/postgrest/releases/download/v12.2.3/postgrest-v12.2.3-linux-static-x64.tar.xz`
  (302 to CDN — valid artifact). Place it at `/tmp/postgrest/postgrest`
  or set `SAVEBITE_POSTGREST_BIN`.

## 9. Acceptance table

Every outcome marked exactly one of PASSED (actual test executed
successfully), FAILED (actual test executed and failed), BLOCKED
(required environment or permission unavailable), NOT TESTED (not
executed), STATIC REVIEW ONLY (inspected but not executed).

Final marks from the post-restore rerun (all on real PostgreSQL 17.11
unless stated). The full backend suite is 437 passed (423 + 14 new),
zero regressions.

| Validation outcome | Result | Evidence |
| ---- | ---- | ---- |
| PostgreSQL 17 migration compatibility (actual PG 17 execution) | PASSED | §2 — bootstrap OK, 4 functions present, grants correct |
| W9.1.2 concurrency regression suite on PG 17 (real PG 17 execution) | PASSED | §2 — 15/15 in 2.9s, same outcomes as PG 16.15 |
| Razorpay test API integration (actual test-mode provider API responses) | BLOCKED | §6 — no test credentials, no staging environment |
| Webhook signature validation (actual FastAPI endpoint tests) | PASSED | §5 D2/D3 — 401, no event row, provider never consulted |
| Duplicate webhook handling (database-backed idempotency assertions) | PASSED | §5 D4/E_D — exactly 1 event row, 1 capture, 1 consumption |
| Payment/expiry race (concurrent PG sessions) | PASSED | §5 E_A–E_D — queueing observed in pg_locks, reconciliation/exactly-once asserted from DB state |
| Late captured payment (reconciliation state verified) | PASSED | §5 E_C — expired + reconciliation_required, no resurrection |
| Inventory invariants (database queries after every scenario) | PASSED | §5 — asserted after every D/E scenario |

## 10. Remaining risks

- The §3 `USAGE` grant is unapplied anywhere durable. Until its
  separate migration is approved and applied (staging first), every
  `backend_*` RPC fails through PostgREST — the staging migration
  cannot proceed without it.
- The residual listing-lock deadlock (W9.1.2 Test 7) is unchanged:
  bounded, atomic, safe-retry, removed entirely only by single-worker
  operation or by changing `confirm_payment_capture`'s listing order
  (separate, justified scope).
- `anon`/`authenticated` hold `EXECUTE` on private functions (default
  `PUBLIC` grant never revoked); the missing `USAGE` grant is currently
  the only barrier to direct private calls. The §3 follow-up hardening
  (revoke from `PUBLIC`, keep `service_role`) should be reviewed with
  the `USAGE` fix.
- Webhook `processed=False` on transient failure returns HTTP 200, so
  Razorpay does not auto-retry; operations must monitor and redeliver
  (see §7).
- Live Supabase PostgreSQL 17 itself is still untested (this task
  tested disposable PG 17 only, by rule — no production contact).
- Webhook/RLS/`begin_payment_checkout` gaps from W9.1.2 carry forward
  except where this task covers them: the webhook HTTP layer IS now
  covered (Stage D/E); RLS policies are still not replayable from the
  tracking copy; `begin_payment_checkout` (requires `auth.uid()`) is
  still never executed.
- No worker heartbeat / last-success record exists (§7 gap).
- CI (GitHub Actions) is not verified — the billing-lock history means
  runs may never start; never claim CI green without an observed
  successful run.

## 11. Pre-staging-migration checklist

Nothing here applies a migration. Each item needs its own owner
approval before it happens; this checklist is the gate, not the act.

- [ ] §3 permission-boundary migration reviewed, approved, and applied
      to STAGING only: superseded by W9.1.4
      (`supabase/migrations/20261104120000_w914_rpc_permission_boundary.sql`,
      docs/w9-1-4-rpc-permission-boundary.md, PR unmerged) — the
      one-line `USAGE` proposal is NOT the migration to apply; the
      W9.1.4 migration grants `USAGE` to `authenticated` and
      `service_role` only, revokes `PUBLIC EXECUTE` on all private
      functions, and re-grants explicitly per the §7 matrix. This
      item stays UNCHECKED: nothing here is applied to staging.
- [ ] W9.1 migration (`20261101200000`) applied to STAGING, then W9.1.1
      (`20261102210000`), in timestamp order, verified by function
      presence + grant checks (service_role only on wrappers).
- [ ] W9.1.2 concurrency suite re-run against the STAGING database
      (not just disposable PG) — or an explicit, recorded decision that
      disposable-PG evidence suffices for staging.
- [ ] Razorpay test-mode credentials configured in STAGING only
      (key id/secret + webhook secret), and a test-mode webhook
      endpoint registered pointing at staging (dashboard change needs
      explicit approval).
- [ ] One Razorpay test-mode webhook end-to-end on staging: confirm +
      expiry race (the Stage D/E scenarios replayed against staging
      data, not just disposable PG).
- [ ] Cleanup worker deployed as a SINGLE instance on staging
      (scheduler or long-running process, `--once` exit codes or log
      alerts wired up; no second instance while listing-lock exposure
      remains).
- [ ] Notification worker deployment + schedule decided (same
      single-instance consideration; outbox processor RPC grants
      already fixed in W9.1.2's privilege work).
- [ ] Admin review path checked on staging: dashboard
      `reconciliation_required_count` + orders list filtered by
      `payment_status=reconciliation_required`.
- [ ] `processed=False` webhook monitoring wired (alert on bursts;
      manual redelivery procedure documented).
- [ ] Worker heartbeat / last-success observability decided (log-based
      alerting now, or a heartbeat record added later).
- [ ] Storage bucket policies verified live (B7, still open from W8).
- [ ] Backend Vercel deployment config recorded in the repo (B8, still
      open from W8).
- [ ] Production migration approval obtained SEPARATELY — staging
      approval does not cover production.
