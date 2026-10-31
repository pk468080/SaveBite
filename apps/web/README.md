# SaveBite website (`apps/web`)

Website-first frontend for SaveBite. One website serves
the public site, the customer app, the merchant portal,
and the platform admin portal. It consumes the existing
FastAPI backend (`backend/`) and the existing Supabase
project — it does not create a second backend, a second
database, or a second auth system.

## Stack

- Next.js 15 (App Router) + React 19 + TypeScript (strict)
- Tailwind CSS v4 (CSS-first config in `app/globals.css`)
- shadcn/ui-style primitives built on Radix UI (`components/ui/`)
- Lucide icons, Zod + React Hook Form
- Supabase Auth via `@supabase/ssr` (cookie sessions)
- Shared API client: `packages/api-client`
- Vitest + React Testing Library; Playwright foundation

## Run locally

```bash
# From the repository root (installs all workspaces):
npm install

# Copy the example env file and fill in your values:
cp apps/web/.env.example apps/web/.env.local

# Start the website (port 3000):
npm run web:dev

# Type-check, lint, test, production build:
npm run web:typecheck
npm run web:lint
npm run web:test
npm run web:build
```

## Environment

Client-safe variables only (see `apps/web/.env.example`):

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

Never put the Supabase service-role key, Razorpay
secrets, or database passwords in any env file here.
Missing variables fail loudly at the integration
boundary (see `lib/config.ts`); they are never
silently treated as configured.

## Authentication architecture

- Supabase Auth is the only identity provider.
- Sessions live in cookies via `@supabase/ssr`
  (`lib/supabase/` + root `middleware.ts` refresh).
- The website sends the current access token as
  `Authorization: Bearer <token>` to FastAPI
  (`lib/api/client.ts` + `packages/api-client`).
- App shells (`components/shared/app-shell.tsx`)
  redirect unauthenticated visitors to `/sign-in`.
  The admin shell additionally asks the BACKEND
  (`GET /v1/admin/dashboard`) whether the user may
  use admin APIs and redirects to `/unauthorized` on
  401/403. Navigation links are never a security
  mechanism: every backend API independently verifies
  permissions, merchant membership never counts as
  platform-admin access, and the M11 limitation still
  applies (only `operations_admin` and `super_admin`
  are verifiable through the admin API gate;
  `support_agent`, `finance_admin`, and
  `compliance_admin` remain restricted pending the
  approved database verification fix).
- No user id or role is ever trusted from local
  storage, query parameters, or frontend state.

## API client

`packages/api-client` is framework-independent so
future React Native apps can reuse it. It parses the
real FastAPI error envelope
(`{"error": {"code", "message", "request_id"}}`),
injects the Bearer token, supports timeouts,
cancellation, and idempotency keys, and exposes
typed service modules (marketplace, orders, payments,
pickup, reviews, merchants, merchant dashboard,
admin, notifications) whose routes are the verified
backend routes from milestones M2–M12. It contains
no business rules: the backend remains the authority.

## Route map

W1 shells and placeholders:

Public: `/` (homepage), `/marketplace` (placeholder),
`/sign-in`, `/sign-up`, `/unauthorized`.
Customer shell: `/customer`, `/customer/orders`,
`/customer/notifications`.
Merchant shell: `/merchant`, `/merchant/orders`,
`/merchant/listings`, `/merchant/inventory`,
`/merchant/analytics`, `/merchant/notifications`.
Admin shell: `/admin`, `/admin/merchants`,
`/admin/stores`, `/admin/orders`, `/admin/payments`,
`/admin/reviews`, `/admin/activity`.
Global: `not-found`, `global-error`, `loading`.

W2 public marketplace (real, guest-accessible):

- `/` — homepage: hero with city/pincode entry (plain
  GET form, so the location lands in a shareable URL),
  three-step How It Works, categories from the real
  category endpoint, "Ending soon" and "Newly listed"
  sections (labelled by their real backend sort, never
  "featured" or "popular"), sustainability/trust
  section with no invented statistics, footer without
  fabricated contact or legal links.
- `/marketplace` — discovery page: URL-synced search
  (debounced), city, pincode, single category, listing
  type, dietary, price range, sort, pagination. The URL
  query string is the single source of filter truth
  (back/forward work, filters reset pagination, stale
  responses cannot overwrite newer results). Desktop
  sidebar + mobile filter drawer share one FilterPanel
  component with distinct input ids per instance.
- `/marketplace/[listingId]` — public detail page:
  images, price + reference value with discount only
  when reference exceeds selling, availability, sale
  and pickup windows, allergens, storage, public store
  summary, store rating summary, and public visible
  reviews (no reviewer names exist in the API contract
  and none are invented). Ineligible/missing listings
  render a designed unavailable state. Reservation
  and payment start from the detail page's Add to
  cart action (W3) — the page itself still creates
  no reservation or payment.

