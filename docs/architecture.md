# SaveBite — FastAPI architecture (Milestone 2)

## Goal

A modular FastAPI monolith that is the single backend for the future
customer app, merchant portal and admin portal. Milestone 2 is foundation
only: configuration, authentication, authorisation, error handling,
logging, health/readiness, and test infrastructure. No business routes
(merchant onboarding, discovery, checkout, pickup, refunds, admin) are
built here; those are Milestones 3–9, each on top of this foundation.

## Source of truth reviewed before implementation

- Milestone 1 commit `9a30e95` on main: `supabase/migrations/README.md`
  (15 remote migrations) and the consolidated baseline
  `20261031060000_remote_schema_baseline.sql`.
- Live schema at that inspection: 41 tables (25 public + 16 private),
  16 enum types, 204 constraints, 41 RLS policies, 45 functions,
  12 triggers. Public RLS is on for all 25 public tables; private RLS
  is off because private is service-role-only and must not be exposed
  through PostgREST.
- Unified listing contract: `public.listings.listing_type` is
  `surprise_bag` or `individual_item`. No separate order/payment
  systems for the two types.
- User-context RPCs (public wrappers, JWT required):
  `apply_merchant_application`, `create_merchant_store`,
  `upsert_store_hours`, `create_order_reservation`,
  `begin_payment_checkout`, `issue_pickup_token`, `verify_pickup_token`,
  `request_refund`.
- Server-only RPCs (public `backend_*` wrappers over private
  implementations): `backend_attach_gateway_order`,
  `backend_mark_payment_failed`, `backend_confirm_payment_capture`,
  `backend_record_payment_webhook_event`,
  `backend_release_expired_reservations`, `backend_review_merchant`,
  `backend_review_store`, `backend_update_refund_status`,
  `backend_post_ledger_transaction`, `backend_reverse_ledger_transaction`.
- Money is NUMERIC in the database; pickup is customer-only (no
  delivery in MVP); a reservation hold currently expires after five
  minutes (database rule, not re-implemented in app code).

## File structure

```
backend/
  README.md                 Local development, Docker, testing, secrets
  Dockerfile                Python 3.12 slim, non-root, uvicorn
  .dockerignore
  pyproject.toml            Dependencies, pytest and ruff config
  requirements.txt          Pinned runtime + test dependencies
  app/
    __init__.py
    main.py                 App factory, middleware, error handlers, routers
    config.py               Settings from environment, secret validation
    logging_config.py       Structured JSON logging + request-id context
    errors.py               ApiError + standard error envelope + handlers
    schemas.py              Pydantic v2 schemas + enums mirroring the DB
    auth.py                 Bearer token -> Supabase Auth user resolution
    supabase_client.py      User-context and service-role REST clients
    dependencies.py         FastAPI dependencies (user, clients)
    rbac.py                 Platform / merchant / store role checks
    security.py             Razorpay webhook signature + idempotency helpers
    routers/
      __init__.py
      health.py             GET /health, GET /v1/health/ready
      me.py                 GET /v1/me (authenticated identity proof)
  tests/
    conftest.py             TestClient fixture + dependency overrides
    test_health.py
    test_auth.py
    test_rbac.py
    test_errors.py
    test_webhook_signature.py
    test_config.py
    test_schemas.py
```

Future milestones add `routers/merchants.py`, `routers/listings.py`,
`routers/orders.py`, `routers/payments.py` (webhook wiring only in
Milestone 6), `routers/admin.py`, and `services/` modules — each
importing the boundaries below, never bypassing them.

## Integration boundaries

### 1. Configuration and secrets

- `config.Settings` reads only environment variables. No secret is
  hard-coded, committed, or logged. `SUPABASE_SERVICE_ROLE_KEY` and
  `RAZORPAY_WEBHOOK_SECRET` are `SecretStr` and are never serialised.
- The app starts without a service-role key so health checks work in
  local development, but any service-role operation fails closed
  (`ServiceRoleUnavailable`, 503) until the key is configured. This is
  deliberate: a missing server secret must never silently downgrade to
  a user token, and a user token must never silently upgrade to
  service-role.
