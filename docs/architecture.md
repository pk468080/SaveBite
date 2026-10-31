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

## Milestone 4: Listings and inventory — Stage 1 audit (read-only,
verified against the live database 2026-10-31, NOT applied)

### Tables and constraints (exact, from baseline + live checks)

- `listings`: id, store_id FK, template_id FK (SET NULL), listing_type
  (`surprise_bag` | `individual_item`), category_id FK, title NOT NULL,
  description, contents_description, reference_value numeric(12,2)
  >= 0, selling_price numeric(12,2) >= 0, currency CHECK = 'INR',
  total_quantity > 0, reserved_quantity >= 0 default 0,
  sold_quantity >= 0 default 0, available_quantity integer
  GENERATED ALWAYS AS
  (total_quantity - reserved_quantity - sold_quantity) STORED
  — database-managed, never writable by application code, and
  recalculated by PostgreSQL whenever the underlying quantities
  change — sale_starts_at
  default now(), sale_ends_at, pickup_starts_at, pickup_ends_at,
  prepared_at, best_before_at, allergen_codes text[] default '{}'
  (NO enum, NO check — format validation only), dietary_classification
  (`vegetarian` | `non_vegetarian` | `vegan` | `egg` | `unknown`,
  default 'unknown'), storage_instructions, food_safety_notes,
  status (`draft` | `scheduled` | `active` | `paused` | `sold_out` |
  `expired` | `cancelled`, default 'draft'), published_at NULL,
  created_by FK auth.users, created_at/updated_at.
  CHECKs: reserved+sold <= total; sale_ends > sale_starts;
  pickup_ends > pickup_starts; pickup_ends >= sale_ends;
  best_before IS NULL OR best_before >= prepared_at.
  Only trigger: set_updated_at on UPDATE.
- `listing_templates`: store_id, listing_type, category_id, title,
  reference_value >= 0, default_selling_price >= 0, contents,
  allergens, dietary, storage_instructions, is_active. No
  created_by column — templates are store-scoped, not user-scoped.
- `listing_images`: listing_id FK CASCADE, storage_path,
  UNIQUE(listing_id, storage_path), alt_text, display_order.
- `categories`: 15 rows seeded, all is_active=true (Bakery, Bread,
  Pastries, Cakes and Desserts, Snacks, Prepared Meals, Restaurant
  Specials, Fruits, Vegetables, Dairy, Groceries, Beverages,
  Sweets, Packaged Food, Other). parent_id self-FK, slug UNIQUE.
- `inventory_events`: event_type CHECK (listing_created,
  quantity_increased, quantity_decreased, reserved,
  reservation_released, sold, manual_adjustment,
  listing_cancelled). `inventory_reservations`: quantity > 0,
  one active reservation per order_item. Neither table has an
  INSERT RLS policy for authenticated users — only SELECT —
  so the API must never write them directly.

### RLS policies (live pg_policies, matching baseline)

- listings SELECT (anon+authenticated): public-active (status
  active AND sale window open AND available_quantity > 0 AND
  is_store_public) OR can_manage_store(store_id, NULL) OR
  platform operations/compliance/super admin.
- listings INSERT (authenticated): created_by = auth.uid() AND
  can_manage_store(store_id, ['store_manager',
  'inventory_manager']) — owners/admins pass via can_manage_store.
- listings UPDATE (authenticated): USING same rule, WITH CHECK
  same rule AND (status <> 'active' OR (available_quantity > 0
  AND is_store_public)).
- listings DELETE: NO policy — DELETE is denied for
  authenticated users. Cancel is therefore a status update, not
  a delete, and this API has no delete endpoint.
- listing_images INSERT (authenticated): listing exists AND
  can_manage_store(listing.store_id, ['store_manager',
  'inventory_manager']). SELECT: public-active listing OR member.
  UPDATE/DELETE: NO policy — images can be registered and
  listed, but not edited or removed through PostgREST.
- listing_templates INSERT/UPDATE/SELECT: member rule above;
  platform operations/super admin on SELECT.
- categories SELECT (anon+authenticated): is_active only.
- inventory_events SELECT: listing owner/admin/store_manager/
  inventory_manager/finance_viewer OR platform
  operations/finance/super admin. inventory_reservations
  SELECT: can_view_order only.

### Column grants — the part RLS alone does not show

Table-level grants look like SELECT-only for authenticated, but
column grants are the real write surface (verified live):

- listings INSERT: every business column EXCEPT id, status,
  published_at, available_quantity, reserved_quantity,
  sold_quantity, created_at, updated_at.
- listings UPDATE: business columns + status, EXCEPT store_id,
  listing_type, template_id, currency, created_by, and all
  inventory counters, published_at, id, timestamps.
- listing_images INSERT: listing_id, storage_path, alt_text,
  display_order only. No UPDATE/DELETE grant at all.
- categories: SELECT only.

Consequences the API enforces:
1. A listing is always created as draft — the API never sends
   status, and could not even if it tried.
2. Inventory counters cannot be forged through PostgREST — the
   API never sends them, and no merchant user can either.
3. listing_type, store_id, template_id, currency, created_by
   are immutable after creation through this API.