W3 customer purchase journey (real, authenticated):

- `/sign-in`, `/sign-up` — Supabase Auth only, with
  password visibility toggles, password confirmation
  on sign-up, and a `?next=` redirect that is honoured
  only for same-site paths (no open redirect).
  `/forgot-password` + `/reset-password` complete the
  Supabase recovery flow (one-time code exchanged for
  a recovery session; expired links report as such).
- `/customer` — account overview: identity from
  `GET /v1/me`, recent orders, unread count.
- `/customer/profile` — read-only by design: no
  backend endpoint supports editing profile fields,
  so none are invented and no browser writes to
  Supabase tables are made.
- `/cart` — one store per cart (the database
  enforces same-store reservations). Adding another
  store's item opens a deliberate Replace-cart dialog;
  items are never silently dropped. Prices shown are
  display values; availability can be refreshed from
  live listings. The cart is NOT a reservation.
- `/customer/checkout` — creates one reservation from
  the cart (or pays an existing `?orderId=` pending
  order; retries never create a second order), shows
  the backend's order number, totals, pickup window,
  and a live countdown from the returned absolute
  expiry. Then opens Razorpay Checkout with the
  server-provided key, order id, amount, and currency.
- `/customer/orders/[orderId]/payment` — payment
  result from the re-read backend order only: success
  only when payment is captured and the order is
  confirmed/ready_for_pickup; reconciliation_required
  is a neutral verification message, never success and
  never a refund promise.
- `/customer/orders` — history, newest first, with
  order-status and payment-status filters and
  pagination (URL-synced).
- `/customer/orders/[orderId]` — detail with
  order-time item snapshots (never live prices),
  store address + pickup instructions, payment summary
  kept separate from fulfilment status, and only real
  recorded timeline events. Another customer's order
  returns the same safe not-found page as a missing one.
- `/customer/notifications` — M12 read APIs only:
  list, unread count badge in the customer nav, mark
  one as read, mark all as read. No preferences form:
  PATCH preferences returns 501 (not persisted), so a
  form would imply settings save, which they do not.

Detailed screens (listing editor, QR scanner, live
dashboards) belong to later milestones.

## Public marketplace: API contract (verified, W2)

Endpoints (all anonymous, no Supabase session):

- `GET /v1/marketplace/listings` — params: `city`
  (exact store-city match, case-insensitive),
  `pincode` (pattern `^[1-9][0-9]{5}$`), `category_id`
  (single UUID only — the API does not support
  multi-category), `listing_type`
  (`surprise_bag` | `individual_item`), `search`
  (title/description/contents substring), `min_price`
  / `max_price` (non-negative, min ≤ max),
  `dietary` (`vegetarian` | `non_vegetarian` |
  `vegan` | `egg` | `unknown`), `sort` (`newest` |
  `lowest_price` | `highest_price` | `ending_soon`),
  `page`, `page_size` (default 20, max 100).
  Response: `{items, total, page, page_size}`.
- `GET /v1/marketplace/listings/{id}` — 404 for any
  listing that is not currently eligible; existence
  of ineligible listings is not leaked.
- `GET /v1/marketplace/categories` — active
  categories only, ordered by display_order then name.
- `GET /v1/stores/{id}/rating-summary` — visible
  reviews only; `average_rating` is null (never a
  fabricated 5.0) when there are no public reviews.
- `GET /v1/stores/{id}/reviews` — visible only,
  sorts `newest` | `highest` | `lowest`, optional
  `rating` filter. Fetched ONLY on the detail page,
  never per listing card.

Listing images: the API returns a STORAGE PATH in
the public `listing-media` bucket, never a URL. The
frontend resolves it as
`{SUPABASE_URL}/storage/v1/object/public/listing-media/{path}`
(`lib/marketplace.ts`), and Next.js `remotePatterns`
in `next.config.ts` allow exactly that host and path
prefix. Listings without images show a placeholder
visual, never fake photography.

Location behavior: visitors type a city or pincode;
nothing is assumed, no geolocation, no IP inference,
no distance sorting (the backend does not offer it).
The chosen location is reflected in the URL.

## SEO

- Homepage: unique title/description, Open Graph,
  canonical `/`.
- Marketplace: static title/description, canonical
  `/marketplace` (bare URL, so arbitrary filter
  combinations do not create duplicate indexable
  URLs).
- Listing detail: dynamic metadata from the real API
  response (title, description, main image, canonical
  `/marketplace/{id}`, Open Graph). Structured data
  is deliberately NOT emitted yet: the API does not
  supply every field a Product/Offer schema would
  require, and no value is invented to fill it.