- Production must set `ENVIRONMENT=production` and must not use
  `ALLOWED_ORIGINS=*`.

### 2. Supabase client integration

- No direct PostgreSQL connection in Milestone 2. All database access
  goes through Supabase's HTTP APIs (Auth + PostgREST / RPC), so RLS
  and the function contracts in Milestone 1 remain the enforcement
  point.
- Two clients, kept apart in code:
  - **User-context client** — built from the caller's Bearer token.
    It forwards that token unchanged (`Authorization: Bearer <token>`)
    plus the publishable key. It is the ONLY client used for
    user-context RPCs and for reads/writes that must respect the
    caller's RLS. It may only query the `public` schema.
  - **Service-role client** — built only from
    `SUPABASE_SERVICE_ROLE_KEY`, only inside server-only service
    code, only for `backend_*` RPCs after the handler has done its
    own authentication, authorisation, validation and (for payments)
    gateway verification. It must never be constructed from, or
    returned to, client code, and it must never be used to call a
    user-context RPC and expect `auth.uid()` to identify the user —
    service-role bypasses RLS and has no user identity.
- The `private` schema is never queried through PostgREST from either
  client. Private data is reached only through the public `backend_*`
  RPC wrappers, which is how the database contract is designed.

### 3. Authentication

- `auth.py` resolves identity by calling Supabase Auth
  `GET /auth/v1/user` with the Bearer token. It does not decode the
  JWT locally and does not trust any `X-User-Id`, `X-Role` or
  body-supplied identity header. A 401/403 from Auth becomes a 401
  here; a missing token becomes a 401; a missing Supabase URL/key
  becomes a 503, never a fallback anonymous identity.
- `AuthenticatedUser` carries `id`, `email`, and the raw token only
  for building the user-context client. The token is excluded from
  every response model.
- `GET /v1/me` exists in Milestone 2 solely to prove this boundary
  end to end in tests: it returns the authenticated user's id/email
  and their platform roles, nothing else.

### 4. Authorisation (RBAC)

- Roles are never accepted from the request. Platform roles come from
  `public.platform_user_roles` where `revoked_at IS NULL`; merchant
  roles come from `public.merchant_memberships` where
  `is_active = true`; store roles come from
  `public.store_staff_memberships` where `is_active = true`. All are
  read through the user-context client, so RLS still applies.
- `rbac.py` provides dependency factories:
  `require_platform_role(...)`, `require_merchant_role(...)`,
  `require_store_role(...)`. A missing or insufficient role is a 403,
  not a 401, and is logged without the role list of other users.
- **Reviewer identity rule:** any future call to
  `backend_review_merchant` / `backend_review_store` /
  `backend_update_refund_status` must use `p_reviewer_id` /
  `p_actor_user_id` = the authenticated user's id. `rbac.py` provides
  `reviewer_id_for(user)` and a `strip_caller_supplied_reviewer`
  helper; handlers must never forward a client-supplied reviewer id.
  Milestone 2 implements the helpers, not the review routes.

### 5. Errors, logging, ids

- Every error uses one envelope:
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.
  Validation errors are 422 `VALIDATION_ERROR`; auth failures are 401;
  authorisation failures are 403; unknown routes are 404; unexpected
  failures are 500 `INTERNAL_ERROR` with no stack trace in the body.
- Every request gets a UUID request-id (from `X-Request-Id` if the
  caller supplies a valid UUID, otherwise generated), returned in the
  response header and included in every log line. Logs are structured
  JSON with timestamp, level, request-id, method and path. No tokens,
  keys or raw request bodies are logged.

### 6. Payments — what Milestone 2 does and does not do

- Milestone 2 does **not** integrate Razorpay, does not create orders,
  does not trigger payments, and does not call any payment RPC.
- It **does** implement and unit-test the one security primitive the
  later webhook handler must use first: HMAC-SHA256 verification of
  the Razorpay webhook signature against the raw request body
  (`security.verify_razorpay_signature`), with constant-time
  comparison and fail-closed behaviour when
  `RAZORPAY_WEBHOOK_SECRET` is not configured.
