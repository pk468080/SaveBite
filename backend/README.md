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
pytest -q tests/test_listings.py    # Milestone 4 only
pytest -q                           # full suite
```

Milestone 3 and 4 tests use fakes and dependency overrides only;
they never touch live Supabase and never use a real secret.

## Milestone 10 routes: merchant dashboard and analytics

Read-only reporting. Every number comes from actual
database records; no dashboard route mutates an order,
listing, payment, or review. Authorization mirrors M7
order reads: merchant owner/admin (all stores of that
merchant) or store staff with role store_manager,
pickup_operator, or finance_viewer; inventory_manager
is not in the orders RLS set and is not granted
dashboard access. A requested store_id can only narrow
the authorized set; an unauthorized store returns 404.

- `GET /v1/merchant/dashboard` — overview for one
  store (`store_id`) or all authorized stores, optional
  half-open period `from`/`to`. Returns store context,
  order metrics, inventory metrics, pickup metrics,
  and rating metrics. `open_now` is null: the
  store_hours weekday convention (0 = Monday or
  Sunday) is unverified in the repository, so operating
  status cannot be determined reliably and is not
  guessed.
- `GET /v1/merchant/dashboard/sales` — `store_id`,
  `from`, `to`, `group_by` (day/week/month). Buckets
  carry total, captured, pending-payment, failed-
  payment, collected, and cancelled-or-expired order
  counts plus captured order value, with a totals
  bucket. Grouping uses the store's own timezone for a
  single store, Asia/Kolkata for multiple stores.
- `GET /v1/merchant/dashboard/inventory` — inventory
  summary; with `low_stock_threshold`, listings whose
  generated available_quantity is at or below it (a
  reporting filter only — it changes nothing).
- `GET /v1/merchant/dashboard/pickups` — `store_id`,
  `from`, `to`, `category` (upcoming/in_window/
  completed/window_expired). Each order shows order
  number, status, pickup window, category, and total
  item quantity. Window-expired is never labelled
  "missed": the database records no no-show event.
- `GET /v1/merchant/dashboard/stores` — one row per
  authorized store: name, status, total orders,
  captured order value, collected orders, active
  listings, available units, average rating, review
  count.

Money, precisely: captured order value is the sum of
total_amount over orders whose payment_status is
captured, and nothing else — pending, authorized-only,
failed, refunded, partially_refunded, and
reconciliation states never count, and a captured order
is not called collected unless its order status is
collected. It is NOT merchant earnings, settlement, or
payout revenue: fees, refunds, and payouts are not
deducted, because the order row carries no refund
amounts to net against, so no net revenue is reported.
All money math is Decimal, serialized as strings
("390.00"), never floats. "Published" listings means
status active. Pickup events in private.pickup_events
are not queried; pickup categories come from order rows
+ current time using the verify RPC's windows
(in-window = pickup start - 15 min to pickup end + 30
min). Rating metrics use visible reviews only, the
same rule as M9. See `../docs/architecture.md` for
metric definitions, date rules, and limitations.

## Milestone 9 routes: reviews and ratings

Reviews already exist in the database (public.reviews,
one per order, rating 1-5, moderation visible/hidden/
under_review) — no new table was created. Eligibility
is a database rule: only the owning customer, only a
collected order, store and merchant taken from the
order, never from the request. Reviews are immutable
after submission (no UPDATE or DELETE policy exists),
and there is no edit, delete, or moderation endpoint
in this milestone.

- `POST /v1/orders/{order_id}/review` — authenticated
  customer submits one review for their own collected
  order. Body: `{"rating": 5, "comment": "optional, max 1000 chars"}`.
  Uncollected orders (pending_payment, confirmed,
  ready_for_pickup, expired, cancelled, refund_pending)
  are rejected, as are another customer's orders (404)
  and duplicates (409). Example response:
  ```json
  {
    "id": "a0000000-0000-4000-8000-000000000099",
    "order_number": "SF-20261031-000001",
    "store_name": "Sharma Foods Dwarka",
    "rating": 5,
    "comment": "Great bag, fresh items",
    "moderation_status": "visible",
    "created_at": "2026-10-31T20:00:00Z"
  }
  ```
- `GET /v1/my/reviews` — the caller's own reviews,
  newest first, paginated (max 100), optional rating
  and moderation_status filters. Own hidden/
  under_review reviews appear here; no customer_id is
  returned.
- `GET /v1/stores/{store_id}/reviews` — public,
  anonymous-readable, visible reviews only. Sorts:
  newest, highest, lowest; optional rating filter;
  paginated. Each review shows id, rating, comment,
  created_at only — no customer data of any kind, and
  no fabricated display name (profiles are own-only,
  so no public customer name exists to show).
- `GET /v1/stores/{store_id}/rating-summary` —
  average rating (mean, rounded half-up to 2dp),
  total visible review count, and 5/4/3/2/1-star
  counts, over the same visible set as the public
  list. A store with no public reviews returns
  average null and all counts zero, never a fabricated
  5.0. Note: there is no database aggregate yet, so
  the summary fetches only the rating column for one
  store and aggregates in Python (pilot-scale; a
  database view is proposed in architecture.md, not
  applied). Marketplace responses are unchanged.

See `../docs/architecture.md` for the full review
audit, visibility rules, and the proposed view.

## Milestone 8 routes: secure pickup verification

The database is authoritative for every collection.
Both endpoints use the caller's user-context client and
the approved RPCs only — no service-role access, no
private-table queries, no client-side status change.

- `POST /v1/orders/{order_id}/pickup-token` —
  authenticated customer issues a one-time pickup token
  for their own eligible order (confirmed or
  ready_for_pickup, within pickup_ends_at + 30 minutes;
  unpaid, failed, pending, cancelled, expired, and
  already-collected orders are rejected by the RPC).
  Example response:
  ```json
  {
    "order_id": "55555555-5555-4555-8555-555555555555",
    "order_number": "SF-20261031-000001",
    "pickup_token": "<64-hex-token, shown once only>",
    "qr_payload": "SB1:<64-hex-token>",
    "expires_at": "2026-10-31T21:30:00Z",
    "pickup_starts_at": "2026-10-31T18:00:00Z",
    "pickup_ends_at": "2026-10-31T21:00:00Z",
    "store_name": "Sharma Foods Dwarka",
    "pickup_instructions": "Collect from counter"
  }
  ```
  The token is stored only as a SHA256 hash, so it
  cannot be retrieved later; issuing a fresh token
  invalidates previous unused ones. QR payload format:
  `SB1:<token>` — version prefix plus opaque token
  only, no personal, payment, or order data. The
  frontend renders this string as a QR code.
- `POST /v1/merchant/pickups/verify` — authenticated
  merchant verifies a token. Body:
  `{"store_id": "<uuid>", "pickup_token": "<token or SB1:token>"}`.
  The store_id is the store where the customer is
  standing; the database checks the caller's
  authorization for that store AND that the token's
  order belongs to it, so it is never trusted as
  authority. Allowed roles (database-enforced): merchant
  owner, merchant admin, store_manager,
  pickup_operator. NOT allowed: finance_viewer,
  inventory_manager. Example success response:
  ```json
  {
    "order_id": "55555555-5555-4555-8555-555555555555",
    "order_number": "SF-20261031-000001",
    "store_name": "Sharma Foods Dwarka",
    "status": "collected",
    "collected_at": "2026-10-31T18:30:00Z",
    "items": [{"title": "Evening Surprise Bag", "quantity": 2}]
  }
  ```
  Failures are privacy-safe and generic: invalid/
  expired/already-used tokens share one message,
  unpaid/cancelled/expired/wrong-store orders share
  another, outside-window is separate, and unauthorized
  store access is 403. A used token can never be
  replayed, and concurrent verifications are serialised
  by the RPC's row locks — two collections of one order
  are impossible.
- Customer order detail now includes `pickup_available`
  (true only for confirmed/ready_for_pickup orders
  within pickup_ends_at + 30 minutes). It does not say
  whether a token was issued, which is unreadable by
  design.

See `../docs/architecture.md` for the full RPC audit,
role table, and replay/expiry behavior.

## Milestone 7 routes: order management

Customer (authenticated, own orders only):

- `GET /v1/orders` — history, filters status,
  payment_status, created_from, created_to; newest first;
  page/page_size (max 100). List items: store summary,
  pickup window, item count, two-item preview.
- `GET /v1/orders/{order_id}` — full detail: amounts,
  store address + pickup instructions, pickup window,
  reservation expiry (pending orders), snapshot items
  with current public images, payment summary, and the
  real event timeline. Another customer's order returns
  the same 404 as a missing one.

Merchant (authenticated, authorized stores only):

- `GET /v1/merchant/orders` — filters store_id (can only
  narrow the authorized set), status, payment_status,
  pickup_from, pickup_to, order-number search; paginated.
  No customer personal information is returned.
- `GET /v1/merchant/orders/{order_id}` — merchant detail
  (same shape, including the customer's order note).
- `GET /v1/merchant/orders/summary` — counts over
  authorized stores: total, awaiting_payment, paid,
  upcoming_pickups, completed (collected),
  cancelled_or_expired.

Status honesty: pending_payment is not paid, captured is
not collected, confirmed is not ready_for_pickup; the
timeline contains only recorded order_status_events rows,
never guessed history. See `../docs/architecture.md`.

## Milestone 6 routes: Razorpay payments

- `POST /v1/orders/{order_id}/checkout` (authenticated,
  201, header Idempotency-Key): starts Razorpay checkout
  for a pending_payment order. Amount comes from the
  database (Decimal rupees -> paise), never from the
  request. Returns key_id, razorpay_order_id,
  payment_transaction_id, amount_paise, currency, and
  prefill email. No secret is returned.
- `POST /v1/payments/verify` (authenticated): body
  razorpay_order_id, razorpay_payment_id, razorpay_signature.
  Verifies the checkout signature against the order id
  fetched from Razorpay's API, fetches the payment
  server-side and requires captured + INR, resolves the
  transaction via the Razorpay order's notes, then calls
  backend_confirm_payment_capture with the provider amount.
  A signature alone never confirms; an authorized-only
  payment is rejected.
- `POST /v1/webhooks/razorpay` (no Supabase Auth; the
  webhook signature is the authentication): verifies
  X-Razorpay-Signature against the raw body with the
  webhook secret before parsing or acting (401 otherwise),
  records the event (deduped by gateway + event id), then
  payment.captured -> confirm, payment.failed ->
  mark_failed (never overwriting a capture), other events
  recorded and ignored.

Configuration (placeholders only; real secrets go in the
deployment environment, never in source or chat): see
`.env.example`. Required for deployment: RAZORPAY_KEY_ID,
RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET, plus the
existing SUPABASE_SERVICE_ROLE_KEY. Razorpay webhook URL:
https://<api-domain>/v1/webhooks/razorpay, events
payment.captured and payment.failed. See
`../docs/architecture.md` for the full lifecycle,
idempotency rules, the proposed (not applied) lookup RPC,
and the operational rule for reconciliation_required
payments.

## Milestone 5 routes: marketplace and reservations

Anonymous, read-only discovery — no bearer token needed:

- `GET /v1/marketplace/listings` — browse eligible public
  listings. Filters: city, pincode, category_id, listing_type,
  search, min_price, max_price, dietary. Sort: newest,
  lowest_price, highest_price, ending_soon (id tiebreak).
  Pagination: page, page_size (max 100). Response: items,
  total, page, page_size.
- `GET /v1/marketplace/listings/{listing_id}` — public details
  only (no created_by, contact phone, merchant internals, or
  payment data). Non-eligible listings return 404.
- `GET /v1/marketplace/categories` — active categories only.

Authenticated reservation — bearer token required:

- `POST /v1/orders/reservations` — body: store_id, items
  (1–20, unique listings, quantity 1–20 each), optional
  customer_note (max 1000 chars). Requires the
  `Idempotency-Key` header (8–128 chars, passed unchanged to
  the RPC). Calls only the approved user-context RPC
  `create_order_reservation`. Returns 201 with order_id,
  order_number, status (pending_payment), total_amount,
  currency, reservation_expires_at (~5 minutes, absent on
  idempotent replay), pickup window, and idempotent_replay.
  A reservation is NOT a paid or fully confirmed order.
  This endpoint never calls begin_payment_checkout and never
  writes orders, order_items, or inventory tables directly.

See `../docs/architecture.md` for the full anonymous-vs-
authenticated access rules, public field list, and the
pagination-at-scale limitation.

## Milestone 4 routes: listings and inventory

All routes require a Supabase Auth Bearer token and use the
user-context client only; the service-role client is never used
here. See `../docs/architecture.md` for the Stage 1 audit,
including the column-grant findings and the corrected
availability contract (generated column, no migration needed).

| Method | Route | Who can call it | Success |
| --- | --- | --- | --- |
| GET | `/v1/categories` | Authenticated user | 200, active categories only |
| POST | `/v1/stores/{store_id}/listings` | Merchant owner/admin, store_manager, inventory_manager | 201, always draft |
| GET | `/v1/stores/{store_id}/listings` | Any active merchant member | 200 |
| GET | `/v1/listings/{listing_id}` | Any active merchant member | 200 |
| PATCH | `/v1/listings/{listing_id}` | Same as create | 200, whitelisted columns only |
| POST | `/v1/listings/{listing_id}/publish` | Same as create | 200, draft/scheduled/paused → active |
| POST | `/v1/listings/{listing_id}/pause` | Same as create | 200, active → paused |
| POST | `/v1/listings/{listing_id}/resume` | Same as create | 200, paused → active |
| POST | `/v1/listings/{listing_id}/cancel` | Same as create | 200, any non-terminal → cancelled |
| GET | `/v1/listings/{listing_id}/inventory` | Any active merchant member | 200, read-only, computed available |
| GET | `/v1/listings/{listing_id}/images` | Any active merchant member | 200 |
| POST | `/v1/listings/{listing_id}/images` | Same as create | 201, registers a listing-media path |

Rules that matter, in plain terms:

- A listing is created as **draft**, always. The database does
  not let a merchant user set status on create, and this API
  never tries.
- **Cancel is a status change, not a delete.** There is no
  delete policy on listings, and there is no delete endpoint.
- **Inventory counters are never written by this API.**
  Reserved and sold counts change only through the database
  reservation functions. `available_quantity` is a generated
  column in the database — total − reserved − sold, recalculated
  by PostgreSQL automatically — and the API's response value
  uses the same formula, so it matches the stored value. The
  database activation check (available > 0 and a public store)
  is therefore evaluated against a real, maintained value, and
  the API checks the computed figure first and returns a clear
  422 when there is genuinely no stock. No trigger or migration
  is needed for availability; see the corrected architecture
  audit. (`published_at` is a separate, still-open issue.)
- **Images have no delete or edit endpoint**, because
  listing_images has no UPDATE or DELETE policy. Images are
  registered (after the caller uploads the file to
  `listing-media/<listing_id>/<file>` with their own token,
  JPEG/PNG/WebP, max 5 MB, enforced by the bucket) and listed.
- Money is Decimal throughout. Selling price must be positive;
  a selling price above the reference value is allowed,
  because the database explicitly permits it (it only checks
  >= 0) — the API does not invent a discount rule the database
  does not have.
- `sold_out` and `expired` are not settable through this API:
  no database code moves listings into those states yet.

### Milestone 4 local testing

```sh
cd backend
pytest -q tests/test_listings.py   # Milestone 4 only
pytest -q                           # full suite
```

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
