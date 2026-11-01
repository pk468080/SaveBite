# SaveBite W8 — Production release runbook

**Status:** plan only. W8 executed NONE of these steps
against production. Each phase gates the next: do not
skip ahead, and do not start Phase E until Phase B is
verified.

**Conventions used below:** every step lists
prerequisites, exact action, expected result,
verification, failure handling, and rollback or
containment. "Approval" always means an explicit
go-ahead from the project owner for that specific step,
not a standing permission.

## Phase A — Pre-deployment

### A1. Review and approve the release code
- **Prerequisites:** W8 PR open; branch
  `feature/w8-production-readiness` reviewed.
- **Action:** review the diff file by file (migrations,
  config, docs, tests). Merge only on explicit owner
  instruction.
- **Expected:** reviewer confirms no secret values, no
  unrelated features, no workflow-file changes smuggled
  in (workflow pushes via API fail with 403 — any CI
  change needs the dashboard/local-git route).
- **Verification:** PR diff + local test record (audit
  §E) re-run on the merge commit.
- **Failure:** any secret or unrelated change → close
  the PR, fix on the branch, re-review.
- **Rollback:** none needed (nothing deployed).

### A2. Verify environment variables (staging first)
- **Prerequisites:** a staging deployment target exists
  (staging project, not production).
- **Action:** set staging values for every variable in
  `backend/.env.example` and `apps/web/.env.example`.
  Backend: `ENVIRONMENT=staging`,
  `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
  `SUPABASE_SERVICE_ROLE_KEY` (server-only),
  `RAZORPAY_KEY_ID` (`rzp_test_`), `RAZORPAY_KEY_SECRET`,
  `RAZORPAY_WEBHOOK_SECRET`, `ALLOWED_ORIGINS`
  (staging website origin, never `*`). Website:
  `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
  `NEXT_PUBLIC_API_BASE_URL` (staging backend),
  `NEXT_PUBLIC_SITE_URL` (staging website origin —
  required since W8; a missing value now fails the
  build loudly instead of falling back to localhost).
- **Expected:** no placeholder values remain; no secret
  in any `NEXT_PUBLIC_*` variable or browser bundle.
- **Verification:** staging build succeeds; readiness
  endpoint (staging) returns ready; homepage loads.
- **Failure:** build fails on a missing variable →
  add it for the correct environment scope and rebuild
  (values bake in at build time — saving alone is
  never enough).
- **Rollback:** revert the variable change; redeploy.

### A3. Validate migrations (no live apply)
- **Prerequisites:** W7 + W8 migration files on the
  release branch.
- **Action:** parse all files (pglast); run
  `backend/tests/test_w7_migrations.py` and
  `test_w8_migrations.py`; review the W8 dedup + grants
  files line by line.
- **Expected:** all parse + consistency tests pass;
  baseline file untouched.
- **Verification:** test output; reviewer sign-off on
  the two W8 files.
- **Failure:** parse/test failure → fix on the branch,
  never by editing a merged W7 file in place.
- **Rollback:** n/a (files only).

### A4. Prepare test accounts
- **Prerequisites:** staging Supabase project.
- **Action:** create staging customer, merchant, and
  admin (operations_admin) accounts through the normal
  sign-up + role-assignment path. Record (privately)
  which account holds which role.
- **Expected:** all three can sign in on staging.
- **Verification:** sign-in on staging for each role.
- **Failure:** role assignment fails → check the
  platform-role mechanism (M11 limitation: only
  operations_admin / super_admin verify through the
  gate); do not weaken the gate.
- **Rollback:** delete staging test accounts.

### A5. Configure Razorpay test mode
- **Prerequisites:** Razorpay dashboard in Test Mode.
- **Action:** create test-mode keys; set them in the
  staging backend env only; create the staging webhook
  for `payment.captured` + `payment.failed` at the
  staging webhook URL.
- **Expected:** test checkout works end to end on
  staging (Phase F).
- **Verification:** a test-mode payment completes and
  the webhook confirms it (staging).
- **Failure:** webhook never arrives → check the
  dashboard webhook URL + events + secret; never test
  with live keys to "see if it works".
- **Rollback:** delete the staging webhook/keys.

## Phase B — Database release

### B1. Confirm backup and recovery plan
- **Prerequisites:** target project identified
  (staging first, production only after staging passes).
- **Action:** confirm from the Supabase dashboard what
  backups/PITR the project plan provides, retention,
  and the restore procedure. Write it into
  `monitoring-recovery-runbook.md` before proceeding.
- **Expected:** a written, project-specific restore
  procedure exists.
- **Verification:** dashboard screenshot/note on file.
- **Failure:** no backup available → STOP. Do not
  apply migrations to a project with no restore path.
- **Rollback:** n/a.

### B2. Review migrations (final)
- **Prerequisites:** B1 done; owner approval to
  proceed.
- **Action:** re-read the five files (3 W7 + 2 W8) in
  timestamp order. Confirm: dedup fix precedes worker
  start; grants file precedes worker start; no baseline
  changes.
