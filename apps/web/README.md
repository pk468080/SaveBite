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

## Route map (W1 — shells and placeholders)

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

Detailed screens (marketplace UI, checkout, listing
editor, QR scanner, live dashboards) belong to later
milestones; W1 pages state which backend endpoint
will feed them.

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
