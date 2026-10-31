# SaveBite

India-focused hybrid surplus-food marketplace: Surprise Bags and individual
surplus items, customer pickup only (no delivery in MVP), one FastAPI
backend and one Supabase database shared by a customer app, a merchant
portal and an admin portal.

**This repository is the canonical codebase for SaveBite. Do not mix it
with KvikStaff or the separate Bachao Bag project.**

## Project identity

- Brand: SaveBite
- Supabase project: surplus-food-marketplace
- Project ref: `zehnhqcfawagxbactvne`
- Project URL: https://zehnhqcfawagxbactvne.supabase.co
- Region: ap-south-1 (Mumbai, India)
- Database: PostgreSQL 17

## Milestone 1 only — what is in this commit

This commit is Milestone 1 (repository inspection + schema baseline +
generated types) only. No UI screens, no FastAPI backend, no Expo app and
no Next.js portals are built yet.

- `supabase/config.toml` — project reference for local Supabase CLI use.
  It contains no secret. Linking still requires the developer's own
  access token locally (see below).
- `supabase/migrations/README.md` — the 15 verified remote migration
  entries, the local-vs-remote mismatch explanation, and baseline
  verification counts.
- `supabase/migrations/20261031060000_remote_schema_baseline.sql` —
  consolidated tracking copy of the live schema. **Do NOT apply it to
  the live project** (see the migrations README for why).
- `packages/types/src/database.ts` — TypeScript types generated from the
  live public schema (25 tables, 16 enums, 19 public RPCs). The private
  schema is deliberately not typed here: it is service-role-only and must
  only be reached from FastAPI, never from browser / Expo code.

## Database contract (do not rename)

- Default API schema: `public`; protected tables and privileged
  implementation functions: `private`.
- Unified listing model: `public.listings` with `listing_type` =
  `surprise_bag` or `individual_item`. Do not create separate
  order/payment systems for the two listing types.
- User-context RPCs (signed-in user's JWT, never service-role):
  `apply_merchant_application`, `create_merchant_store`,
  `upsert_store_hours`, `create_order_reservation`,
  `begin_payment_checkout`, `issue_pickup_token`, `verify_pickup_token`,
  `request_refund`.
- Server-only RPCs (`backend_*`, FastAPI only, after auth, authorisation,
  validation and gateway verification): `backend_attach_gateway_order`,
  `backend_mark_payment_failed`, `backend_confirm_payment_capture`,
  `backend_record_payment_webhook_event`,
  `backend_release_expired_reservations`, `backend_review_merchant`,
  `backend_review_store`, `backend_update_refund_status`,
  `backend_post_ledger_transaction`, `backend_reverse_ledger_transaction`.

## Environment rules

- Client apps: publishable key only (`EXPO_PUBLIC_SUPABASE_URL`,
  `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`).
- FastAPI only: `SUPABASE_SERVICE_ROLE_KEY`, `RAZORPAY_KEY_ID`,
  `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`.
- Never paste secrets in chat, never commit them, never expose the
  service-role key in Expo / Next.js browser code, build logs or prompts.
  The owner copies keys from Supabase Settings into deployment secrets.

## Local Supabase CLI linking (developer step, not committed)

```sh
supabase link --project-ref zehnhqcfawagxbactvne
```

Use your own Supabase access token for this step. After linking, verify
the remote migration history still shows the 15 entries in
`supabase/migrations/README.md` before pushing any new migration.
Never run `supabase db reset`, `supabase db push` against live without a
written change plan and explicit approval, and never run destructive DDL.

## Stop conditions

Stop and report before: changing database design, changing live RLS,
adding a new payment provider, implementing deliveries, altering the
order/payment state machines, weakening security, or running destructive
Supabase commands. The approved schema is the integration contract.