- `app/robots.ts`: public routes allowed; customer,
  merchant, admin, auth, and API routes disallowed.
- `app/sitemap.ts`: static public routes plus real
  listing URLs from the marketplace API (paginated,
  capped at 500, hourly revalidation, static-only
  fallback if the backend is unreachable).

## Customer checkout: API contract and rules (verified, W3)

All contracts below were read from the backend source
(`backend/app/routers/`, `backend/app/schemas.py`),
not assumed from the brief. The W1 api-client types
for orders, reservations, and checkout were wrong
placeholder shapes and were corrected in W3.

- `GET /v1/me` → `{ id, email, platform_roles }`.
  Identity comes from the verified session only.
- `POST /v1/orders/reservations` (auth, requires
  `Idempotency-Key: 8–128 chars of [A-Za-z0-9_-]`):
  body `{ store_id, items: [{ listing_id, quantity }],
  customer_note? }`; 1–20 unique listings, quantity
  1–20 each, same-store enforced by the database.
  Returns `{ order_id, order_number, status,
  total_amount, currency, reservation_expires_at,
  pickup_starts_at, pickup_ends_at,
  idempotent_replay }`. On a replay,
  `reservation_expires_at` is null (the RPC replay
  carries no expiry) — the frontend then re-reads
  the order detail for the authoritative expiry
  instead of inventing one.
- `POST /v1/orders/{order_id}/checkout` (auth,
  requires `Idempotency-Key`, 201): returns only safe
  fields `{ order_id, payment_transaction_id, key_id
  (public), razorpay_order_id, amount_paise, currency,
  prefill_email? }`. The amount comes from the
  database; the frontend never calculates it.
  Retrying with the same key returns the same
  transaction instead of a second Razorpay order.
- `POST /v1/payments/verify` (auth): body
  `{ razorpay_order_id, razorpay_payment_id,
  razorpay_signature }`. The backend verifies the
  signature, fetches the payment from Razorpay,
  requires captured + INR, and confirms through the
  approved RPC. `verified: true` does NOT by itself
  mean the order is confirmed: the RPC routes amount
  mismatches and non-live reservations to
  `reconciliation_required`, so the frontend always
  re-reads the order detail after verification before
  showing success. A Razorpay callback alone never
  marks an order paid.
- `GET /v1/orders` (auth, own orders only): filters
  `status`, `payment_status`, `created_from`,
  `created_to`; pagination `page`/`page_size`.
  `GET /v1/orders/{order_id}`: detail with snapshot
  items, payment summary (`amount_paid` is the total
  only when captured, else 0), store detail,
  `reservation_expires_at`, `pickup_available`, and
  the real `timeline` events. Other customers' orders
  return the same 404 as missing ones.
- `GET /v1/notifications`, `/unread-count`,
  `POST /{id}/read`, `POST /read-all` (M12, own
  records only). Generation is not active; there are
  no fake notifications.

### Idempotency-key lifecycle

One logical attempt gets one key, generated once
(`crypto.randomUUID` without dashes) and stored in
`sessionStorage` for that attempt: retries,
re-renders, and StrictMode double effects all reuse
it. A deliberate new attempt (new cart contents, or
a fresh checkout after abandoning the previous one)
gets a fresh key. Keys are never generated per render
and never stored in `localStorage`. See
`lib/idempotency.ts`.

### Reservation lifecycle and expiry

The cart is cleared once the backend confirms the
reservation, so the same cart cannot create a second
one; the reservation reference lives in
`sessionStorage` so a refresh recovers it. The
countdown is driven only by the returned absolute
expiry and recomputed from `Date.now()` each tick,
so a suspended tab shows the true remaining time.
When it reaches zero, the order is re-read from the
backend — the frontend never changes the order to
paid, confirmed, or cancelled itself, and never
assumes an expired reservation has been released
until the backend state confirms it. A closed
Razorpay window proves nothing: the order is
re-read, and only then is a retry offered (pending
payment) or success shown (captured).

### Razorpay Checkout integration

`lib/razorpay.ts` loads the official script
(`https://checkout.razorpay.com/v1/checkout.js`)
exactly once per page lifetime (concurrent callers
share one promise; a failed load clears it so a
retry can try again). Checkout opens with the
server-provided key, Razorpay order id, amount, and
currency, plus prefill email only when the backend
supplied one. No key secret, webhook secret, or
provider payload ever enters browser code. Ambiguous
cases (network loss after provider capture, failed
verification) preserve the order reference, re-read
the order, and show the backend state.

### Security invariants