4. published_at cannot be stamped on activation through
   PostgREST — it stays NULL (see gap 2 below).

### Storage bucket listing-media (verified live)

- Public bucket, file_size_limit 5,242,880 bytes (5 MB),
  allowed_mime_types image/jpeg, image/png, image/webp.
- INSERT/UPDATE/DELETE policies: path first segment must match
  the UUID regex AND the listing's store must be manageable by
  the caller (store_manager/inventory_manager, owners/admins
  via can_manage_store). SELECT is public for the whole bucket.
- Therefore the upload path MUST be `<listing_id>/<file>`.
  The API validates that shape and rejects URLs; the file
  itself is uploaded by the caller with their own token (the
  bucket policy authorises them), and the API only registers
  the storage_path in listing_images. No signed-URL or
  service-role upload path was added in this milestone.

### Inventory functions — authority stays in the database

- `create_order_reservation` (user RPC) is the ONLY stock
  reservation path: it locks the listing row, checks status
  active + windows + `available_quantity < quantity`, then
  increments reserved_quantity and writes inventory_reservations
  + inventory_events. This milestone does NOT recreate any of
  that in Python, and the inventory endpoint is read-only.
- `backend_release_expired_reservations` is server-only.

### Availability — corrected (2026-10-31): no migration needed

CORRECTION to the Milestone 4 audit: the earlier claim that
available_quantity was a nullable column without automatic
calculation was wrong. The verified live definition is:

  available_quantity integer GENERATED ALWAYS AS
  (total_quantity - reserved_quantity - sold_quantity) STORED

That means, in the actual live database:

- Availability is generated from total_quantity minus
  reserved_quantity minus sold_quantity. PostgreSQL
  recalculates it automatically whenever any of those three
  quantities change — no trigger, no application code, and no
  additional migration is needed for availability.
- The reservation function locks the listing row, checks
  available stock (available_quantity < quantity) before
  reserving, and increments reserved_quantity; PostgreSQL
  then recalculates the generated column in the same
  transaction.
- Merchants cannot directly modify the generated availability
  value: there is no manual INSERT or UPDATE permission for
  available_quantity for anon or authenticated, and the API
  never sends it on create or update.
- Public visibility and activation therefore work on the
  generated value: a listing with stock has available > 0 by
  construction, and the activation WITH CHECK
  (available_quantity > 0 AND is_store_public) is evaluated
  against the generated value, not a stale or NULL column.
- The API's response value total - reserved - sold is the
  SAME formula as the generated column, so it matches the
  stored value exactly; it is kept as a read-side computation
  in code, not as a replacement for the database column.

No trigger for available_quantity was added, and no migration
was created for this correction — the baseline file was
corrected to match the live schema, which already works.
No trigger or additional migration is needed for availability.

Gap 2 (SEPARATE, still open — do not bundle with availability):
published_at has no writer. No trigger sets it on activation
and the role cannot update it. This still needs separate
review and a dedicated implementation plan; until then it
stays NULL and must not be presented as a publish timestamp.
No trigger or publication-behaviour change is introduced
here for published_at.

Gap 3: image removal is impossible through current policies
(no DELETE policy, no DELETE grant on listing_images, and the
storage DELETE policy exists but would orphan the row).
Proposed fix, if removal is required: add a
listing_images_delete_store_operator policy + DELETE column
grant, and delete the storage object in the same request.
Until then this API has no image-delete endpoint, by design.

Gap 4: sold_out and expired have no writer either — no
function or trigger moves a listing into them. They exist in
the enum but are not API-settable in this milestone; a future
system job (e.g. expiry sweep, stock depletion in the
reservation function) must own those transitions.

Gap 5 (accepted, not a defect): the API-level role checks
duplicate the RLS rules. That is deliberate defence in depth:
a caller gets a clean 403/404 from the API instead of a raw
PostgREST rejection, and a future grant/policy change cannot
silently widen the API.

### Milestone 4 routes (implemented)

- POST /v1/stores/{store_id}/listings (201, draft)
- GET /v1/stores/{store_id}/listings (any merchant member)
- GET /v1/listings/{listing_id}
- PATCH /v1/listings/{listing_id} (whitelisted columns only;
  total_quantity >= reserved+sold enforced in API)
- POST /v1/listings/{listing_id}/publish|pause|resume|cancel
- GET /v1/listings/{listing_id}/inventory (read-only; available
  is the generated column value, same formula as in code)
- GET /v1/categories (active only)
- GET/POST /v1/listings/{listing_id}/images (register + list;
  no edit/delete, per gap 3)
- Validation: Decimal money (never float), selling_price > 0,
  reference_value >= 0, selling_price above reference is
  ALLOWED because the database explicitly permits it (only
  >= 0 checks) — the API does not invent a discount rule;
  total_quantity > 0; windows per DB CHECKs; best_before >=
  prepared_at when both set; allergen format only (no invented
  code list); category must be active; template must belong
  to the store; storage_path must start with the listing id.

Explicitly NOT in this milestone: customer checkout, Razorpay,
pickup verification, refunds, delivery, listing deletion,
image deletion, and any migration or live database change.

## Milestone 5: Customer marketplace & reservation

### Anonymous versus authenticated access

