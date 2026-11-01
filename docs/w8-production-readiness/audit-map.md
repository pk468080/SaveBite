# SaveBite W8 — Audit map

**Scope:** production-readiness audit of SaveBite at main `39896d8`
(PR #21 merge; PRs #19, #20, #21 all merged). Branch:
`feature/w8-production-readiness`. Preparation only: this
milestone changes no live production resource.

**Method:** repo-file audit (four parallel read-only areas:
backend, payments + worker, frontend + storage,
database + security + CI/CD) plus read-only public-endpoint
evidence already verified on 2026-11-01 (backend readiness
READY 4/4; website production Ready on main `39896d8`;
`NEXT_PUBLIC_SITE_URL` set for All Environments;
Supabase Site URL + redirect URL both production).
Everything else about live services is NOT VERIFIED.

**Environment limits (honest):** no Postgres binaries in the
sandbox, so migration replay was impossible — migrations
were validated by pglast parsing + consistency checks
only. No Docker/Podman, so Docker builds were not verified
locally. GitHub Actions has an account-wide billing lock
(account issue, not a code defect), so no CI run is claimed
green. Nothing below describes a mocked or local test as
production verification.

## Verdicts at a glance

| Service | Verdict | One-line reason |
|---|---|---|
| Frontend (Next.js / Vercel) | WARNING | Sound code; silent localhost fallback fixed in W8; storage policies + callback gap still open |
| FastAPI backend | WARNING | Strong fail-closed code; live Vercel deployment config not in repo; docs-in-prod + `$PORT` fixed in W8 |
| Supabase DB + migrations | BLOCKER | W7 dedup drops multi-recipient events (fixed in a W8 file, not applied); RPC grants missing (fixed in a W8 file, not applied); W7 files unapplied |
| Authentication / authorization | PASS | Supabase Auth verification, RBAC, RLS, client separation all sound in code |
| Razorpay | BLOCKER | Code mostly sound, but checkout retry returns 422 after a successful attach; keys + webhook not configured |
| Notification worker | BLOCKER | Worker code sound; no worker/scheduler deployed; migrations unapplied |
| Scheduler | BLOCKER | No scheduler exists; release-expiry job also has no caller |
| Storage | WARNING | Upload mechanics sound; bucket policies not verifiable from repo; no image-removal path |
| CI/CD | WARNING | Backend + Docker jobs only; no web or migration-replay jobs; billing lock blocks runs |
| Monitoring / backups | WARNING | Logs + health endpoints exist; no alerting; backups NOT VERIFIED |

## Overall go-live decision

**NOT READY FOR PRODUCTION.** See
`production-readiness-audit.md` §C for the blocker list
with evidence, impact, and fixes. The recommended next
step is a staging deployment (test-mode Razorpay, W7 + W8
migration files applied to a staging project) once the
checkout-retry fix lands — staging is the path to
production, not a substitute for the blockers.

## What W8 changed (code, all on this branch)

1. `supabase/migrations/20261101130000_w8_notification_dedup_per_recipient.sql`
   — per-recipient dedup keys (fixes the multi-recipient drop).
2. `supabase/migrations/20261101131000_w8_notification_rpc_grants.sql`
   — service-role-only EXECUTE on both W7 worker RPCs.
3. `apps/web/lib/config.ts` — `NEXT_PUBLIC_SITE_URL` is now
   required and fails loudly; added to `configProblems()`.
4. `apps/web/tests/config.test.ts` — SITE_URL in the required list.
5. `apps/web/app/sitemap.ts` — auth routes removed (robots
   already disallows them).
6. `apps/web/next.config.ts` — minimal security headers
   (nosniff, frame DENY, referrer policy, HSTS; CSP deferred).
7. `backend/app/main.py` — interactive API docs disabled
   when `ENVIRONMENT=production`.
8. `backend/tests/test_w8_production_config.py` — docs tests.
9. `backend/tests/test_w8_migrations.py` — W8 migration tests.
10. `backend/tests/test_schema_contract.py` — migration pin extended.
11. `backend/Dockerfile` — honours `$PORT` (default 8000).
12. `backend/.env.example`, `apps/web/.env.example`,
    `supabase/migrations/README.md` — production warnings
    and the W7 + W8 apply list.

## What W8 deliberately did NOT change

- No live production resource (no deploy, migration apply,
  SQL, RLS, secret, env, DNS, storage, or worker change).
- No `.github/workflows/*` change (API push of workflow
  files fails with 403; the recommended CI jobs are
  documented in the audit instead).
- No payment-path SQL surgery for the checkout-retry
  blocker (needs a Postgres replay to verify; the exact
  fix is specified in the audit for a reviewed follow-up).
- No `/auth/callback` route, no rate limiter, no CSP:
  each is documented as a follow-up with its rationale.
- No architecture rewrite, no new product feature.

## Documents in this directory

- `production-readiness-audit.md` — full audit (§A–§G).
- `release-runbook.md` — sequential Phases A–F.
- `monitoring-recovery-runbook.md` — detection, recovery,
  escalation, backups.
- `worker-deployment-plan.md` — worker + scheduler plan
  (deployment itself is NOT done in W8).
