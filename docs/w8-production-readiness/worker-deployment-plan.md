# SaveBite W8 — Notification worker deployment plan

**Status:** plan only. W8 deploys NO worker and NO
scheduler. Deployment happens only after the release
runbook Phase B (migrations + RPC privileges) is
verified and the owner approves the worker start.

## 1. What the worker is

`python -m app.notification_worker` (run from `backend/`).
Each pass: (1) enqueue pickup reminders via
`backend_enqueue_pickup_reminders`, then (2) process one
outbox batch via `backend_process_notification_outbox`.
It delivers in-app notifications only (no email, SMS,
WhatsApp, or push in W7).

```
python -m app.notification_worker [--once] [--interval-seconds 60] [--batch-size 50] [--window-minutes 60] [--worker-id NAME]
```

## 2. Deployment options (pick one)

### Option A (recommended): long-running process
- Host: Render Background Worker (or equivalent
  always-on process host).
- Command: `python -m app.notification_worker`
  (defaults: 60s interval, batch 50, window 60 min).
- Pros: drains backlogs continuously; a failed pass is
  logged and retried next interval without killing the
  worker; SIGINT/SIGTERM shut down gracefully after
  the current pass.
- Cons: an always-on process to pay for / keep alive
  (host-dependent; confirm cost before choosing).

### Option B: scheduled `--once` runs
- Host: any cron/scheduler (Render cron, or equivalent).
- Command: `python -m app.notification_worker --once`
  every 15 minutes (every 5 minutes under burst load).
- Pros: no always-on process; simple to reason about.
- Cons: one batch per run — a backlog above 50 per
  run drains slowly, so interval must shrink as volume
  grows; a reminder-RPC failure fails the whole pass
  (exit 1) and stalls delivery until the next run.

Either option is safe for concurrent workers: claiming
uses `FOR UPDATE SKIP LOCKED`, dedup inserts prevent
double-visible delivery, and claims expire after
10 minutes (a batch running longer than 10 minutes
could theoretically be reclaimed, but the dedup insert
still prevents a duplicate visible notification).

## 3. Environment (server-side only)

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (server-only; never in
  browser code, never in logs, never in chat)
- The worker docstring also lists
  `SUPABASE_PUBLISHABLE_KEY`, but the service-role
  client path does not use it — set it only if the
  host requires a complete env set.
- Without the service key, the worker fails closed at
  startup (exit 2). No worker run should ever use a
  user token or the publishable key alone.

## 4. Activation prerequisites (all mandatory, in order)

1. W7 + W8 migration files applied in timestamp order
   (runbook Phase B), including the per-recipient
   dedup fix.
2. RPC privileges verified: only `service_role` holds
   EXECUTE on `backend_process_notification_outbox`
   and `backend_enqueue_pickup_reminders`
   (`has_function_privilege` for anon / authenticated /
   service_role on file).
3. Server-side service-role configuration present.
4. Staging worker passes one full end-to-end test
   (paid order → customer + merchant notifications;
   reminder window → exactly one reminder).
5. Monitoring from `monitoring-recovery-runbook.md`
   §1 in place (backlog, dead-letter, stuck-row,
   worker-heartbeat alerts).

## 5. Failure handling (built into the worker)

| Situation | Behaviour | Operator action |
|---|---|---|
| Per-job exception | Retried with backoff ~1/2/4/8 min, capped in practice by the 5-attempt ceiling | None, unless it dead-letters |
| 5th failure | `status='failed'` (dead-letter, never reclaimed) | Investigate the payload; fix the cause; re-enqueue only via a reviewed path |
| Preference disabled | `status='cancelled'`, `last_error='preference_disabled'` | None (user choice); a later re-enable can still deliver a fresh reminder |
| Mandatory categories | `payment_updates`, `operational_alerts` always delivered | None |
| Stale claim (>10 min `processing`) | Reclaimed by the next pass | Check for crashed workers if frequent |
| `--once` with dead letters | Exits 0 anyway | Scheduler MUST parse stdout JSON and alert on `dead > 0` / `skipped > 0` |
| Reminder-RPC failure | Whole pass fails (exit 1 in `--once`; logged + retried in loop mode) | Fix the reminder RPC; delivery waits for the next pass |
| Host clock skew | Reminder window edges shift (worker sends its own `p_now`) | Prefer a host with NTP; long-term fix: default the RPC to DB `now()` |
| Negative `--window-minutes` | Silently enqueues nothing (no validation) | Never pass a negative window; validate ranges in the scheduler wrapper |

## 6. Sizing guidance

- Defaults (60s interval, batch 50, window 60 min)
  suit pilot volume.
- If `--once` cron is chosen: 15-minute cadence at
  pilot volume; shorten it if the pending backlog
  regularly exceeds one batch.
- Server clamps batch to 1–200; do not set a client
  batch above 200 (it will be clamped silently).
- Reminder window (60 min) vs cadence: a 15-minute
  cadence inside a 60-minute window gives ~4 chances
  to enqueue each reminder — comfortable margin.

## 7. Smoke test (staging, before production start)

1. Start the staging worker.
2. Create a staging paid order → confirm the customer
   notification and the merchant notification appear,
   each exactly once, to the right users only.
3. Create a staging order entering its reminder window
   → confirm exactly one reminder is enqueued and
   delivered.
4. Kill the worker mid-batch (staging only) → restart
   → confirm no duplicate visible notifications and
   the batch drains.
5. Confirm worker logs contain counts + worker id only
   (no titles, bodies, user ids, tokens, or keys).

## 8. Related scheduler gap (separate from this worker)

`backend_release_expired_reservations` has no caller
today, so abandoned `pending_payment` orders do not
auto-expire. When a scheduler exists for the
notification worker, schedule the release job on the
same host (separate cadence, e.g. every 15 minutes)
and verify expired reservations actually release.
Until then, the payment page's "expired" outcome is a
promise without a mechanism — say so in any launch
communication.