- The Milestone 6 webhook handler must: verify the signature first,
  then record the event via `backend_record_payment_webhook_event`
  with `p_signature_verified = true`, and only then act on it. A
  client success screen, an unverified webhook, or a frontend payment
  status must never be trusted as payment confirmation. That wiring
  is explicitly out of Milestone 2 scope.

### 7. Health and readiness

- `GET /health` is liveness only: it never touches Supabase, so a
  load balancer can use it even when the database is down.
- `GET /v1/health/ready` is readiness: it checks BOTH Supabase Auth
  (`GET /auth/v1/health` must return 200) AND PostgREST
  (`GET /rest/v1/` with the publishable key must return 200, no data
  is read), and reports whether Supabase and the service-role key
  are configured (booleans only, never keys, URLs, or upstream
  bodies). On success it returns 200 with `status: "ready"` and a
  `checks` map. On failure — Supabase not configured, Auth
  unreachable, or PostgREST unreachable — it raises
  `ServiceUnavailableError`, which the error handler turns into
  HTTP 503 with the standard error envelope
  (`error.code: "SERVICE_UNAVAILABLE"`, plus `request_id`). It does
  NOT return a 200 with `status: "degraded"`: a degraded dependency
  is a 503, never a success response.

## Testing strategy

- `pytest` + FastAPI `TestClient`. Auth, readiness and RBAC tests
  override dependencies / HTTP calls with fakes; no test hits the
  live Supabase project and no test uses a real secret.
- Initial coverage targets the boundaries above, not business logic:
  health liveness vs readiness, missing/invalid token, platform and
  merchant role grants and denials, error-envelope shape, webhook
  signature verification (valid, tampered body, tampered signature,
  missing secret), config validation, and schema validation
  (enums, INR Decimal, pagination bounds).
- Static checks in Milestone 2: `ruff check` and `mypy` (see
  `backend/README.md`). Both must pass before the branch is reviewed.

## Milestone 2 review fixes (same branch, before merge)

1. **RPC restrictions are enforced in code, not just documented.**
   `supabase_client.py` now has explicit allowlists: user-context
   clients may only call the 8 user RPCs, service-role clients may
   only call the 10 `backend_*` RPCs, and unknown RPCs are rejected
   by both. (The earlier draft of this section said 11; the actual
   allowlist in `supabase_client.py` — and the test that asserts it
   — contains exactly 10 backend RPCs.) Service-role clients may not query tables directly at
   all — privileged work must go through a reviewed `backend_*`
   function. Violations raise `RPCNotAllowedError` before any HTTP
   call, and are covered by `tests/test_supabase_client_restrictions.py`.
2. **Dependencies upgraded and pinned.** FastAPI 0.115.6 (Starlette
   0.41.3, vulnerable) → FastAPI 0.162.0 (Starlette 1.10.0),
   Pydantic 2.14.2, Uvicorn 0.54.0, pytest 9.2.0. Starlette is not
   pinned independently; FastAPI's requirement resolves it and the
   resolved version is recorded in `backend/requirements-lock.txt`.
   `pip-audit` is clean on the new pins (see report).
3. **Dockerfile fails on install failure.** The `|| true` and the
   test-tool uninstall step are removed. The image installs runtime
   dependencies only from `requirements.txt`; a failed install fails
   the build. CI also builds the image and smoke-tests `/health`.
4. **CORS parsing is consistent.** `ALLOWED_ORIGINS` accepts a
   single URL, a comma-separated list, or a JSON list (as in
   `backend/README.md`), validates each origin, and rejects `*` in
   production at settings construction time. The field is
   `Annotated[list[str], NoDecode]`, so pydantic-settings passes the
   raw environment string to the validator instead of JSON-decoding
   it first; environment-source tests in `tests/test_cors.py`
   construct `Settings()` from real environment variables to prove
   this, not only from direct constructor arguments.
5. **Readiness checks Auth and PostgREST.** Both must be reachable
   or readiness returns 503. Responses contain only check names and
   booleans, never URLs, keys, or upstream bodies.
