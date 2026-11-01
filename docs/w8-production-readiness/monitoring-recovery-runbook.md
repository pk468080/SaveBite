# SaveBite W8 — Monitoring, backup, and recovery runbook

**Status:** requirements + procedures. W8 implements none
of the monitoring or backup tooling below — it documents
what must exist before launch and how to respond when
something breaks. Nothing here claims a backup exists or
a restore was tested: neither is evidenced in the repo.

## 1. What must be monitored before launch

| Signal | Why it matters | How to detect (minimum) |
|---|---|---|
| API uptime + `/v1/health/ready` | Backend down = no orders | Uptime check every 1–5 min on `/health` and `/v1/health/ready`, alert on non-200 / not-ready |
| API error rate (5xx) | Silent breakage | Log-based alert on 5xx rate spike |
| Supabase connectivity | Auth + data depend on it | Readiness check covers config/auth/PostgREST; alert on readiness failure |
| Payment webhook failures | Unconfirmed paid orders | Razorpay dashboard delivery failures + backend webhook-error logs |
| `reconciliation_required` orders | Money stuck in limbo | Daily query + alert on any new row (no admin UI exists today — see below) |
| Outbox backlog | Notifications not delivering | Query: `pending` rows older than 15 min; alert on growth |
| Dead-letter outbox rows | Permanently failed jobs | Query: `status='failed'`; alert on any new row |
| Stuck `processing` rows | Crashed worker mid-batch | Query: `status='processing'` with `claimed_at` older than 30 min (claim expiry is 10 min, so 30 min means stuck) |
| Worker availability | No worker = no delivery | Worker process heartbeat / `--once` cron success + log presence |
| Storage upload failures | Merchants cannot publish | Merchant-reported + upload-error logs |
| Frontend errors | Broken pages | Vercel deployment status + browser error reports (none wired today — at minimum, check deployments) |
| Duplicate payment events | Double-confirm risk | Webhook dedup is code-enforced; alert on duplicate `gateway_event_id` replays that change state (should be none) |

**Admin visibility gap (must be closed before the first
live charge):** today, `reconciliation_required` orders,
dead-letter outbox rows, and unresolvable webhook events
are visible only by direct DB access, and the admin API
deliberately excludes private webhook events. Until an
admin surface or a documented dashboard query exists,
assign one person to run the three queries above daily.

## 2. Backups and recovery (honest status)

- **Repo evidence:** none. No backup/restore docs,
  retention statement, PITR statement, or restore test
  exists in `docs/`, `README.md`, `backend/README.md`,
  or `apps/web/README.md`.
- **Required before launch:** confirm from the Supabase
  dashboard (project plan) what backups/PITR are
  available, retention, and the exact restore procedure;
  write it here; perform one restore test to a
  disposable project and record the result. Do not
  launch on a project with no restore path.
- **Migration safety rule:** migrations are one-way.
  There is no `db reset` on a live project, ever. A
  failed migration is fixed forward with a new reviewed
  file (see §3, "Failed migration").

## 3. Incident runbooks

### API outage
- **Detect:** uptime check fails; readiness not ready.
- **Inspect:** deployment status (Vercel); readiness
  body (which check failed: config / auth / postgrest);
  recent deployment + env changes.
- **Contain:** roll back to the previous deployment.
- **Recover:** fix the failing check (usually a missing
  or wrong env value); redeploy; re-verify readiness.
- **Escalate:** if Supabase itself is down, there is no
  app-side fix — post a status notice and wait for the
  platform; do not restart things blindly.

### Supabase connectivity outage
- **Detect:** readiness auth/postgrest checks fail;
  Auth errors spike.
- **Inspect:** Supabase status; project health;
  readiness body.
- **Contain:** API stays up (liveness is independent)
  but returns 503 on data paths — that is the designed
  fail-closed behaviour, not a bug to work around.
- **Recover:** restore connectivity (keys, project
  status); re-verify readiness.
- **Escalate:** platform outage → status notice.

### Authentication outage
- **Detect:** sign-in/sign-up failures spike;
  `/auth/v1/user` errors.
- **Inspect:** Supabase Auth status; Site URL +
  redirect allow-list (a localhost regression breaks
  confirmation/reset links — the 2026-11-01 incident
  class); `NEXT_PUBLIC_*` values in the live build.
- **Contain:** if links point to the wrong domain, fix
  the setting and redeploy; do not disable email
  confirmation to "unblock" users.
- **Recover:** re-verify with a test sign-up +
  confirmation + sign-in.
- **Escalate:** Supabase Auth platform issue → status
  notice.

### Payment webhook failure
- **Detect:** Razorpay dashboard delivery failures;
  paid orders stuck in `pending_payment`.
