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
  render a designed unavailable state. No reservation
  or payment is started here — that is W3.

Detailed screens (checkout, listing editor, QR
scanner, live dashboards) belong to later milestones.

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

## Testing

- `apps/web/tests/`: marketplace helpers (pincode,
  price validation, discount math, labels, INR
  formatting, filter URL round-trip and rejection of
  unknown values), ListingCard (real values, computed
  discount, image fallback, no purchase action),
  layouts, config.
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