Supabase Auth is the only identity provider; no
client-supplied user id is trusted; no service-role
key, Razorpay secret, or webhook secret is in
browser code or bundles (verified by the bundle
scan in the W3 report); no direct browser writes to
business tables; no client-side payment confirmation
or inventory deduction; no duplicate reservation
from retries.

## Testing

- `apps/web/tests/`: marketplace helpers (pincode,
  price validation, discount math, labels, INR
  formatting, filter URL round-trip and rejection of
  unknown values), ListingCard (real values, computed
  discount, image fallback, no purchase action),
  layouts, config, plus W3: cart rules (same-store
  guard, quantity clamps, 20-item cap, fingerprint,
  malformed stored carts), order-status labels and
  countdown math, Razorpay loader (single script
  injection, immediate resolve when loaded).
- `packages/api-client/tests/`: W3 service contracts
  (reservation body + idempotency header, checkout
  header, verify body, order-list filters).
- `apps/web/e2e/`: Playwright specs against
  `e2e/stub-api.mjs` (fixed fixture responses in the
  real API shapes, port 8000) plus the Next dev
  server. The stub exists only so e2e can run
  without a live Supabase project; it is NOT a
  backend replacement, and e2e passing does not claim
  a live-backend test. Run:
  `npx playwright install chromium` once, then
  `npx playwright test` in `apps/web` (requires
  `apps/web/.env.local` from `.env.example`).
  W3 extends the stub with mocked Supabase Auth
  (password grant, user, refresh), in-memory
  reservations/orders, checkout initiation, payment
  verification, and notifications, and the specs
  inject a mocked Razorpay Checkout SDK — so the
  journey spec is a MOCKED end-to-end test, not a
  production payment test. E2E runs the dev server
  with Supabase pointed at the stub (see
  `playwright.config.ts`); if a stale dev server is
  already running on port 3000 with older env or
  code, stop it first — Playwright reuses existing
  servers. The stub does not serve listing image
  bytes, so image 404 warnings in e2e output are
  expected and harmless.

## Known limitations (W2)

- No dedicated public store page: the backend has no
  public store-detail endpoint, so store information
  lives on the listing detail page. Proposed later
  backend task: a public store endpoint if a full
  store profile page is wanted.
- No multi-category filter, no distance sorting, no
  geolocation: none are supported by the backend.
- No structured data on listing pages (see SEO).
- The W1 `lib/api/client.ts` combined module was
  split into `lib/api/browser.ts` (client) and
  `lib/api/server.ts` (server): importing the server
  Supabase client from a client component failed the
  production build. The old path remains as
  re-exports for server imports only.
- Two latent W1 bugs fixed in W2: (1) `lib/config.ts`
  used dynamic `process.env[name]` indexing, which
  Next.js does not inline into browser bundles, so
  every browser config read threw; values are now
  read with static property access at module load.
  (2) The shared ApiClient stored bare `fetch`, which
  loses its Window binding in browsers ("Illegal
  invocation"); it now uses `fetch.bind(globalThis)`.

## Design system

Tokens live in `app/globals.css` (brand green
primary, warm neutrals, radius/shadow conventions,
light theme + dark theme via OS preference, no JS
toggle in W1). Primitives in `components/ui/`:
Button, Input, Select, Checkbox, Dialog,
DropdownMenu, Card, Badge, Table, Tabs, Skeleton,
Toast, Alert, Loading/Empty/Error states. Brand
treatment is text + icon only: no official logo
exists in the repository and none is invented.

## Testing

- `packages/api-client/tests/`: token injection,
  error-envelope parsing, 401/403 classification,
  idempotency keys, network failure, cancellation.
- `apps/web/tests/`: public header, app navigation
  (longest-prefix active rule), shared states, env
  validation (missing vars reported, secrets never
  listed as required client config).
- Playwright foundation (`apps/web/e2e/`): browsers
  are NOT installed by `npm install`; run
  `npx playwright install chromium` once before
  `npx playwright test` in `apps/web`.

## Known limitations (W1)

- ESLint uses a standalone flat config, not
  `eslint-config-next`: that package's bundled
  `@rushstack/eslint-patch` fails to load under this
  npm-workspaces install for both `next lint` and
  the ESLint CLI. Coverage is equivalent (recommended
  JS + TypeScript + React Hooks rules). Revisit if a
  future `eslint-config-next` fixes the patch.
- The production build shows the standard Next.js
  warning that the Next.js ESLint plugin was not
  detected; it does not block the build.
- Unauthenticated app-shell redirects are delivered
  by Next.js as a streamed page carrying a
  `NEXT_REDIRECT` instruction and a meta refresh to
  `/sign-in` (standard behaviour when a redirect is
  thrown inside a Suspense boundary); browsers follow
  it. Verified in the production smoke test.