- Discovery (`GET /v1/marketplace/listings`,
  `GET /v1/marketplace/listings/{listing_id}`,
  `GET /v1/marketplace/categories`) requires NO bearer token.
  It uses a dedicated anonymous client (`anon_client` in
  supabase_client.py, `get_anon_client` dependency) that
  authenticates as Supabase's anon role with the publishable
  key only. That client is read-only by construction: its
  insert, update, and rpc methods raise before any HTTP call,
  it never carries a user token, and it never uses the
  service-role key. The existing authenticated client behaviour
  is unchanged, and the RPC allowlists and service-role
  boundaries are untouched.
- Reservation (`POST /v1/orders/reservations`) REQUIRES
  Supabase Auth (get_current_user + get_user_client). No
  caller-supplied user id or role is accepted anywhere:
  identity comes only from the Auth dependency, and the RPC
  itself resolves the customer from auth.uid().

### Public discovery rules

Eligibility is enforced twice: by the RLS public policies
(listings: status active, sale window open, available > 0,
public store; stores: status active + merchant approved;
categories: is_active; images: eligible public listing) AND
by re-checks in the router (same rules, plus category active,
pickup window not ended, and an explicit field projection).
Draft, paused, cancelled, sold_out, expired, zero-stock,
inactive-store, and unapproved-merchant listings are never
returned; a non-eligible detail request returns 404, not a
leak of the listing's existence.

Public response fields only (PublicListingSummary): id, store
(id, name, locality, city, state, pincode, timezone),
listing_type, category_id, category_name, title, description,
contents_description, reference_value, selling_price, currency,
available_quantity (the generated column value), dietary
classification, allergen codes, storage instructions, sale
and pickup windows, prepared_at, best_before_at, and image
references (storage_path in listing-media, alt_text,
display_order). Excluded by design: created_by, created_at,
updated_at, template_id, food_safety_notes, total/reserved/
sold quantities, merchant internals, contact phones, and any
payment data. Image paths are validated to
`<listing_id>/<file>`; any URL or foreign path is dropped.

Filters: city (exact, case-insensitive, on the store),
pincode (six digits), category_id, listing_type, search
(substring over title/description/contents), min/max selling
price (Decimal, min <= max), dietary classification.
Sorting: newest (created_at desc), lowest_price, highest_price,
ending_soon (sale_ends_at asc), each with an ascending id
tiebreak so pagination is stable. Pagination: page (default
1) and page_size (default 20, max 100), applied after
filtering and sorting; the response carries items, total,
page, and page_size. Distance sorting is NOT offered: it
would need a PostGIS RPC or schema change, documented here
as a future enhancement, not invented.

Pagination note (honest limitation): because city/pincode
live on stores while listings live on listings, the router
fetches eligible listings through PostgREST and then filters,
sorts, and paginates in Python. That is correct for pilot
scale and for the tested behaviour, but at large catalogue
scale it should move to a dedicated read RPC with
server-side pagination. No schema change was made for it in
this milestone.

### Reservation

`POST /v1/orders/reservations` with header `Idempotency-Key`
(8–128 characters, validated in the API and by the RPC) and
body `{store_id, items: [{listing_id, quantity}], customer_note?}`.
Validation in the API: store/listing UUIDs, 1–20 items,
unique listing ids, quantity 1–20 per item, note max 1000
characters. Everything else is the database's authority:
the RPC locks listing rows, checks active status and sale/
pickup windows, checks available inventory, rejects items
from another store, creates the order in pending_payment
status, increments reserved inventory, writes reservation
and event records, and enforces idempotency (same key + same
request hash returns the original order with
idempotent_replay true and no new expiry; same key with a
different request is rejected). Expiry is approximately
5 minutes after creation, as set by the RPC.

Example request:

```sh
curl -X POST http://127.0.0.1:8000/v1/orders/reservations \
  -H "Authorization: Bearer <supabase-user-jwt>" \
  -H "Idempotency-Key: order-2026-10-31-001" \
  -H "Content-Type: application/json" \
  -d '{"store_id": "<store-uuid>", "items": [
    {"listing_id": "<listing-uuid>", "quantity": 2}
  ], "customer_note": "Please pack separately"}'
# 201 {"order_id": "<uuid>", "order_number": "SF-20261031-000001",
#      "status": "pending_payment", "total_amount": "390.00",
#      "currency": "INR",
#      "reservation_expires_at": "2026-10-31T12:05:00Z",
#      "pickup_starts_at": "...", "pickup_ends_at": "...",
#      "idempotent_replay": false}
```

A reservation is NOT a completed or paid order. The status
pending_payment means stock is reserved and payment is still
due; the customer must not be told payment succeeded or the
order is fully confirmed. This milestone does NOT call
begin_payment_checkout, does NOT generate or verify pickup
tokens, does NOT process refunds, and does NOT touch orders,
order_items, inventory_reservations, inventory_events, or
inventory counters directly in Python.

Error responses use the standard envelope: 401
unauthenticated reservation, 404 listing not found (or not
eligible), 422 validation (including database validation
such as insufficient_inventory, listing_not_available, and
idempotency-key reuse, mapped from the RPC error), 502
upstream failure.