- **Expected:** reviewer confirms order + contents.
- **Verification:** file list + reviewer sign-off.
- **Failure:** any doubt → pause and resolve on the
  branch; never edit an applied migration in place.
- **Rollback:** n/a.

### B3. Verify RPC privileges (pre-apply baseline)
- **Prerequisites:** read-only DB access to the target.
- **Action:** record current EXECUTE privileges for
  `backend_process_notification_outbox` and
  `backend_enqueue_pickup_reminders` (they do not exist
  yet pre-apply — record that) and for the existing
  `backend_*` RPCs.
- **Expected:** a written pre-apply privilege snapshot.
- **Verification:** snapshot on file.
- **Failure:** cannot read privileges → pause; do not
  apply blind.
- **Rollback:** n/a.

### B4. Obtain explicit approval, then apply
- **Prerequisites:** B1–B3 done; staging passes
  before production is even considered.
- **Action:** on explicit owner approval, apply the
  five files in timestamp order through the approved
  process (Supabase dashboard SQL editor or linked
  CLI with the owner's token — never `db push` of the
  baseline). Apply W7 + W8 files in one release.
- **Expected:** all five apply without error.
- **Verification:** migration history shows the five
  versions; `select distinct notification_type from
  public.notifications` was checked before applying
  (type CHECK gate).
- **Failure:** any statement fails → STOP. Do not
  re-run a partially applied migration; fix forward
  with a new reviewed file. See the recovery runbook
  ("Failed migration").
- **Rollback:** migrations are one-way by design.
  Containment = stop the release, fix forward, never
  `db reset` on a live project.

### B5. Verify schema and permissions (post-apply)
- **Prerequisites:** B4 applied.
- **Action:** (a) confirm the five objects exist
  (preferences table, outbox columns/indexes,
  triggers, processor + reminder functions);
  (b) run `has_function_privilege` checks for anon /
  authenticated / service_role on both worker RPCs —
  only service_role must hold EXECUTE;
  (c) confirm the dedup key on a test event delivers
  to 2+ recipients (staging test event).
- **Expected:** (a) present, (b) service-role-only,
  (c) one outbox row per recipient.
- **Verification:** query outputs on file.
- **Failure:** any check fails → do not start the
  worker. Fix with a reviewed follow-up migration.
- **Rollback:** fix-forward only (see B4).

## Phase C — Backend release

### C1. Configure backend secrets
- **Prerequisites:** Phase B verified (staging).
- **Action:** set production backend env (same list as
  A2, production values, production website origin in
  `ALLOWED_ORIGINS`, `ENVIRONMENT=production`).
- **Expected:** no placeholder, no `*` origin.
- **Verification:** readiness endpoint returns ready;
  no secret appears in any response body.
- **Failure:** readiness 503 → read which check failed
  (config vs auth vs postgrest) and fix that variable;
  never paste the secret into chat or logs.
- **Rollback:** restore previous env values; redeploy.

### C2. Deploy FastAPI
- **Prerequisites:** C1; merge approved.
- **Action:** deploy through the project's normal
  route (record the Vercel project's build/start
  settings in the deployment docs first — B8: they are
  currently not in the repo).
- **Expected:** new deployment serves traffic.
- **Verification:** `/health` 200; `/v1/health/ready`
  ready (4/4).
- **Failure:** deploy fails → keep the previous
  deployment serving; fix from its logs, never by
  editing production env blindly.
- **Rollback:** redeploy/roll back to the previous
  production deployment.

### C3. Verify authentication + webhook endpoint
- **Prerequisites:** C2 ready.
- **Action:** (a) call an authenticated endpoint with a
  valid token (200) and without one (401);
  (b) POST a bad-signature webhook (expect 401, nothing
  recorded); (c) confirm the Razorpay webhook URL +
  events in the dashboard.
- **Expected:** (a) 200/401 as stated, (b) 401, (c)
  dashboard shows the webhook subscribed.
- **Verification:** response codes + dashboard view.
- **Failure:** auth bypass or webhook accepting bad
  signatures → STOP the release; treat as a security
  incident, not a config tweak.
- **Rollback:** roll back the backend deployment.

## Phase D — Frontend release

### D1. Verify production website URL + Supabase Auth URLs
- **Prerequisites:** Phase C ready.
- **Action:** confirm `NEXT_PUBLIC_SITE_URL` equals the
  production website origin for All Environments;
  confirm Supabase Auth Site URL + redirect allow-list
  equal the same origin (dashboard check).
- **Expected:** all three match the production origin;
  no localhost anywhere.
- **Verification:** dashboard values + a fresh build
  (values bake in at build time).
- **Failure:** mismatch → fix the setting, redeploy,
  re-verify. Never ship a build made before the fix.
- **Rollback:** redeploy the previous production build.

### D2. Deploy customer, merchant, and admin pages
- **Prerequisites:** D1.
- **Action:** deploy the website from the release
  branch (after merge) through the normal route.
