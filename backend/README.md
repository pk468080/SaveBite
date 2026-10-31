# SaveBite API — FastAPI foundation (Milestone 2)

Modular FastAPI monolith for the SaveBite surplus-food marketplace.
Milestone 2 is foundation only: configuration, authentication,
authorisation, error handling, structured logging, health/readiness,
and tests. No business routes, no Razorpay integration, and no
database schema changes are included here.

See `../docs/architecture.md` for the full architecture, integration
boundaries, and security rules.

## Quick start (local, no secrets required for health)

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Then:

- Liveness: `curl http://127.0.0.1:8000/health`
- Readiness: `curl http://127.0.0.1:8000/v1/health/ready`
  (returns 503 until Supabase is configured and reachable — that is
  correct behaviour, not a bug)
- Interactive docs: http://127.0.0.1:8000/docs

## Environment variables

Copy these into a local `.env` file (never commit `.env`):

```sh
ENVIRONMENT=development
LOG_LEVEL=INFO
SUPABASE_URL=https://zehnhqcfawagxbactvne.supabase.co
SUPABASE_PUBLISHABLE_KEY=<your publishable key from Supabase Settings>
# Server-only, deployment secrets only — never in browser code:
# SUPABASE_SERVICE_ROLE_KEY=<server-only>
# RAZORPAY_WEBHOOK_SECRET=<server-only, required only from Milestone 6>
# ALLOWED_ORIGINS=https://app.example.com
```

Rules:

- The publishable key is the only Supabase key client code may use.
- The service-role key must never be exposed to Expo / Next.js
  browser code, never logged, and never committed. If it is missing,
  service-role operations fail closed (503) instead of silently
  downgrading.
- The Razorpay webhook secret must be configured before any webhook
  is accepted; without it, verification raises instead of passing.
- Never paste a secret in chat. The owner copies keys from Supabase
  Settings into deployment secrets.

## Supabase CLI linking (developer step)

The repository's `supabase/config.toml` records the project ref
(`zehnhqcfawagxbactvne`) but contains no token. To link locally:

```sh
supabase link --project-ref zehnhqcfawagxbactvne
```

Use your own Supabase access token. After linking, verify the remote
migration history still shows the 15 entries in
`../supabase/migrations/README.md` before pushing any new migration.
Never run `supabase db reset`, `supabase db push` against live, DROP,
or destructive DDL without a written change plan and explicit approval.

## Tests and static checks

```sh
cd backend
pytest -q
ruff check app tests
mypy app
```

Tests use fakes at the Auth / PostgREST boundary and never hit the
live Supabase project or use a real secret. A live end-to-end test
against `zehnhqcfawagxbactvne` remains a developer step, because no
Supabase access token or DB password is available in this environment.

## Docker

```sh
cd backend
docker build -t savebite-api:0.1.0 .
docker run --rm -p 8000:8000 \
  -e SUPABASE_URL=https://zehnhqcfawagxbactvne.supabase.co \
  -e SUPABASE_PUBLISHABLE_KEY=<publishable key> \
  savebite-api:0.1.0
```

The image runs as a non-root user, exposes port 8000, and health-checks
`GET /health`. Secrets are passed at run time only, never baked in.

## What is deliberately NOT in Milestone 2

- No merchant, listing, order, payment, pickup, refund, or admin routes.
- No Razorpay integration and no real payments; only the HMAC-SHA256
  webhook signature verification primitive in `app/security.py`,
  unit-tested, for Milestone 6 to use first.
- No delivery workflow — MVP is customer pickup only.
- No direct PostgreSQL connection; all DB access is via Supabase HTTP
  APIs so RLS and the Milestone 1 RPC contracts remain enforced.
- No private-schema access via PostgREST; private data is reached
  only through public `backend_*` RPC wrappers, from server-only code.
