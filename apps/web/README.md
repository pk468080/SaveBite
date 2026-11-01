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

W4 merchant portal (real, authenticated; backend
is the final permission authority — hiding a
button is never treated as security):

- `/merchant` — M10 dashboard: store selector
  (hidden for single-store merchants, "all stores"
  only where the endpoint supports it), date range,
  total/paid/awaiting/collected orders, captured
  order value (labelled as captured payments only,
  never earnings or payouts), active listings,
  available/reserved units, upcoming/in-window/
  completed/window-expired pickups (window-expired
  is never called "missed" — no no-show event
  exists), average rating with a null-average
  honest empty state. No-merchant users are routed
  to onboarding, never shown operations.
- `/merchant/onboarding` — application form using
  only the real M3 fields (legal name, display
  name, business type from the 10-value enum,
  optional business email/phone). Submission
  reports pending review; approval is admin-only
  and never implied by the portal.
- `/merchant/application` — per-merchant status
  (pending_review, additional_information_required,
  approved, rejected, suspended) plus the separate
  verification status (pending, under_review,
  verified, rejected, expired). Document upload is
  honestly unavailable here (see Known
  limitations, W4).
- `/merchant/stores`, `/merchant/stores/new`,
  `/merchant/stores/[storeId]`,
  `/merchant/stores/[storeId]/hours` — store list
  from the caller's memberships only; create with
  the real StoreCreate validation (slug pattern,
  6-digit pincode starting 1–9, latitude/longitude
  both-or-neither, Indian mobile format); detail
  assembled from the membership store lists because
  the backend has no single-store GET endpoint;
  weekly hours editor over weekday numbers 0–6
  (the backend never confirms whether 0 is Monday
  or Sunday, so day names are never guessed, and
  M10 `open_now` stays null for the same reason).
- `/merchant/listings`, `/merchant/listings/new`,
  `/merchant/listings/[listingId]`,
  `/merchant/listings/[listingId]/edit` — both
  listing types (surprise_bag, individual_item).
  Creation always starts as a draft (the backend
  never accepts a client-sent status). Publish,
  pause, resume and cancel follow the backend
  transition map exactly (draft/scheduled →
  active/cancelled, active → paused/cancelled,
  paused → active/cancelled, sold_out/expired →
  cancelled, cancelled → nothing); backend
  refusals are shown as returned. Edit uses PATCH
  with only updateable fields (type, store,
  currency and counters are immutable). Available
  quantity is the database generated value
  (total − reserved − sold), displayed read-only.
- Listing images — the file is first uploaded by
  the browser to the public `listing-media` bucket
  at `<listing_id>/<file>` (JPG/PNG/WebP, max
  5 MB, `upsert: false`, caller's own token, bucket
  policy authorises store operators), then
  registered via `POST /v1/listings/{id}/images`
  with a storage_path that must start with the
  listing id. Images can never be edited or deleted
  through the API (INSERT/SELECT only) and the
  portal says so.
- `/merchant/inventory` — read-only visibility:
  M10 inventory summary plus the per-listing
  table (total/reserved/sold/available, sale and
  pickup dates, status filter). The low-stock
  threshold input is a reporting filter only; no
  automatic low-stock status is invented and no
  direct inventory adjustment exists.
- `/merchant/orders`, `/merchant/orders/[orderId]`
  — M7 queue and detail: order number, store,
  order/payment statuses kept distinct, order-time
  item snapshots, pickup window, totals, real
  timeline only. Filters: store, order status,
  payment status, order-number search, pagination.
  Customer email, phone and address are absent by
  design (the merchant API excludes them) and are
  never shown. No merchant status change, cancel
  or refund action exists in this scope.
- `/merchant/pickups` — `POST
  /v1/merchant/pickups/verify` with the raw token
  (the backend strips the `SB1:` prefix itself).
  Camera scanning uses BarcodeDetector +
  getUserMedia only after permission, with manual
  token entry as the fallback for denial or
  unsupported browsers; in-flight and last-token
  guards stop duplicate requests from repeated
  frames, the input is cleared after every attempt,
  and tokens are never logged or stored. Success
  is shown only from the backend response (order
  number, store, collected_at, items); invalid,
  expired, already-used, wrong-store and
  out-of-window failures show the backend's safe
  messages. No order is ever marked collected
  locally.
- `/merchant/analytics` — M10 sales buckets
  (day/week/month grouping) with captured value
  never labelled earnings, inventory summary,
  pickup counts and orders, and a store comparison
  table when the caller has more than one store.
