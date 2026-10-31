# SaveBite API — FastAPI foundation (Milestone 2) + Merchant
Onboarding & Store Setup (Milestone 3)

Modular FastAPI monolith for the SaveBite surplus-food marketplace.
Milestone 2 provided configuration, authentication, authorisation,
error handling, structured logging, health/readiness, and tests.
Milestone 3 adds merchant onboarding and store management routes
(see below). No Razorpay integration, no listings, no ordering, and
no database schema changes are included here.

See `../docs/architecture.md` for the full architecture, integration
boundaries, and security rules.

## Milestone 3 routes

All routes require a Supabase Auth Bearer token (see
`GET /v1/me` in Milestone 2). All use the user-context Supabase
client and user-context RPCs; the service-role client is never used
for these operations. Roles come from `merchant_memberships` and
`store_staff_memberships`, never from the request body.

| Method | Route | Who can call it | Success |
| --- | --- | --- | --- |
| POST | `/v1/merchants/applications` | Any authenticated user | 201, created merchant |
| GET | `/v1/merchants` | Authenticated user | 200, only their active memberships' merchants |
| GET | `/v1/merchants/{merchant_id}` | Any active merchant member | 200 |
| POST | `/v1/merchants/{merchant_id}/stores` | Merchant owner or admin | 201, created store (status `draft`) |
| GET | `/v1/merchants/{merchant_id}/stores` | Any active merchant member | 200 |
| GET | `/v1/stores/{store_id}/hours` | Merchant owner/admin, or store_manager with an active merchant membership | 200 |
| PUT | `/v1/stores/{store_id}/hours` | Same as GET hours | 200, `processed` = entries upserted |

Store-hours authorisation mirrors
`private.can_manage_store(store_id, ['store_manager'])`: owners and
admins are allowed even with no store-staff row, and a
store_manager is allowed only with an active merchant membership
as well. Do not rely on store-staff memberships alone, or owners
would be blocked.

### Examples

Submit a merchant application (email/phone are optional in the
database and in this API; when supplied they must be a valid email
and an Indian mobile number):

```sh
curl -X POST http://127.0.0.1:8000/v1/merchants/applications \
  -H "Authorization: Bearer <supabase-user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "legal_name": "Sharma Foods Pvt Ltd",
    "display_name": "Sharma Foods",
    "business_type": "restaurant",
    "business_email": "hello@sharma.example.com",
    "business_phone": "9876543210"
  }'
# 201 {"id": "<merchant-uuid>", "status": "pending_review",
#      "verification_status": "pending", ...}
```

Create a store (owner/admin only; PIN code must be six digits
starting 1-9; latitude and longitude must both be present or both
absent; slug is lowercased):

```sh
curl -X POST http://127.0.0.1:8000/v1/merchants/<merchant-uuid>/stores \
  -H "Authorization: Bearer <supabase-user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sharma Foods Dwarka",
    "slug": "sharma-foods-dwarka",
    "address_line_1": "Shop 12, Sector 7 Market",
    "city": "New Delhi", "state": "Delhi", "pincode": "110075",
    "latitude": 28.5921, "longitude": 77.0460
  }'
# 201 {"id": "<store-uuid>", "status": "draft", "country_code": "IN",
#      "timezone": "Asia/Kolkata", ...}
```

Set weekly hours (weekdays 0-6, one entry per weekday, max 7;
closed days must have no times; open days need opens_at before
closes_at):

```sh
curl -X PUT http://127.0.0.1:8000/v1/stores/<store-uuid>/hours \
  -H "Authorization: Bearer <supabase-user-jwt>" \
  -H "Content-Type: application/json" \
  -d '{"hours": [
    {"weekday": 0, "opens_at": "09:00", "closes_at": "21:00"},
    {"weekday": 6, "is_closed": true}
  ]}'
# 200 {"store_id": "<store-uuid>", "processed": 2, "hours": [...]}
```

Errors use the standard envelope
`{"error": {"code": "...", "message": "...", "request_id": "..."}}`:
401 unauthenticated, 403 non-member / wrong role, 404 store or
merchant not visible to the caller, 422 validation (including
database validation errors such as `business_name_required`,
mapped from the PostgREST error code), 502 upstream failure.

### Known limitations and deferred workflows (Milestone 3)

- Merchant approval, document verification, and store activation
  are NOT implemented: new merchants stay `pending_review` and new
  stores stay `draft` until a later, approved workflow changes them.
- No listings, inventory, ordering, reservations, payments,
  pickup verification, refunds, or delivery.
- No new tables, columns, functions, policies, or migrations.
- Store responses do not include the `location` geography field:
  the database stores it as geography, not latitude/longitude
  columns, and this milestone does not invent a conversion for it.
- Business email and phone are optional (matching the database
  RPC defaults), not required, even though a real onboarding flow
  will usually collect them.
- The API does not expose approved merchants publicly: listing
  and detail routes return only the caller's own memberships, even
  though the database RLS also allows approved-merchant reads.

### Local testing

```sh
cd backend
pytest -q tests/test_merchants.py   # Milestone 3 only
pytest -q                           # full suite
```

Milestone 3 tests use fakes and dependency overrides only; they
never touch live Supabase and never use a real secret.

## Quick start (local, no secrets required for health)

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
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
ruff format --check app tests
mypy app
pip-audit -r requirements.txt
pip-audit -r requirements-dev.txt
```

Dependency versions are fully pinned in `requirements.txt`
(runtime), `requirements-dev.txt` (test/audit tools), and
`requirements-lock.txt` (full resolved set, generated with
`pip freeze` after installing the pinned files). Do not pin Starlette
independently: FastAPI's own requirement resolves it, and the resolved
version is recorded in the lock file.

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

The Dockerfile has no `|| true`: if `pip install` fails, the build
fails. GitHub Actions (`.github/workflows/ci.yml`) also builds the
image and smoke-tests `GET /health` on every pull request to main.

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