Explicitly NOT in this milestone: Razorpay checkout or
payment confirmation, payment webhooks, pickup tokens,
refunds, merchant payouts, delivery, new merchant onboarding,
admin portal, image deletion, published_at repair, and any
RLS/grant/RPC/schema change.

## Milestone 6: Razorpay payments

### Verified payment lifecycle (from the baseline, not assumed)

- `private.payment_transactions`: order_id, gateway
  (CHECK razorpay/other), gateway_order_id, gateway_payment_id,
  amount numeric(12,2) >= 0, currency CHECK = 'INR',
  status payment_status (created, authorized, captured,
  failed, refund_pending, partially_refunded, refunded,
  reconciliation_required), idempotency_key UNIQUE,
  gateway_signature_verified boolean, captured_at,
  failure_code, failure_description. Unique partial indexes
  on (gateway, gateway_order_id) and (gateway,
  gateway_payment_id) where not null.
- `private.payment_webhook_events`: gateway, gateway_event_id
  UNIQUE with gateway, event_type, payload jsonb,
  signature_verified, processing_status CHECK (received,
  processing, processed, failed, ignored).
- Order status enum: pending_payment, confirmed,
  ready_for_pickup, collected, expired, cancelled,
  refund_pending, refunded. Payment status enum: see above.
- `begin_payment_checkout(p_order_id, p_idempotency_key)`
  (user-context): requires the caller to own the order and
  the order to be pending_payment with all reservations live
  (active, not expired); creates or reuses a payment
  transaction by idempotency key (same key + different
  order = payment_idempotency_conflict); returns
  payment_transaction_id, order_id, amount, currency,
  gateway razorpay.
- `backend_attach_gateway_order(p_payment_transaction_id,
  p_gateway_order_id)` (server-only): requires transaction
  status created; re-attaching the SAME gateway order id is
  allowed, a different one is a conflict.
- `backend_confirm_payment_capture(p_payment_transaction_id,
  p_gateway_payment_id, p_amount, p_signature_verified)`
  (server-only): refuses unless p_signature_verified is
  true; returns the order id without side effects when
  already captured; on amount mismatch sets transaction and
  order to reconciliation_required; on a non-live
  reservation likewise; otherwise marks the transaction
  captured, moves reserved -> sold quantities, consumes
  reservations, writes inventory events, and confirms the
  order (pending_payment -> confirmed).
- `backend_mark_payment_failed(...)` (server-only):
  refuses a captured payment (captured_payment_cannot_be_
  failed); otherwise marks the transaction failed and the
  order payment_status failed (only while pending_payment
  and no other live transaction exists).
- `backend_record_payment_webhook_event(p_gateway,
  p_gateway_event_id, p_event_type, p_payload,
  p_signature_verified)` (server-only): refuses unless
  signature verified; inserts with ON CONFLICT (gateway,
  gateway_event_id) DO NOTHING-equivalent, so a redelivery
  creates no second row.

### Endpoints

- `POST /v1/orders/{order_id}/checkout` (authenticated,
  201, header Idempotency-Key 8–128 chars of letters,
  digits, - or _): user-context begin_payment_checkout,
  then a server-side Razorpay order for exactly the
  database amount (Decimal rupees -> integer paise, never
  float; non-INR rejected), then server-only attach. The
  Razorpay order carries notes savebite_payment_transaction_
  id and savebite_order_id. Returns only key_id (public),
  razorpay_order_id, payment_transaction_id, amount_paise,
  currency, and the customer's email as prefill. No secret
  is ever returned or logged.
- `POST /v1/payments/verify` (authenticated): body
  razorpay_order_id, razorpay_payment_id, razorpay_signature.
  The payment is fetched from Razorpay's API server-side;
  the signature is verified as HMAC-SHA256 over
  `razorpay_order_id|razorpay_payment_id` with the key
  secret, computed over the provider-confirmed order id,
  not a frontend-supplied one; the payment must be
  captured, INR, and resolvable to a SaveBite transaction
  via the Razorpay order's notes. Only then is
  backend_confirm_payment_capture called with the
  provider-verified amount and p_signature_verified true.
  A valid signature alone never confirms: an authorized-
  only payment is rejected, and a replayed verification is
  a no-op through the RPC's already-captured path.
- `POST /v1/webhooks/razorpay` (no Supabase Auth; the
  webhook signature is the authentication): the raw body
  is verified with HMAC-SHA256 and the webhook secret
  (X-Razorpay-Signature) BEFORE parsing or acting; missing
  or invalid signatures get 401 and nothing is processed.
  The event is recorded first (deduped by gateway + event
  id, from the X-Razorpay-Event-Id header), then:
  payment.captured -> provider fetch + confirm (same
  rules as verify, minus the checkout signature, because
  the webhook signature was already verified);
  payment.failed -> provider order notes -> mark_failed
  (a failure after capture is treated as already_captured,
  never overwriting the capture); every other event,
  including order.paid, is recorded and ignored (subscribing
  to payment.captured is sufficient). A transient provider
  fetch failure returns 502 so Razorpay retries; an
  unresolvable mapping returns 200 with a reason, because
  a retry cannot fix a missing mapping.

### Idempotency and retry behaviour