- `/merchant/reviews` — public visible reviews
  only, average rating, star distribution and star
  filter. No reviewer names exist in the contract
  and none are invented; no edit, delete, approve,
  hide or reply action exists for merchants.
- `/merchant/notifications` — M12 read APIs only
  (list, unread badge, mark read, mark all read).
  Generation is not active yet and preferences are
  not persisted (PATCH returns 501), so no
  preferences form is offered.
- `/merchant/settings` — honest read-only page:
  memberships and stores as reported, plus the
  notification-preference and document-submission
  limitations. No staff invitation or role
  management exists in the backend, so none is
  built.

## Merchant portal: API contract and roles (verified, W4)

Endpoints used, all under `/v1`: merchant
applications (`POST /merchants/applications`,
`GET /merchants`, `GET /merchants/{id}`), stores
(`POST /merchants/{id}/stores`,
`GET /merchants/{id}/stores`, `GET|PUT
/stores/{id}/hours`), categories (`GET
/categories`, auth, active only), listings
(`POST /stores/{id}/listings`,
`GET /stores/{id}/listings`, `GET|PATCH
/listings/{id}`, `POST
/listings/{id}/publish|pause|resume|cancel`,
`GET /listings/{id}/inventory`, `GET|POST
/listings/{id}/images`), merchant orders (`GET
/merchant/orders`, `/summary`, `/{id}`), pickup
verify (`POST /merchant/pickups/verify`),
dashboard (`GET /merchant/dashboard`, `/sales`,
`/inventory`, `/pickups`, `/stores`), reviews
(public store reviews + rating-summary), and
notifications (M12 read APIs). Listing window
rules enforced by the backend and mirrored in
form validation: sale_ends > sale_starts when
given, pickup_ends > pickup_starts, pickup_ends
>= sale_ends, best_before >= prepared_at when
both set; selling_price > 0, reference_value >=
0, total_quantity > 0; allergen codes are
format-validated only (lowercase
`^[a-z0-9_-]+$`), there is no closed allergen
list. Role matrix (backend-enforced; the portal
only mirrors it): store create is owner/admin;
listing management is owner/admin or
store_manager/inventory_manager with an active
merchant membership; hours update is owner/admin
or store_manager with membership; order and
dashboard views are owner, admin,
store_manager, pickup_operator, finance_viewer
(inventory_manager is NOT a dashboard/order
role); finance viewers get no listing or pickup
authority from the portal, and inventory managers
get no dashboard/order access. Selected-store
state in localStorage (`savebite_merchant_store_v1`)
is validated against the loaded memberships on
every load and never treated as proof of access.

## Customer pickup QR and merchant collection (W5, M8)

- `/customer/orders/[orderId]` — the Pickup card
  now carries a pickup QR section. The customer
  must deliberately click "Show Pickup QR"; the
  page never issues a token on load. The button
  appears only when the order is confirmed or
  ready_for_pickup and its payment is captured
  (a display gate only — the backend re-checks
  status, payment, window and ownership on every
  issuance). Ineligible orders show a plain
  reason instead (pay first, already collected,
  no longer eligible, not ready yet).
- Issuance uses `POST /v1/orders/{id}/pickup-token`
  and renders the backend-returned `qr_payload`
  (`SB1:<64-hex-token>`) with `qrcode.react`
  (QRCodeSVG, high-contrast black on white, large
  mobile-first size). The token lives in component
  memory only: never localStorage, sessionStorage,
  cookies, URLs or logs, never shown as visible
  text, and cleared when the code is hidden, the
  order changes, or the view unmounts. The screen
  shows order number, store, pickup window,
  expiry (pickup end + 30 minutes, per the
  backend), instructions, a do-not-share reminder,
  and an accessible label plus screen-reader text.
  "Request a fresh code" warns first that the
  current unused code will stop working; if a
  fresh-code request fails, the old code is also
  cleared rather than left on screen as if valid,
  because it may already have been invalidated
  server-side. Failed first requests show the
  backend message and keep the button for a
  deliberate retry — issuance is never retried
  automatically, since every issuance invalidates
  the previous unused token.