- **Expected:** production deployment Ready.
- **Verification:** homepage, marketplace, sign-up,
  sign-in load; `/admin` redirects unauthenticated
  users to sign-in.
- **Failure:** build fails (e.g. missing env) → fix
  the variable scope and redeploy; do not ship a
  partial build.
- **Rollback:** redeploy the previous production build.

### D3. Verify protected routes
- **Prerequisites:** D2 Ready.
- **Action:** as an unauthenticated user, open
  `/customer`, `/merchant`, `/admin` (expect sign-in
  redirect); as a customer, open `/admin` (expect
  denial, never admin data).
- **Expected:** redirects/denials as stated, no data
  leak.
- **Verification:** browser checks, recorded.
- **Failure:** any protected data visible → STOP;
  treat as a security incident.
- **Rollback:** redeploy the previous production build.

## Phase E — Notification activation

### E1. Confirm migrations + RPC permissions
- **Prerequisites:** Phase B verified (production).
- **Action:** re-run the B5 checks against production.
- **Expected:** service-role-only EXECUTE; per-recipient
  dedup confirmed.
- **Verification:** query outputs on file.
- **Failure:** any check fails → do not start the
  worker. Period.
- **Rollback:** n/a (worker not started yet).

### E2. Configure worker credentials + deploy to staging
- **Prerequisites:** E1 (staging).
- **Action:** set worker env server-side only
  (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`);
  deploy the worker to staging per
  `worker-deployment-plan.md` (long-running process
  preferred; `--once` cron every 15 min acceptable).
- **Expected:** worker starts, exits 0 on `--once`
  (or polls cleanly in loop mode), logs counts only.
- **Verification:** worker logs + outbox rows moving
  pending → sent on a staging event.
- **Failure:** RPC errors → check grants (B5) and
  service key; exit 2 means startup failure (missing
  key), exit 1 means RPC failure.
- **Rollback:** stop the staging worker.

### E3. Verify one notification end to end + reminders
- **Prerequisites:** E2 running on staging.
- **Action:** trigger a staging paid order; confirm
  the customer notification appears and the merchant
  notification appears (2+ recipients where
  applicable); create a staging order entering its
  reminder window and confirm a reminder is enqueued
  and delivered.
- **Expected:** all notifications visible to the right
  users only; reminder fires once.
- **Verification:** staging UI + outbox/notification
  rows.
- **Failure:** missing or duplicated notifications →
  inspect outbox rows (`pending`/`failed`/`sent`) and
  processor counts; do not retry by re-firing events.
- **Rollback:** stop the worker; notifications already
  delivered cannot be recalled (note it in the incident
  log).

### E4. Production scheduler — only after approval
- **Prerequisites:** E3 passes on staging; owner
  approval for production worker start.
- **Action:** deploy the worker to production with the
  same configuration; configure the scheduler
  (long-running preferred).
- **Expected:** production outbox drains; no dead
  letters in the first 24h.
- **Verification:** production outbox counts +
  alerting (see monitoring runbook).
- **Failure:** dead letters or stuck `processing` rows
  → follow the worker-outage runbook; stop the worker
  if it is mis-delivering.
- **Rollback:** stop the production worker/scheduler.

## Phase F — Controlled smoke tests

Run in order on staging first, then production (after
E4). Each test: record pass/fail + evidence. Any
failure stops the release at that test.

1. **Customer registration + login** — sign up, confirm
   email (link lands on the production domain), sign in.
2. **Email confirmation** — confirmation activates the
   account; a second click does not error confusingly.
3. **Password recovery** — reset link lands on the
   production domain; reset works; old password stops
   working.
4. **Merchant login** — merchant signs in, sees own
   stores/orders only.
5. **Authorized admin login** — operations_admin signs
   in, sees the admin portal; a plain customer opening
   `/admin` is denied.
6. **Marketplace browsing** — listings load; empty
   state (no listings) renders honestly.
7. **Reservation** — reserve → `pending_payment`,
   inventory reserved, ~5-minute expiry visible.
8. **Razorpay test payment** — test-mode checkout
   completes; verify confirms; order becomes
   `confirmed`/`ready_for_pickup` as appropriate.
9. **Webhook confirmation** — dashboard shows the
   webhook delivered; a duplicate delivery changes
   nothing.
10. **Customer notification** — paid-order notification
    visible to the customer only.
11. **Merchant notification** — paid-order notification
    visible to merchant staff only.
12. **Customer pickup QR** — QR issues for a
    confirmed/ready order; token never shown as text
    in logs or URLs.
13. **Merchant pickup verification** — merchant verifies
    the QR inside the pickup window; order becomes
    `collected`.
14. **Order collection state** — collected order shows
    collected everywhere (customer + merchant).
15. **Pickup reminder eligibility** — an order entering
    its reminder window gets exactly one reminder.

**Release sign-off:** all Phase F tests pass on staging
AND production (where production-applicable), B5 + E1
checks are on file, and the owner has approved the
go-live. Until then, the decision remains NOT READY
FOR PRODUCTION.