- Checkout: same key + same order reuses the transaction.
  A Razorpay API timeout after order creation is treated
  as ambiguous and is NOT auto-retried (a retry would
  create a second Razorpay order); the client retries with
  the same key and the new Razorpay order is attached. An
  orphaned, unpaid Razorpay order charges nobody.
- Webhook: record-then-act, so a crash between recording
  and acting is recovered by Razorpay's retry (the
  redelivery records the same event id and then acts).
  Confirm and mark-failed are themselves idempotent /
  capture-protecting, so duplicate deliveries cannot double
  capture or overwrite a capture.
- Verification and webhook in either order are safe: the
  first confirms, the second is a no-op.

### What is deliberately NOT in this milestone

No refunds, merchant payouts, settlements, delivery, or
pickup-token workflows. No frontend-reported failure
endpoint: a frontend failure is not authoritative — only a
provider-verified webhook justifies mark_failed, and a
customer closing checkout simply lets the reservation
expire. No direct private-table access anywhere: the
service-role client may only call backend_* RPCs, and it
may not query tables at all.

### Missing capability — PROPOSED, NOT APPLIED

There is no approved RPC that maps a Razorpay gateway
order id (or a SaveBite order id) back to a payment
transaction id, and the service-role client is forbidden
from querying tables, so the gateway-order -> transaction
mapping is currently resolved through Razorpay's own
order notes (set by the backend at checkout, read back
server-side). That works, but it costs an extra provider
API call and fails closed when notes are absent. The clean
fix, which needs separate approval and is NOT applied
here, is one server-only function:

```sql
-- PROPOSED ONLY — do not apply without a separate approval.
CREATE OR REPLACE FUNCTION public.backend_get_payment_transaction_by_gateway_order(
  p_gateway_order_id text
) RETURNS uuid
LANGUAGE sql SECURITY DEFINER
SET search_path TO ''
AS $$ SELECT id FROM private.payment_transactions
     WHERE gateway = 'razorpay' AND gateway_order_id = p_gateway_order_id $$;
```

With it, verification and webhooks could resolve the
transaction without the notes round-trip, and a checkout-
status endpoint could recover a lost checkout response
after a successful attach (today, a repeat checkout in
that case returns 422 because the new Razorpay order
conflicts with the already-attached one — the customer is
not charged, but the original gateway order id cannot be
re-issued through the API).

### Deployment configuration (manual, by the owner)

Set these in the Render environment (never in source):
SUPABASE_SERVICE_ROLE_KEY, RAZORPAY_KEY_ID (rzp_test_ in
test mode, rzp_live_ in production — the key_id is the only
Razorpay value the API returns), RAZORPAY_KEY_SECRET,
RAZORPAY_WEBHOOK_SECRET. Razorpay dashboard webhook URL:
https://<api-domain>/v1/webhooks/razorpay, subscribed to
payment.captured and payment.failed (order.paid is
recorded and ignored, so it need not be subscribed).
Operational rule for pending or ambiguous payments: a
payment whose provider status is authorized (not captured)
is never confirmed by this API; a transaction in
reconciliation_required (amount mismatch or non-live
reservation at confirm time) needs manual review against
Razorpay's dashboard before any further action — do not
re-confirm it from the frontend.

## Milestone 7: Order management and customer tracking

### What was audited (verified, not assumed)

- `public.orders`: order_number, customer_id, merchant_id,
  store_id, status (order_status enum: pending_payment,
  confirmed, ready_for_pickup, collected, expired,
  cancelled, refund_pending, refunded), payment_status
  (created, authorized, captured, failed, refund_pending,
  partially_refunded, refunded, reconciliation_required),
  subtotal/discount/platform_fee/tax/total amounts,
  pickup window, customer_note, cancellation_reason,
  confirmed_at, collected_at, cancelled_at, created_at,
  updated_at, plus internal request_idempotency_key and
  request_hash (never exposed).
- `public.order_items`: listing snapshot (title,
  description, allergens, dietary), quantity, unit_price,
  reference_value_snapshot, line_total. No image column —
  item images come from listing_images, and only the
  listing's current public image, which may be absent.
- `public.order_status_events`: from_status (nullable),
  to_status, actor_type (customer/merchant/admin/system),
  reason, created_at. This is the ONLY timeline source.
- `public.inventory_reservations`: status active/consumed/
  released/expired, expires_at — the source of
  reservation_expires_at for pending orders.
- RLS: orders/items/events/reservations selectable only
  by the owning customer or a store operator
  (can_manage_store with owner/admin/store_manager/
  pickup_operator/finance_viewer); membership rows only by
  the member or a merchant owner/admin; profiles own-only.
  The API enforces the same rules in Python on top of RLS,
  so a permissive upstream cannot widen access.

### Endpoints (all authenticated, user-context client only)

- `GET /v1/orders` — the caller's own orders, filtered by
  status, payment_status, created_from, created_to;
  newest first (created_at desc, id desc tiebreak);
  page/page_size (max 100). List items carry store
  summary, pickup window, item count, and a two-item
  preview (batched in one order_items query, not N+1).