- `/merchant/pickups` (W5 improvements on the W4
  page): a scanned value must now be exactly a
  SaveBite QR payload (`SB1:` + 64 hex chars) or
  it is rejected before any backend call — a
  decode is never a collection. Manual entry
  validates the same 64-hex token format locally
  (the backend route rejects anything else before
  its RPC). A failed scan keeps scanning instead
  of going silent; a successful scan stops the
  camera. The success box links to the collected
  order, and order pages refetch on navigation so
  the collected status shows on both sides. The
  backend still owns every check (token, store
  authorization, payment, window — verification
  runs from pickup start − 15 minutes to pickup
  end + 30 minutes — and one-time atomic
  collection), and its collapsed failure messages
  ("invalid, expired, or already used",
  "cannot be collected", "outside the pickup
  window") are shown as-is. Verify roles are the
  backend's: owner/admin plus store_manager and
  pickup_operator; finance_viewer and
  inventory_manager cannot verify.
- Order status synchronization needs no polling
  or realtime: customer detail and history pages
  are server-rendered and refetch on every
  navigation, and merchant pages fetch on mount,
  so a backend-confirmed collection shows as
  collected everywhere on the next visit. Nothing
  is ever marked collected optimistically.
- Security invariants: no token is generated in
  JavaScript, no token is persisted, logged, or
  sent anywhere except the two backend endpoints,
  and no service-role key or payment secret is in
  client bundles. No migration, RLS change,
  backend change, or live Supabase change was
  made in W5.

## Admin portal: implementation map (verified, W6, M11)

The W1 admin shell already had a server-side
gate (GET /v1/admin/dashboard; 401/403 redirect
to /unauthorized) plus sidebar navigation, the
signed-in user's email, and sign-out. W6 fills
the placeholder pages with real functionality.
Every permission check stays in the backend:
the gate admits only operations_admin and
super_admin, because the platform_user_roles
SELECT policy lets only those two roles read
the role table. support_agent, finance_admin,
and compliance_admin exist as role names in the
database but are denied by the gate until a
backend fix (own-row read policy or a
verification RPC) is approved — the portal
never grants them access, never lets a user
pick a role, and never treats a client-side
role value as proof. Client pages also handle
401/403 from any admin request as access
denied, once, without retrying.

What the backend actually supports (and W6
builds, nothing more):

- `/admin` — platform overview from GET
  /v1/admin/dashboard: merchant/store/listing/
  order counts, captured payment count, captured
  order value, failed/pending/reconciliation/
  refund-pending counts, visible-review count
  and average, recent orders (5). Captured
  order value is the sum of captured payments
  only and is labelled exactly that — never
  earnings, payouts, revenue, or profit. There
  is no customer count (profiles are readable
  only by their owner), so none is shown or
  estimated. Refresh re-reads; no polling.
- `/admin/merchants` — list with server-side
  status, verification-status, and display-name
  search filters (search covers display_name
  only, per the backend) plus pagination.
- `/admin/merchants/[id]` — detail from GET
  /v1/admin/merchants/{id} (application fields
  plus the merchant's stores) and the decision
  panel: approve or reject via POST
  /v1/admin/merchants/{id}/review, with a
  confirmation step, duplicate-submission
  guard, and a detail refetch after success —
  never an optimistic local status. Approval
  requires verification status verified plus a
  verified, current FSSAI document, both
  enforced by the backend RPC; a failed
  approval shows the backend's reason.
- `/admin/stores` — list with server-side
  status, city, pincode, and store-name search
  filters plus pagination.
- `/admin/stores/[id]` — detail from GET
  /v1/admin/stores/{id} (address, timezone,
  hours as weekday numbers — the backend never
  confirms whether weekday 0 is Monday or
  Sunday, so no day names are guessed — plus
  listing/order counts) and the activation
  panel: activate or deactivate via POST
  /v1/admin/stores/{id}/review, with the same
  confirmation, duplicate guard, and refetch.
  Activation requires an approved and verified
  merchant, a store location, and store hours,
  all enforced by the backend RPC.
- `/admin/orders` — read-only list with
  server-side order-number, order-status, and
  payment-status filters plus pagination.
- `/admin/orders/[id]` — read-only detail:
  items, pickup window, collected time,
  customer note when returned, and the recorded
  status timeline. No customer personal data is
  returned by this endpoint, so none is shown.
- `/admin/payments` — two read-only tabs:
  payment exceptions (GET /v1/admin/payments,
  order-level only — no gateway ids,
  signatures, or provider payloads) and refunds
  (GET /v1/admin/refunds, refund-related orders
  only; refund-pending is NOT refunded, and no
  refund amount is estimated beyond the order
  total). No refund execution exists, so no
  refund button is shown.
- `/admin/reviews` — READ-ONLY list with
  rating and moderation-status filters. There
  is NO review moderation endpoint and NO
  moderation RPC in the backend: reviews are
  immutable through the API, and the reviews
  SELECT policy hides hidden and under_review
  rows from platform admins, so this list shows
  visible reviews in practice. No hide, restore,
  edit, or delete action is offered — inventing
  one would be a fake. Moderation needs a
  separate backend change (a moderation RPC
  plus a policy letting administrators see
  non-visible rows).
- `/admin/activity` — recorded
  order_status_events only (GET
  /v1/admin/activity, order-number search).
  Private audit logs, pickup events, and
  webhook events are not exposed by the API
  and no audit-log screen is fabricated.

Deliberately NOT built in W6 (no supporting
endpoint exists): review moderation actions,
role or user management, order status changes,
refund or payout execution, store suspension
beyond activate/deactivate, listing management
actions (GET /v1/admin/listings is read-only
and has no page in W6), audit-log viewing,
and any access for support, finance, or
compliance roles. No migration, RLS change,
backend change, or live Supabase change was
made in W6.

## Notifications: implementation map (verified, W7, M12)

W7 activates in-app notifications end to end. The
customer and merchant notification pages already
showed real records from the M12 read APIs; W7
adds generation, delivery, persistent preferences,
and pickup reminders. No email, SMS, push, or
WhatsApp delivery exists.

How generation works (no frontend creation):

- Database triggers enqueue jobs into
  private.notification_outbox in the SAME
  transaction as the business change, so a
  notification can never be created for a
  rolled-back operation, and a committed
  operation cannot lose its notification to a
  crash between the business commit and a
  separate emission call.
- Order payment captured: the customer gets
  payment_captured and the merchant recipients
  get new_paid_order. Payment failed: the
  customer gets payment_failed. Payment
  reconciliation required: operations and super
  admins get payment_reconciliation_required.
  Order collected: the customer gets
  pickup_completed and the merchants get
  merchant_pickup_completed.
- Merchant application submitted, approved, or
  rejected, and store activated or deactivated,
  notify the merchant recipients and, for
  application events, the platform admins.
- Recipients come only from authoritative
  database relationships: the order customer,
  active owner/admin merchant members, active
  store managers and pickup operators, the
  merchant applicant, and non-revoked
  operations/super admins. Never from request
  data. No route and no frontend code creates
  notifications, and public.notifications has
  no INSERT policy for callers.

How delivery works:

- A standalone worker (backend/app/
  notification_worker.py) calls
  backend_enqueue_pickup_reminders and then
  backend_process_notification_outbox through
  the service-role client. Run it continuously
  or with --once from a scheduler; it holds no
  queue state, so killing it loses nothing.
- The processor claims a bounded batch with
  FOR UPDATE SKIP LOCKED, so concurrent
  workers claim disjoint sets, and reclaims
  jobs stuck in processing past 10 minutes.
- Delivery is at-least-once per event and
  recipient, with exactly-once user-visible
  effect through the dedup key: a retried
  delivery cannot create a second row.
- Retry uses bounded exponential backoff
  (about 1, 2, 4, 8 minutes, capped at 30),
  at most 5 attempts; the 5th failure leaves
  the row failed, which is never reclaimed
  (the dead-letter state). One bad payload
  cannot roll back the rest of a batch.
- Preferences are checked at delivery: a
  category the recipient disabled is skipped,
  never delivered. Mandatory categories
  (payment_updates, operational_alerts) are
  always delivered.

Pickup reminders:

- The worker enqueues reminders for confirmed
  or ready_for_pickup orders with payment
  captured, when now falls inside
  [pickup_starts_at - 60 minutes,
  pickup_starts_at). Comparisons use absolute
  instants; the store timezone affects display
  only. Collected, cancelled, expired, unpaid,
  and past-window orders are never reminded,
  and one order gets at most one reminder
  (dedup key pickup_reminder:{order_id}).

Preferences in the interface:

- /customer/notifications and
  /merchant/notifications each show a
  preferences section with only that
  audience's categories, backed by GET and
  PATCH /v1/notifications/preferences.
  Mandatory categories render locked on.
  Toggles are a draft until Save succeeds:
  "Saved" appears only after the API
  confirms, and a failed save shows the error
  with no saved confirmation.

Deliberately NOT built in W7 (no supporting
business trigger exists):

- Reservation notifications: notifying on an
  unpaid reservation is forbidden by the
  product rule, so reservation_created is
  never emitted. Reservation expiry has no
  running sweeper, order cancellation has no
  route, and refunds have no route caller, so
  no expiry, cancellation, or refund
  notification exists. Each needs a real
  business trigger first, not just a new
  notification type.
- External channels: outbox rows for push,
  email, SMS, and WhatsApp remain dormant;
  the processor claims in-app rows only.
- Worker deployment and migration
  application: the worker command and the
  three migration files exist in this PR, but
  no production worker or scheduler is
  configured and no migration is applied to
  live by this PR. Until both land, no
  notification is delivered in production.

## Known limitations (W4)

- No merchant-facing document-upload endpoint
  exists: FSSAI verification is admin-side only,
  enforced in the review RPC. The portal shows a
  clear "document submission is not yet available
  through the portal" message and never works
  around it with direct Supabase storage writes
  to a public bucket. Separate backend task if
  merchant uploads are wanted.
- No single-store GET endpoint: store detail is
  assembled from the caller's membership store
  lists; a store id outside those lists renders
  not-found.
- Listing images cannot be edited or deleted
  (INSERT/SELECT policy only); no image edit or
  delete UI is offered.
- Store-hours weekday convention (0 = Monday vs
  Sunday) is unverified in the backend, so the
  hours editor shows weekday numbers and M10
  `open_now` is always null; never guess day names.
- No merchant payout, settlement, refund,
  delivery, staff-invitation, or review-reply
  capability: none exists in the backend for W4.
- E2E does not cover image upload or
  registration: the stub serves no Supabase
  Storage, so neither the bucket upload nor the
  registration call is exercised in Playwright;
  both need a manual check against a real bucket
  before launch.

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
  records only). Generation is active since W7:
  database triggers enqueue in-app notifications
  for payment, collection, merchant application,
  and store events, delivered by the standalone
  worker; preferences are persistent via GET and
  PATCH /v1/notifications/preferences. There are
  no fake notifications and no external channels.

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
  header, verify body, order-list filters), plus W4
  merchant service contracts (application, store,
  hours, listing create/PATCH/transitions,
  inventory, image registration, dashboard, pickup
  verify request shapes).