6. **RBAC is filtered twice.** Platform revoked records and inactive
   merchant/store memberships are filtered in code as well as in the
   PostgREST query, and forbidden-access tests cover missing roles.

## Milestone 3: Merchant onboarding & store setup

Routes: `POST /v1/merchants/applications`,
`GET /v1/merchants`, `GET /v1/merchants/{merchant_id}`,
`POST /v1/merchants/{merchant_id}/stores`,
`GET /v1/merchants/{merchant_id}/stores`,
`GET /v1/stores/{store_id}/hours`,
`PUT /v1/stores/{store_id}/hours`.

Contract, verified against the baseline SQL and generated types
before implementation (no columns, parameters, or behaviour
invented):

- `apply_merchant_application(p_legal_name, p_display_name,
  p_business_type, p_business_email, p_business_phone)` returns
  the merchant UUID, creates the merchant (`status`
  `pending_review`, `verification_status` `pending` by DB default)
  and an `owner` membership for `auth.uid()`. Email/phone are
  nullable in the DB and optional in the API; when supplied they
  are format-validated.
- `create_merchant_store(p_merchant_id, p_name, p_slug,
  p_address_line_1, p_address_line_2, p_locality, p_city, p_state,
  p_pincode, p_latitude, p_longitude, p_contact_phone,
  p_pickup_instructions)` returns the store UUID, requires
  merchant owner/admin, and creates the store in `draft` status
  with `country_code` `IN` and `timezone` `Asia/Kolkata` by DB
  default. Slug is lowercased by the DB; the API lowercases it
  first so the RPC argument matches the stored value.
- `upsert_store_hours(p_store_id, p_hours jsonb)` returns the
  number of processed entries (1-7). Each entry is
  `{weekday, is_closed, opens_at, closes_at}`; closed days must
  have no times, open days need both times. It requires
  `can_manage_store(store_id, ['store_manager'])`.

Authorisation, in API code and in the DB:

- Every route resolves the user through Supabase Auth and uses
  only the user-context client. Service-role is never used here.
- Merchant list/detail/store-list require any active merchant
  membership; store creation requires owner/admin.
- Store hours require `can_manage_store_hours`, which mirrors
  the DB function: owners/admins pass with no store-staff row;
  a store_manager passes only with an active merchant membership
  as well. Relying on store-staff memberships alone would block
  owners/admins, which is the bug this design avoids.
- RLS remains authoritative: a caller who is not a member sees
  no rows, and the API turns that into 403 (membership-gated
  routes) or 404 (a store that is not visible to the caller).
- Upstream PostgREST errors are mapped by PG code in the body
  (42501 → 403, 22023 → 422, P0002 → 404, otherwise 502), not by
  HTTP status alone, because PostgREST returns 400 for most PG
  errors.

Validation (API layer, before any RPC): business-type enum is
exactly the DB's 10 values; names are stripped and non-empty;
email format and Indian mobile format when supplied; PIN code
`^[1-9][0-9]{5}$`; latitude -90..90, longitude -180..180, both
or neither; hours weekdays 0-6, unique, max 7, min 1, closed
days have no times, open days have opens_at < closes_at (the
DB only rejects equal times; the API rejects reversed times too
as invalid business data). Invalid requests return 422 with the
standard envelope; no request value is echoed in errors.

Explicitly deferred: merchant approval/document verification,
store activation, listings, inventory, ordering, payments,
pickup, refunds, delivery, and any schema change.

## Remaining blockers (not hidden)

1. No Supabase access token or DB password is available in this
   environment, so the Supabase CLI link step and any live
   end-to-end test against `zehnhqcfawagxbactvne` remain a
   developer step (see `backend/README.md`). All Milestone 2 tests
   are therefore mocked at the Auth/PostgREST boundary.
2. The consolidated baseline mismatch from Milestone 1 still stands:
   local migrations are one tracking file, remote history is 15
   files. No new migration is created in Milestone 2, so this does
   not block foundation work, but it must be re-verified before any
   future schema change.
3. Razorpay keys, webhook secret, and the service-role key must be
   supplied as deployment secrets by the owner; they are not in this
   repository and must not be added to it.