- `GET /v1/orders/{order_id}` — full customer detail:
  amounts, store address + pickup instructions, pickup
  window, reservation expiry (pending orders only),
  snapshot items with prices and current public images,
  payment summary (status, gateway label, amount paid,
  paid_at), and the real event timeline. Another
  customer's order, or a missing one, returns the same
  404, so existence is never leaked.
- `GET /v1/merchant/orders` — orders for the caller's
  authorized stores only, filtered by store_id (which can
  only narrow the authorized set, never widen it), status,
  payment_status, pickup_from, pickup_to, and order-number
  search. No customer personal information is returned:
  profiles are own-only by RLS, so the API cannot surface
  customer emails, phones, or addresses, and it does not
  return customer_id either.
- `GET /v1/merchant/orders/{order_id}` — merchant detail
  (same shape as the customer detail, including the
  customer's order note for fulfilment, still with no
  customer personal information).
- `GET /v1/merchant/orders/summary` — counts over
  authorized stores (optionally store_id and created
  range): total, awaiting_payment (pending_payment), paid
  (payment_status captured), upcoming_pickups (confirmed
  or ready_for_pickup with a future pickup start),
  completed (collected — the database's completion state;
  there is no separate 'completed' status),
  cancelled_or_expired.

### Status honesty rules enforced here

- pending_payment is not paid; captured is not collected;
  confirmed is not ready_for_pickup. The summary and
  detail show the stored statuses as-is, including
  reconciliation_required (never shown as a successful
  purchase) and expired/cancelled (never shown as an
  active pickup).
- The timeline contains only recorded events, labelled
  from their recorded to_status/reason (reservation
  created, payment confirmed, ready for pickup, collected,
  expired, cancelled, refund pending/refunded). With no
  events, the timeline is empty — history is never
  guessed from the current status. actor_user_id is never
  exposed.
- Payment information comes only from the order row.
  The private payment_transactions table is never queried;
  amount_paid is the order total only when payment_status
  is captured, otherwise 0; gateway_label is "Razorpay"
  only when a payment exists, because Razorpay is the only
  gateway implemented — it is not a per-transaction lookup.

### Pagination and performance note

Filters (customer_id, status, payment_status, created
range, store_id, order-number search, pickup range) are
sent to PostgREST, so the whole orders table is never
fetched into Python; items for a page are fetched in one
batched query. Sorting and pagination are then applied
over the filtered set. At very large scale, limit/offset
should move into PostgREST with a count header (the
current client does not return response headers, so a
total cannot come from PostgREST today) — documented
here as a future optimisation, not hidden. No index or
function was created in the live project for this
milestone.

### Explicitly NOT in this milestone

Pickup-token generation/verification, QR pickup,
cancellation workflows, refunds, payouts, delivery
tracking, notifications, automatic reservation cleanup,
new payment behaviour, and any live schema/RLS/grant/RPC
change. No database change is proposed for M7: the
existing RLS policies already support every read above
through the user-context client.

## Milestone 8: Secure pickup verification and QR collection

### Audit findings (verified from the baseline, not assumed)

- `private.pickup_tokens`: id, order_id, token_hash
  (SHA256 hex, never plaintext), expires_at, used_at,
  invalidated_at, failed_attempts, created_at; token_hash
  is UNIQUE. There is NO public pickup-token table and NO
  retrieval API: a token's plaintext exists only in the
  issue response, once.
- `private.issue_pickup_token(p_order_id uuid) RETURNS
  jsonb`: SECURITY DEFINER, auth.uid() required; order
  must belong to the caller and be confirmed or
  ready_for_pickup (so unpaid, failed, pending_payment,
  cancelled, expired, and already-collected orders are
  all rejected with pickup_not_available — payment
  eligibility is enforced through status, which only
  reaches confirmed via a verified capture); issuance
  refused after pickup_ends_at + 30 minutes; previous
  unused tokens for the order are invalidated; the new
  token is 32 random bytes hex-encoded (64 hex chars),
  stored only as its SHA256 hash, expiring at
  pickup_ends_at + 30 minutes; returns pickup_token_id,
  pickup_token, expires_at. Note: issuance has NO lower
  window bound — a token may be issued early, but
  verification enforces the collection window (below).
- `private.verify_pickup_token(p_store_id uuid,
  p_pickup_token text) RETURNS jsonb`: SECURITY DEFINER,
  auth.uid() required; token must be at least 32 chars;
  caller must satisfy can_manage_store(store,
  [store_manager, pickup_operator]) — and by that
  function's definition, merchant owner/admin members
  pass as well, while finance_viewer and
  inventory_manager do NOT; the token row is locked FOR
  UPDATE and must be unused, uninvalidated, and
  unexpired; the order is locked FOR UPDATE and must
  belong to the store, be confirmed/ready_for_pickup,
  and have payment_status captured; the current time
  must be within pickup_starts_at - 15 minutes to
  pickup_ends_at + 30 minutes. Atomically it then marks
  the token used, sets the order collected with
  collected_at, writes an order_status_event (actor: the
  verifying user, type merchant, reason
  pickup_token_verified) and a pickup_events row
  (method 'qr', result accepted). A second verification
  fails because used_at is set, and concurrent
  verifications are serialised by the FOR UPDATE locks —
  two collections of one order are impossible at the
  database level. Returns order_id, order_number, status
  collected, collected_at. Observation, not a blocker:
  failed_attempts exists in the schema but is NOT
  incremented by this function version, so there is no
  lockout after failed attempts; brute-force protection
  is the token's 64-hex-char randomness plus the
  generic failure messages (below).