- `apps/web/tests/merchant.test.ts`: W4 listing
  form validation (window rules, price/quantity,
  allergen format), transition map, slug/pincode
  patterns, pickup-token normalisation.
- `apps/web/e2e/merchant.spec.ts`: W4 mocked
  merchant journey (sign-in, dashboard, Surprise
  Bag draft, publish, inventory, seeded order
  queue + detail, pickup invalid + valid tokens,
  analytics, reviews) plus unauthorized-store
  not-found and a backend-refused transition
  after cancel. Image upload is excluded (see
  Known limitations, W4). W5 updates the spec's
  tokens to the real 64-hex format (valid stub
  token, well-formed unissued token).
- `apps/web/tests/pickup.test.ts` + `tests/pickup-qr-section.test.tsx`: W5 QR payload
  build/parse (SB1: + 64 hex only), eligibility
  gate and reasons, and the QR section component
  (request-on-click only, QR renders, raw token
  never visible as text, duplicate clicks send
  one request, ineligible orders show no button,
  failed issuance shows an error with deliberate
  retry, hide clears the code, fresh-code
  invalidation note, order change clears the
  token).
- `apps/web/e2e/pickup.spec.ts`: W5 mocked
  customer-to-merchant journey (eligible order,
  QR request + display, no token in browser
  storage, hide + fresh code, merchant manual
  verification of the fresh code, collected
  status on customer refetch, already-used
  rejection) plus invalid-token refusal and
  ineligible-order gating. The spec learns the
  mocked token from the stub issuance response
  (the way a merchant learns it by scanning);
  no real camera hardware is used.
