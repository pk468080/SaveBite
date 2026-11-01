# SaveBite W8 — Production readiness audit (full report)

**Branch:** `feature/w8-production-readiness`, from verified
main `39896d8` (PR #21 merge; PRs #19, #20, #21 all merged).
**Date:** 2026-11-01. **Status:** preparation only — no live
production resource was changed by this milestone.

**Method:** repo-file audit in four parallel read-only areas
(backend, payments + worker, frontend + storage,
database + security + CI/CD), plus read-only
public-endpoint evidence verified on 2026-11-01 (see §A).
Local tests are reported as local; mocked tests as
mocked; nothing below presents a local or mocked result
as production proof.

**Environment limits:** no Postgres binaries in the
sandbox, so migration replay was impossible (pglast parse
+ consistency checks only). No Docker/Podman, so Docker
builds were not verified locally. GitHub Actions has an
account-wide billing lock (account issue, not a code
defect), so no CI run is claimed green.

## A. Executive summary

**Is SaveBite ready for a controlled production release?
No — NOT READY FOR PRODUCTION.** The code is in
genuinely good shape in most areas (fail-closed auth,
payments, and secrets handling; clean client separation;
sound worker mechanics), and the live website + backend
are already deployed and answering. But four things block
a real launch, and none of them is fixed by deploying
what exists today:

1. **Checkout retry is broken (BLOCKER).** After a
   successful gateway-order attach, retrying checkout in
   the same tab returns 422. A customer who dismisses the
   Razorpay modal, or loses the checkout response, cannot
   pay without discovering the new-tab escape hatch.
2. **Notifications cannot run (BLOCKER).** The W7
   migrations are unapplied, the worker RPC grants are
   missing, and no worker or scheduler is deployed. Even
   with the migrations applied, nothing delivers until a
   worker exists.
3. **Payments cannot run (BLOCKER).** Razorpay keys and
   the webhook are not configured.
4. **Two things cannot be proven from the repo
   (BLOCKER-adjacent).** Storage-bucket policies are not
   in the baseline SQL, and the live backend's Vercel
   deployment configuration is not in the repo. Both need
   a live-dashboard check before launch.

W8 fixes what can be fixed safely in code (per-recipient
dedup keys, RPC grants file, loud `SITE_URL` failure,
docs-in-production, `$PORT`, security headers, sitemap
hygiene) and specifies the rest exactly. The recommended
path is: fix the checkout retry, apply W7 + W8 migrations
to a staging project, deploy the worker to staging,
configure test-mode Razorpay, and run the Phase F smoke
tests — then return for a controlled production release
decision. See `release-runbook.md`.

**Architecture (current, verified + repo evidence):**

```mermaid
flowchart LR
  Browser["Customer / merchant / admin\nNext.js on Vercel\nsavebite-gilt.vercel.app"] -->|NEXT_PUBLIC_API_BASE_URL| API["FastAPI backend\nbackend-delta-rose-95.vercel.app"]
  Browser -->|Supabase Auth (publishable key)| SB["Supabase\nsurplus-food-marketplace\nap-south-1"]
  API -->|user-context RPCs| SB
  API -->|service-role RPCs only| SB
  API -->|server-side orders + verify| RZ["Razorpay\n(test mode planned)"]
  RZ -->|webhook payment.captured/failed| API
  Worker["Notification worker\n(python -m app.notification_worker)\nNOT DEPLOYED"] -->|service-role RPCs| SB
  Merchant["Merchant browser"] -->|listing-media upload| SB
  SB -->|PostgREST / Auth| API
```

Data flow in one line: the browser talks to Supabase
Auth directly (publishable key only) and to FastAPI for
everything else; FastAPI enforces auth/RBAC and calls
Supabase only through allowlisted RPCs; Razorpay confirms
payments server-side only; the (undeployed) worker drains
the transactional outbox the DB triggers fill.

## B. Service-by-service readiness

### Frontend — WARNING
- PASS: no secrets in the browser bundle; clean browser /
  server Supabase client separation; refresh-only
  middleware with server-validated `getUser()`; backend-
  enforced admin gate; API base URL throws loudly if
  unset; no hardcoded localhost in production paths;
  image `remotePatterns` confined to `listing-media`.
- FIXED IN W8: `NEXT_PUBLIC_SITE_URL` now fails loudly
  instead of silently falling back to localhost (the
  2026-11-01 confirmation-link failure class); auth
  routes removed from the sitemap (robots already
  disallowed them); minimal security headers added.
- WARNING (open): no `/auth/callback` route and sign-up
  passes no `emailRedirectTo`, so confirmation-code
  session establishment has no code path (users sign in
  manually after confirming — works, but UX gap); no CSP
  yet (needs allowlisting for the Razorpay script and
  Supabase hosts); backend error messages surface
  verbatim in UI (acceptable for current generic
  messages).
- NOT VERIFIED: storage-bucket policies (not in repo);
  admin gate 401/403 → `/unauthorized` path live;
  Vercel default headers.
- Live (verified 2026-11-01): production Ready on main
  `39896d8`; homepage / sign-up / sign-in load clean;
  `/admin` redirects to sign-in; `NEXT_PUBLIC_SITE_URL`
  set for All Environments; Supabase Site URL + 1
  redirect URL both production.

### FastAPI backend — WARNING
- PASS: fail-closed secret handling (`SecretStr`, no
  hard-coded secrets); PR #20 auth-check apikey and
  PR #21 PostgREST secret-key behaviours confirmed in
  code; readiness requires the service-role key and
  returns only boolean check states; auth via Supabase
  Auth (no local JWT decode, no trusted header/body id);
  strict user-context vs service-role separation with
  RPC allowlists; CORS with `*` banned in production;
  error envelope + request IDs; JSON logging without
  secrets; Decimal paise handling.
- FIXED IN W8: interactive docs disabled when
  `ENVIRONMENT=production`; Dockerfile honours `$PORT`
  (default 8000).
- WARNING (open): no lifespan/startup-shutdown handlers
  (missing production secrets surface as 503-at-readiness,
  not at boot); Pydantic datetimes not required to be
  timezone-aware (naive-vs-aware `TypeError` risk in
  time-window logic); log timestamps use host-local
  offset, not UTC; single-process uvicorn, no
  `--proxy-headers` (fine for MVP).
- NOT VERIFIED: the exact production startup command for
  the live Vercel backend — no `vercel.json`,
  `render.yaml`, or Vercel adapter exists in the repo,
  while the live backend runs on Vercel. The only
  repo-documented production command is the container
  one (`uvicorn app.main:app --host 0.0.0.0 --port
  ${PORT:-8000}`). Record the Vercel project's build/start
  settings before release.
- Live (verified 2026-11-01): `/v1/health/ready` returns
  READY with all 4 checks ok.

### Supabase database + migrations — BLOCKER
- PASS (file-level): W7 chronological order and
  dependencies correct; every table/column/enum literal
  referenced exists in the baseline; all six W7 functions
  use `SECURITY DEFINER` + empty `search_path` + fully
  qualified names; RLS on preferences (own-row only) and
  notifications (no INSERT policy — DEFINER-only writes,
  correct); mandatory-category CHECK mirrors the API.
- BLOCKER (fixed in a W8 file, not applied): W7 dedup
  keys have no user component, so multi-recipient events
  deliver to the first recipient only
  (`20261101130000_w8_notification_dedup_per_recipient.sql`
  fixes it; must apply with the W7 files, in order,
  before the worker starts).
- BLOCKER (fixed in a W8 file, not applied): no EXECUTE
  grant for either W7 worker RPC in the W7 files, and
  Postgres defaults leave new functions executable by
  PUBLIC
  (`20261101131000_w8_notification_rpc_grants.sql`
  revokes PUBLIC and grants service_role; verify with
  `has_function_privilege` for anon / authenticated /
  service_role at apply time).
- BLOCKER: W7 files are not applied to live at all.
- WARNING: claim query has no composite
  `(channel, status, available_at, created_at)` index
  (fine at pilot scale); retry-backoff comment overstates
  the 30-minute cap (5-attempt ceiling dead-letters
  first — comment nit, not code); store-trigger guard
  has a dead disjunct; rerun idempotency is weak (no
  `IF NOT EXISTS` on triggers/indexes — standard for
  one-shot migrations; never re-run, fix forward).
- WARNING (known, handled): baseline mismatch — live has
  15 original migrations, the repo holds one
  consolidated tracking baseline that must never be
  pushed to live. No repo artifact can prove live
  schema/grants state.
- NOT VERIFIED: live schema/grants/row state (including
  whether any `notifications` row would violate the new
  type CHECK at apply time); live storage-bucket
  policies; migration replay (no Postgres here).
- Note: the baseline file does not pglast-parse (line
  939 renders a policy role list as individual
  characters — a pre-existing introspection artifact).
  It is a tracking copy, never applied; W7 files
  (6/5/12 statements) and W8 files (1/4 statements)
  all parse clean.

### Authentication / authorization — PASS
- Supabase Auth verification per request; JWT never
  decoded locally; no trusted header/body identity.
- RBAC reads roles from the DB (revoked/inactive
  filtered twice); admin gate requires
  `operations_admin` or `super_admin` on every admin
  route. Known bound: `support_agent`,
  `finance_admin`, `compliance_admin` cannot verify
  through the gate pending an approved DB fix (M11
  limitation, documented, not a W8 change).
- RLS: enabled on all 25 public tables; private tables
  service-role-only by design. No service-role reference
  anywhere under `apps/web/app` or `apps/web/lib`.

### Razorpay — BLOCKER
- PASS: reservation flow; server-side order creation
  from DB amounts (never the request body); Decimal
  paise conversion with 422 on non-integral values;
  checkout response shape (public `key_id` only);
  verify = provider fetch (captured + INR + matching
  order id) + checkout HMAC + confirm; webhook raw-body
  HMAC verified before any parse/act; event dedup on
  `(gateway, gateway_event_id)`; duplicate/delayed
  safety (capture never overwritten by later failure);
  frontend callback alone never confirms; secrets
  hygiene (no secret in frontend code or logs).
- BLOCKER (code, not fixed in W8 — needs a Postgres
  replay to verify): same-tab checkout retry after a
  successful gateway-order attach returns 422
  (`gateway_order_id_conflict`). See §C.
- BLOCKER (deployment): Razorpay keys + webhook not
  configured; webhook must be created in Test Mode
  (events `payment.captured`, `payment.failed`) against
  `https://<api-domain>/v1/webhooks/razorpay`.
- WARNING: no admin surface for the
  `reconciliation_required` queue, dead-letter outbox
  rows, or unresolvable webhook events (direct DB access
  only today); no `payment.failed` Checkout handler
  (failure display depends on the webhook landing);
  payment captured after the ~5-minute reservation
  lapses lands in reconciliation with no auto-resolution;
  `backend_release_expired_reservations` has no
  caller/scheduler; verify does not check caller
  ownership of the order (documented trust assumption:
  unforgeable signature + provider fetch).
- Known gap (fail-closed, worked around): no approved
  RPC maps gateway order id → payment transaction id;
  resolution goes through Razorpay order notes read back
  server-side. Proposed follow-up: approve the
  server-only lookup RPC (also enables checkout-status
  recovery).

### Notification worker — BLOCKER
- Worker code sound: `python -m
  app.notification_worker [--once] [--interval-seconds
  60] [--batch-size 50] [--window-minutes 60]
  [--worker-id NAME]`; fail-closed without service key
  (exit 2); `--once` exit 0/1/2 semantics;
  `FOR UPDATE SKIP LOCKED` claiming with 10-minute
  stale-claim recovery; backoff ~1/2/4/8 min, dead-letter
  at 5 attempts; SIGINT/SIGTERM graceful shutdown;
  counts-only logging; reminder rule mirrors the Python
  `reminder_due` exactly (confirmed/ready_for_pickup +
  captured + 60-minute window + dedup).
- BLOCKER: no worker or scheduler is deployed or
  configured anywhere in the repo (no `render.yaml`,
  `Procfile`, `vercel.json`, or cron config). Even after
  the migrations are applied, nothing delivers until a
  worker exists. See `worker-deployment-plan.md`.
- WARNING: `--once` exits 0 even with dead letters
  (scheduler must parse stdout JSON counts); CLI ranges
  unvalidated (negative window silently enqueues
  nothing); reminder timestamp comes from the worker
  host clock, not DB `now()`; reminder-RPC failure
  stalls all delivery for that pass; `--once` processes
  one batch per run, so a backlog above 50 per
  15-minute cron run drains slowly (loop mode or a
  shorter interval is safer under burst load).

### Scheduler — BLOCKER
- No scheduler exists for the worker, for pickup
  reminders, or for `backend_release_expired_reservations`.
  W8 configures none (forbidden by the brief); the plan
  is in `worker-deployment-plan.md`.

### Storage — WARNING
- Upload mechanics sound: browser upload to
  `listing-media` at `<listing_id>/<timestamp>-<name>`
  (sanitized, `upsert: false`, 5 MB + JPEG/PNG/WebP
  client checks), then registration via API; DB has
  INSERT/SELECT policies only, no UPDATE/DELETE.
- WARNING: MIME/size enforcement is client-side only;
  bucket-level enforcement NOT VERIFIED; upload path
  uses the URL param, not the backend-validated id;
  orphan risk if upload succeeds but registration
  fails (no cleanup/delete path); no image-removal path
  once published (a wrong image stays public); no
  merchant-facing document upload exists (FSSAI approval
  depends on an out-of-band channel whose handling is
  NOT VERIFIED — define it before onboarding).
- NOT VERIFIED: bucket policies for all four buckets
  (`avatars` public, `listing-media` public,
  `incident-evidence` private, `merchant-documents`
  private) — the baseline contains no `storage.buckets`
  inserts or storage policies. Verify live before
  merchant images go live.

### CI/CD — WARNING
- Present: `.github/workflows/ci.yml` — backend job
  (pytest, Ruff check + format check, Mypy, pip-audit
  on both requirement files) + Docker job (build +
  `/health` smoke test). Actions major-version pinned.
- Gaps: no web job (no typecheck/lint/test/build/
  Playwright despite those scripts existing); no
  migration-replay job (tests are file-parse only, so
  the dedup bug and grants gap could not be caught by
  CI as written); no deploy job. Triggers are PR-to-main
  and push-to-main only — feature-branch pushes run
  nothing until a PR opens (intentional per the file's
  own comment).
- Billing lock: no evidence in the repo either way, so
  its state is NOT VERIFIED from repo evidence. Do not
  claim CI is green. Once resolved, watch the first PR
  run end-to-end and record it.
- Constraint honoured: no `.github/workflows/*` file was
  changed in this PR (API push of workflow files fails
  with 403). The recommended jobs are documented here
  and in the PR as a manual follow-up: web job +
  Postgres migration-replay job (apply baseline + W7 +
  W8 files to an empty DB).

### Monitoring / backups / recovery — WARNING
- Present: structured JSON logging with request IDs;
  per-request method/path/status/timing logs;
  counts-only worker logs; `GET /health` + `GET
  /v1/health/ready`; Docker `HEALTHCHECK`.
- Absent: no monitoring, alerting, uptime checks, or
  error tracking in code or docs; no backup/restore
  documentation, retention statement, PITR statement,
  or restore test anywhere. Supabase platform backups
  depend on the project plan and live settings — NOT
  VERIFIED from the repo. Do not claim backups exist.
- Required before launch (see
  `monitoring-recovery-runbook.md`): readiness + worker-
  failure alerting (dead-letter `failed` rows, stuck
  `processing` rows, outbox backlog), webhook-failure
  visibility, and a backup/restore runbook with a
  tested restore.

## C. Critical blockers

### B1. Checkout retry returns 422 after a successful attach
- **Component:** backend `begin_payment_checkout` /
  `attach_gateway_order` + frontend checkout key reuse.
- **Evidence:** `create_checkout` unconditionally
  creates a new Razorpay order, then attaches it;
  `attach_gateway_order` allows re-attaching the same id
  but raises `gateway_order_id_conflict` for a different
  one. The frontend reuses one idempotency key per order
  for the whole tab session (`sessionStorage`, never
  cleared), while the checkout page advertises retry
  after a dismissed or failed attempt.
- **Impact:** a customer who dismisses the Razorpay
  modal, or loses the checkout response, cannot pay in
  the same tab. The new-tab escape hatch is
  undiscoverable in-UI and leaves orphan `created`
  transactions with no cleanup.
- **Fix (reviewed follow-up, NOT in W8):** extend
  `begin_payment_checkout` to return the already-
  attached `gateway_order_id` when one exists and have
  `create_checkout` reuse it; alternatively approve the
  proposed server-only
  `backend_get_payment_transaction_by_gateway_order`
  lookup RPC, which also enables a checkout-status
  recovery endpoint. Verify against Postgres (replay)
  before merging — this is payment-path SQL and was
  deliberately not changed without a replay.

### B2. W7 dedup drops multi-recipient notifications
- **Component:** `private.w7_enqueue_notification`
  + dedup indexes (W7 delivery migration).
- **Evidence:** key built without a user component;
  triggers loop per recipient; second+ recipients hit
  `ON CONFLICT DO NOTHING` on both outbox and delivery
  indexes.
- **Impact:** for `new_paid_order`,
  `merchant_pickup_completed`,
  `payment_reconciliation_required`, and application /
  store events, only the first recipient is notified.
- **Fix (DONE in W8, file only):**
  `20261101130000_w8_notification_dedup_per_recipient.sql`.
  Still a blocker until applied with the W7 files, in
  order, before the worker starts.

### B3. W7 worker RPC grants missing
- **Component:** `backend_process_notification_outbox`,
  `backend_enqueue_pickup_reminders`.
- **Evidence:** zero GRANT/REVOKE statements in the W7
  files; Postgres defaults leave new functions
  executable by PUBLIC.
- **Impact:** direct PostgREST callers are not
  constrained by the app-level allowlist; the processor
  trusts its caller.
- **Fix (DONE in W8, file only):**
  `20261101131000_w8_notification_rpc_grants.sql`
  (revoke PUBLIC, grant service_role). Still a blocker
  until applied and verified with
  `has_function_privilege` for anon / authenticated /
  service_role.

### B4. No notification worker or scheduler deployed
- **Component:** worker + scheduler (deployment).
- **Evidence:** no `render.yaml`, `Procfile`,
  `vercel.json`, or cron config in the repo; worker
  docstring states deployment is not done.
- **Impact:** no outbox delivery, no pickup reminders,
  even after migrations are applied.
- **Fix:** deploy per `worker-deployment-plan.md`
  (staging first), with dead-letter / stuck-row
  alerting. Requires B2 + B3 applied first.

### B5. Razorpay keys + webhook not configured
- **Component:** backend env + Razorpay dashboard.
- **Evidence:** user decision (test mode, keys later);
  no keys in repo (correctly); webhook endpoint fails
  closed without the secret.
- **Impact:** no live payment possible; no webhook
  confirmations.
- **Fix:** set test-mode keys + webhook secret in the
  backend deployment env; create the webhook in Test
  Mode for `payment.captured` + `payment.failed` at
  `https://<api-domain>/v1/webhooks/razorpay`; run a
  test-mode charge end to end in staging before any
  production key.

### B6. W7 migrations unapplied
- **Component:** live Supabase schema.
- **Evidence:** W7 files state NOT APPLIED TO LIVE;
  no live change in W7.
- **Impact:** notification preferences, outbox, and
  delivery machinery do not exist live.
- **Fix:** apply W7 + W8 files in timestamp order
  through the approved process (release-runbook
  Phase B), with the apply-time checks in §B above.

### B7. Storage-bucket policies not verifiable from repo
- **Component:** Supabase Storage policies.
- **Evidence:** baseline contains no `storage.buckets`
  inserts or storage policies.
- **Impact:** cannot prove listing uploads are
  restricted to store operators, or that private
  buckets are private, without a live check.
- **Fix:** verify in the Supabase dashboard before
  merchant images go live (checklist in the runbook);
  do not weaken any policy to make a test pass.

### B8. Live backend deployment config not in repo
- **Component:** backend hosting (Vercel project).
- **Evidence:** no Vercel/Render config for the backend
  in the repo, while the live backend runs on Vercel.
- **Impact:** the release cannot be reproduced from
  the repo; a future deploy may diverge silently.
- **Fix:** record the Vercel project's build/start
  settings in the deployment docs (manual step, no
  code change) before release.

## D. Ordered deployment runbook (summary)

Full detail in `release-runbook.md`. Order:
**A** pre-deployment (review, env, staging config,
migration validation, test accounts, Razorpay test
mode) → **B** database (backup check, review, RPC
privileges, approval, apply, verify) → **C** backend
(secrets, deploy, health/readiness, auth, webhook) →
**D** frontend (URLs, Supabase Auth URLs, deploy,
protected routes) → **E** notification activation
(migrations, RPCs, worker credentials, staging worker,
end-to-end notification, reminders, scheduler only
after approval) → **F** controlled smoke tests
(registration, confirmation, recovery, merchant/admin
login, browsing, reservation, test payment, webhook,
notifications, QR pickup, collection, reminders).
No step in this runbook was executed by W8.

## E. Verification (exact commands + results, local)

Backend (from `backend/`, venv `.venv`, requirements-dev
installed):
- `.venv/bin/python -m pytest -q` → **346 passed**
  (340 at PR #21 base + 6 new W8 tests).
- `.venv/bin/ruff check app tests` → clean.
- `.venv/bin/ruff format --check app tests` → clean.
- `.venv/bin/mypy app` → clean (29 files).
- `.venv/bin/pip-audit -r requirements.txt` and
  `-r requirements-dev.txt` → no known vulnerabilities.
- Migration syntax (pglast): W7 files 6/5/12 statements
  OK; W8 files 1/4 statements OK; baseline does NOT
  parse (pre-existing introspection artifact, line 939;
  tracking-only, never applied).
- Docker build: NOT VERIFIED (no Docker in sandbox).

Frontend (repo root, Node 24 / npm 10):
- `npm run test --workspace=apps/web` → **67 passed**.
- `npm run test --workspace=packages/api-client` → **22 passed**.
- `npm run typecheck --workspace=apps/web` → clean.
- `npm run lint --workspace=apps/web` → clean.
- Production build (explicit test env incl. required
  `NEXT_PUBLIC_SITE_URL`) → succeeds.
- Playwright (mocked, stub API + dev server, `CI=1 npx
  playwright test`) → **17 passed (3.4m)**. The dev-server
  image 404 warnings in the log are the known stub
  limitation (the stub does not serve Supabase Storage),
  not test failures.
- Secret scan: source grep for service-role / Razorpay /
  webhook secrets across web + api-client → clean. One
  built-chunk pattern match verified as Supabase client
  library prefix-check code (`startsWith("sb_secret_")`
  in key-type detection), not a secret value.

All above are LOCAL or MOCKED verification. Production
verification claimed in this report is limited to the
read-only public-endpoint evidence dated 2026-11-01 in
§A/§B (backend readiness READY; website production
Ready; Supabase Auth URLs dashboard-verified).

## F. Repository outcome

- Branch: `feature/w8-production-readiness` (from main
  `39896d8`).
- PR: `W8: Production Readiness and Release Preparation`
  → main (link in the final report; PR NOT merged).
- Files changed: 2 new migration files, 2 new backend
  test files, 1 updated backend test, 5 web code/config
  files, 1 Dockerfile, 2 `.env.example` files, 1
  migrations README, 5 new docs files in
  `docs/w8-production-readiness/`.
- CI status: NOT VERIFIED (billing lock; no run
  observed). Local checks above are the verification
  record for this PR.
- Live production resources changed: NONE.

## G. Final go-live decision

**NOT READY FOR PRODUCTION.**

This is not a judgement on code quality — most of the
system is sound and well-tested. It is a judgement on
launch completeness: payments cannot complete their
retry path, notifications cannot run at all, Razorpay is
unconfigured, and two release-critical facts (storage
policies, backend hosting config) are unverified. Fix
B1–B8 in order, prove them in staging with the Phase F
smoke tests, and the next decision can be a controlled
production release.