- Both RPCs were already in the user-context allowlist;
  no new RPC, migration, RLS change, or grant change was
  needed or applied for this milestone.

### Endpoints (authenticated, user-context client only)

- `POST /v1/orders/{order_id}/pickup-token` — customer
  issues a one-time token for their own eligible order.
  The order fetch before the RPC only supplies response
  fields and a clean 404 for another customer's order;
  ownership and eligibility are the RPC's checks.
  Response (example): order_id, order_number,
  pickup_token (plaintext, once only),
  qr_payload "SB1:<token>", expires_at,
  pickup_starts_at, pickup_ends_at, store_name,
  pickup_instructions. pickup_token_id is deliberately
  NOT returned — the frontend needs the token, not an
  internal id — and no hash, contact data, or payment
  data is ever included. A lost token is not retrievable;
  issuing a fresh one invalidates the old one.
- `POST /v1/merchant/pickups/verify` — body: store_id,
  pickup_token (raw token or SB1: payload; the prefix is
  stripped and the remaining 64 hex chars validated
  before any RPC call). The store_id is the store where
  the customer is standing; it is required by the RPC's
  signature and is NOT trusted as authority — the
  database checks the caller's authorization for that
  store AND that the token's order belongs to it, so a
  wrong store_id fails and can never grant access to
  another store. Success response (example): order_id,
  order_number, store_name, status collected,
  collected_at, items (title + quantity). Item/store
  enrichment happens AFTER the atomic RPC verification;
  if those reads fail, the collection is not rolled back
  — the RPC fields are returned with an empty item list.
- Customer order detail (`GET /v1/orders/{id}`) gained
  `pickup_available`: true only for a confirmed or
  ready_for_pickup order whose pickup window has not
  closed (pickup_ends_at + 30 minutes). It says nothing
  about whether a token was issued (that is unreadable
  by design), and a collected, cancelled, or expired
  order is never pickup-available. Payment status and
  fulfilment status stay separate.

### QR payload format

`"SB1:<64-hex-token>"`. SB1 is a version prefix only.
The payload contains nothing else: no customer name,
phone, email, payment data, order id, or store id. The
frontend renders this string as a QR code; the backend
validates it entirely through the verify RPC. A QR
payload alone never marks anything collected — only a
successful RPC verification does, and a used or expired
token in a QR code fails like any other.

### Store-role permissions for pickup verification

Allowed: merchant owner, merchant admin, store_manager,
pickup_operator (the first two via can_manage_store's
owner/admin branch, the latter two via the role list the
RPC passes). NOT allowed: finance_viewer,
inventory_manager, and any customer or unauthenticated
caller. These rules live in the database, not in Python;
the API maps the RPC's pickup_access_denied (42501) to
403 and does not bypass or widen it.

### Error responses (privacy-safe by design)

- 401: unauthenticated (both endpoints).
- 404: order not found / not the caller's (issue only).
- 422 invalid token format: token is not 64 hex chars
  after prefix stripping (checked before any RPC call).
- 422 "Pickup token is invalid, expired, or already
  used": the RPC's pickup_token_invalid_or_used, which
  deliberately does not distinguish invalid, expired,
  and already-used tokens.
- 422 "Order cannot be collected": the RPC's
  order_not_collectable, which deliberately does not
  distinguish unpaid, cancelled, expired, and
  wrong-store orders.
- 422 "Outside the pickup window": the RPC's
  outside_pickup_window.
- 403 "Not authorized...": pickup_access_denied.
No failure reveals whether another store has an order
for a token, and no token hash or private database error
is ever returned or logged.

### Replay and expiry behavior

Tokens expire at pickup_ends_at + 30 minutes; issuing a
new token invalidates all previous unused tokens for the
order; a used token can never be replayed (used_at is
set atomically with the collection); concurrent
verifications are serialised by FOR UPDATE locks on
both the token and the order rows. A repeated scan after
collection returns the generic invalid/used 422, not a
second collection and not a leak of the order's state.

### Explicitly NOT in this milestone

Delivery/courier tracking, cancellation, refunds,
payouts, notifications, reviews, new payment behavior,
inventory reconciliation, token retrieval, and any live
schema/RLS/grant/RPC change. No database change is
proposed: the existing RPCs already implement the full
required workflow.

## Milestone 9: Customer reviews, ratings and feedback

### Audit findings (verified from the baseline, not assumed)

A review system ALREADY exists in the database — no
new table was needed, and none was created:

- `public.reviews`: id, order_id (FK orders ON DELETE
  RESTRICT), customer_id (FK auth.users), store_id (FK
  stores), merchant_id (FK merchants), rating smallint
  CHECK 1-5, comment text nullable, moderation_status
  text CHECK ('visible','hidden','under_review')
  DEFAULT 'visible', created_at, updated_at
  (set_updated_at trigger). UNIQUE(order_id) — one
  review per order, enforced by the database including
  under concurrent submissions.