- `packages/api-client/tests/admin-services.test.ts`:
  W6 admin service contracts (dashboard URL,
  merchant/store list filters and pagination,
  merchant review body, store review body,
  order/payment/refund/review/activity
  endpoints).
- `apps/web/tests/admin.test.ts` +
  `tests/admin-dashboard.test.tsx` +
  `tests/admin-review-panel.test.tsx` +
  `tests/admin-reviews.test.tsx`: W6 admin
  labels, dashboard rendering (real backend
  fields, captured value never labelled as
  earnings or revenue, refresh re-reads, 403
  shows access denied once without retry,
  backend failure shows an error not an empty
  dashboard), review panels (confirmation
  before acting, one API call per decision,
  duplicate submissions blocked, failure leaves
  the shown status untouched, success asks the
  parent to re-read), and the reviews page
  (visible row renders, no moderation buttons
  exist).
- `apps/web/e2e/admin.spec.ts`: W6 mocked admin
  journey (sign-in, dashboard counts and honest
  captured-value labelling, merchant list to
  detail to approve with confirmation and
  backend refetch, store list to detail to
  activate, order list to detail, payments and
  refunds tabs, reviews read-only, activity
  events) plus the standalone access-denied
  page. Real role authorization is enforced by
  the backend gate, not by these mocks.
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