- **Inspect:** webhook URL + events + secret in the
  dashboard; backend webhook logs (signature failures
  return 401 by design — a 401 storm means a wrong
  secret, not an attack to ignore).
- **Contain:** do not manually mark orders paid.
  Ever. A manual confirm bypasses the provider check.
- **Recover:** fix URL/secret; Razorpay retries
  delivery; verify each order via the provider fetch
  path (`/v1/payments/verify` flow), not by editing
  rows.
- **Escalate:** money-affecting discrepancy →
  owner + finance review before any row is touched.

### Payment reconciliation issue
- **Detect:** `reconciliation_required` order appears.
- **Inspect:** the order, its payment transaction, and
  the Razorpay dashboard record (amount, status,
  currency). Never trust a frontend report alone.
- **Contain:** leave the order in reconciliation;
  tell the customer honestly ("needs verification")
  and promise no refund until verified.
- **Recover:** resolve via the provider record; if
  captured correctly, confirm through the normal
  verify path; if not captured, follow the refund
  path. Record the resolution.
- **Escalate:** any amount mismatch → owner review.

### Notification worker outage
- **Detect:** outbox backlog grows; dead letters
  appear; worker logs stop.
- **Inspect:** worker process/cron status; last
  `--once` exit code and stdout JSON counts
  (`dead`/`skipped` matter — exit 0 does not mean
  zero dead letters); RPC grant checks (B5).
- **Contain:** stop a mis-delivering worker. A stopped
  worker means delayed notifications, not lost ones:
  pending rows wait for the next run (deduplicated).
- **Recover:** fix the cause (grants, key, DB
  connectivity); restart; watch one full pass drain
  the backlog; confirm no duplicate visible
  notifications (dedup should prevent them).
- **Escalate:** backlog older than 24h → owner
  decision on a catch-up announcement.

### Outbox backlog (worker running, backlog growing)
- **Detect:** pending count rising across runs.
- **Inspect:** batch size vs arrival rate (`--once`
  drains one batch per run; loop mode drains
  continuously). A backlog above 50 per 15-minute cron
  run means the cron interval is too long.
- **Contain:** shorten the interval or switch to loop
  mode; do not raise the batch above the server clamp
  (200) blindly.
- **Recover:** drain + confirm delivery counts match
  notifications created.
- **Escalate:** sustained growth → scale the worker
  (still one logical consumer is fine — claiming is
  `SKIP LOCKED` safe for concurrent workers).

### Failed database migration
- **Detect:** apply step errors; migration history
  incomplete.
- **Inspect:** which statement failed and whether
  earlier statements in the same file committed
  (Supabase applies files transactionally per file
  only if wrapped — check the actual state, do not
  assume).
- **Contain:** STOP. Do not re-run the file. Do not
  `db reset`. Do not hand-edit live objects to "make
  it match".
- **Recover:** fix forward with a new reviewed
  migration file that brings the schema to the intended
  state from the actual state; re-verify with the
  Phase B checks.
- **Escalate:** any production data at risk → owner
  + restore-from-backup decision (see §2).

### Duplicate payment event
- **Detect:** same `gateway_event_id` delivered twice
  (normal) — or a state change on replay (abnormal).
- **Inspect:** webhook event rows; order/payment
  status history.
- **Contain:** dedup is code-enforced (record-then-act,
  unique event id, idempotent confirm). A replay that
  changes state is a bug, not a retry to accept.
- **Recover:** if state was wrongly changed, restore
  via the provider record + owner review; never edit
  payment rows directly without that review.
- **Escalate:** any money movement → owner + finance.

### Storage upload failure
- **Detect:** merchant reports upload errors; upload
  error logs.
- **Inspect:** bucket policies (dashboard), file type/
  size, path convention, backend `addImage`
  authorisation.
- **Contain:** if uploads succeed but registration
  fails, orphan files stay public with no DB row —
  note them for cleanup; do not delete bucket objects
  blindly (a live listing may reference the path).
- **Recover:** fix the failing layer (policy vs API);
  re-upload; confirm the listing renders the image.
- **Escalate:** inappropriate published image → use
  the (to-be-built) removal path; until it exists,
  removal is a dashboard action by the owner only.

### Frontend deployment failure
- **Detect:** Vercel deployment Error; homepage or
  auth pages broken.
- **Inspect:** build log (most common: a missing
  `NEXT_PUBLIC_*` variable for that environment —
  values bake in at build time).
- **Contain:** keep the previous production deployment
  serving; never ship a partial build.
- **Recover:** fix the variable scope, redeploy,
  re-verify homepage + sign-up + sign-in + admin
  redirect.
- **Escalate:** auth pages broken in production →
  treat as an authentication outage (§3 above).