- Reviews are per STORE and per ORDER. There is no
  listing_id, no rating dimensions, no merchant-response
  column, no report table, and no aggregate view or
  function. None is invented here.
- RLS, the only policies on the table:
  - INSERT to authenticated WITH CHECK: customer_id =
    auth.uid() AND an order exists with id = order_id,
    customer_id = auth.uid(), store_id = reviews.store_id,
    merchant_id = reviews.merchant_id, status =
    'collected'. Eligibility is a database rule:
    pending_payment, confirmed, ready_for_pickup,
    expired, cancelled, and refund_pending orders can
    never produce a review, and neither can another
    customer's order. A captured payment alone is not
    enough — collection is required.
  - SELECT to anon + authenticated USING:
    moderation_status = 'visible' OR customer_id =
    auth.uid(). Public readers see visible reviews
    only; a customer also sees their own
    hidden/under_review reviews in their own history.
  - NO UPDATE and NO DELETE policy: reviews are
    immutable after submission through this API. There
    is no edit, delete, or moderation endpoint in this
    milestone — moderation_status can only change
    outside the API, and any moderation workflow would
    need its own policy/RPC and approval.
- Column grants for reviews are NOT reproduced in the
  consolidated baseline, so the insert path's grant
  surface is unverified from the baseline alone and must
  be confirmed against live before production use. The
  RLS policies above are verified; grants are the one
  open verification item, documented, not assumed.

### Endpoints (user-context client for writes and own
### reads; anonymous read-only client for public reads)

- `POST /v1/orders/{order_id}/review` — authenticated
  customer submits one review for their own collected
  order. Request: rating (integer 1-5) and optional
  comment (max 1000 chars; whitespace-only becomes no
  comment). Store and merchant ids come from the order
  row, customer id from Auth — the request carries no
  identity or store. The API pre-checks ownership
  (404) and collected status (422), but the RLS INSERT
  check remains the final authority: if the status
  changes between pre-check and insert, the insert
  fails and the API reports ineligibility. Duplicate
  submissions return 409 (UNIQUE order_id); a racing
  duplicate cannot create two reviews. Response:
  review id, order number, store name, rating, comment,
  moderation_status, created_at. No customer_id.
- `GET /v1/my/reviews` — the caller's own reviews,
  newest first (created_at desc, id desc), paginated
  (max 100), optional rating and moderation_status
  filters. Own hidden/under_review reviews appear here
  (policy allows them to the owner); another customer's
  reviews never appear.
- `GET /v1/stores/{store_id}/reviews` — public,
  anonymous-readable, visible reviews only (the SELECT
  policy enforces this for anon readers, and the filter
  is applied explicitly too). Sorts: newest, highest,
  lowest; optional rating filter; paginated. Each
  review shows id, rating, comment, created_at only —
  no customer id, name, email, phone, address, order
  id, payment data, or moderation notes. There is no
  customer display label: profiles are own-only by RLS,
  so no public customer name exists in the database
  contract to show, and none is invented. A store with
  no reviews returns an empty list, never fabricated
  reviews.
- `GET /v1/stores/{store_id}/rating-summary` —
  average rating, total visible review count, and
  5/4/3/2/1-star counts, computed over the SAME visible
  set as the public list, so the two always agree.
  Average is the mean, rounded half-up to 2 decimal
  places; a store with no public reviews returns
  average null and all counts zero, never a fabricated
  5.0. Performance note, documented honestly: there is
  no database aggregate, so the summary fetches ONLY
  the rating column for one store and aggregates in
  Python. That is a pilot-scale approach; at large
  scale it must be replaced by a database view (see
  "Proposed database change" below). No full review
  rows are fetched for the summary.

### Visibility and moderation behavior

Default moderation_status is 'visible', so a submitted
review is publicly visible immediately. 'hidden' and
'under_review' reviews are excluded from public lists
and from the summary, but remain visible to their owner
in their own history. There is no moderation workflow,
merchant reply, report flow, or edit/delete in this
milestone, because the database provides no policy or
RPC for them — adding one would be a schema/policy
change requiring its own approval.

### Marketplace integration

Deliberately NOT changed: adding a store rating to
every marketplace listing would need the same aggregate
source plus a batched lookup, and inventing one here
would risk N+1 queries. The rating-summary endpoint is
the integration point until the proposed view exists;
existing marketplace filtering and responses are
unchanged.

### Proposed database change (NOT applied, needs
### separate approval)

A read-only view or function for store rating
aggregates, e.g. a view over public.reviews restricted
to moderation_status = 'visible', exposing store_id,
average_rating (numeric, 2dp), total_reviews, and the
five star counts, with SELECT granted to anon and
authenticated. Purpose: replace the Python aggregation
in the rating summary at large scale and enable safe
marketplace integration without N+1 queries. It changes
no write path, no RLS, and no existing table. Until it
is approved and applied, the summary's Python
aggregation over the rating column is the documented
behavior.

### Explicitly NOT in this milestone

Merchant replies, review reporting, admin moderation
dashboard, sentiment analysis, AI moderation, photo/
video uploads, loyalty points, discounts or incentives
for reviews, fake/test production reviews, refunds,
payouts, and any live schema/RLS/grant/RPC change.

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
