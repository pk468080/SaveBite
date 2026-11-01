# SaveBite — Supabase migrations

## Live project

- Product: SaveBite (India-focused hybrid surplus-food marketplace)
- Supabase project: surplus-food-marketplace
- Project ref: `zehnhqcfawagxbactvne`
- Project URL: https://zehnhqcfawagxbactvne.supabase.co
- Region: ap-south-1 (Mumbai)
- PostgreSQL 17, status ACTIVE_HEALTHY at inspection on 2026-10-31

## Remote migration history — 15 entries (verified live)

These are the migrations already applied to the live project, read from
`supabase_migrations.schema_migrations` on 2026-10-31. Do not re-apply them,
do not renumber them, and do not edit them in place.

| Version | Name |
|---|---|
| 20261031052859 | core_marketplace_schema |
| 20261031052926 | commerce_inventory_and_finance |
| 20261031052957 | support_safety_and_operations |
| 20261031053137 | row_level_security_and_access_policies |
| 20261031053406 | marketplace_transaction_functions |
| 20261031053431 | storage_buckets_and_access_policies |
| 20261031053621 | rpc_hardening_and_fk_indexes |
| 20261031053649 | database_testing_and_function_grants |
| 20261031053823 | reservation_timestamp_cast_fix |
| 20261031054026 | public_discovery_policy_hardening |
| 20261031054132 | merchant_store_admin_workflows |
| 20261031054200 | refund_workflow |
| 20261031054222 | immutable_double_entry_ledger |
| 20261031054250 | refund_status_checker_cleanup |
| 20261031054340 | refund_events_fk_index |

## Migration-history mismatch — read this before any `db push`

**Local vs remote do not match by file, and that is expected here.**

The SaveBite GitHub repository was empty when Milestone 1 started, so it
contained none of the 15 original migration files. The original migration
SQL is not recoverable from the live database — only the versions and names
above can be read back. Reconstructing 15 files and pretending they are the
originals would be fabrication.

Instead, this directory contains one consolidated file:

- `20261031060000_remote_schema_baseline.sql` — a tracking copy of the
  current live schema, generated 2026-10-31 by introspecting
  `pg_catalog` / `information_schema` via the Supabase Management API
  (read-only). It is NOT one of the 15 remote migrations.

**Do NOT apply this baseline to the live project.** The live project already
has every object in it. Running `supabase db push` with this file against
live would fail on duplicate objects and is forbidden by the project stop
conditions, as are `db reset`, DROP, and any destructive DDL.

The baseline's purpose is repository tracking and code review only:
future app code and the generated types in `packages/types` can be checked
against the real schema without recreating it.

**How future migrations must work:** new changes go in NEW migration
files with a later timestamp, with a written change plan and explicit
approval first. A developer linking this repo locally must first run
`supabase link --project-ref zehnhqcfawagxbactvne` with their own access
token (never committed, never pasted in chat), then verify that the
remote history still shows the 15 entries above before pushing anything.

## W7 and W8 files — NOT applied to live

These files exist in this directory only. They have never been
applied to the live project, and this PR does not apply them.
Apply them in timestamp order, in one release, through the
approved process (see docs/w8-production-readiness), and
only then start the notification worker:

- `20261101120000_w7_notification_preferences.sql` (W7)
- `20261101121000_w7_notification_outbox.sql` (W7)
- `20261101122000_w7_notification_delivery.sql` (W7)
- `20261101130000_w8_notification_dedup_per_recipient.sql` (W8:
  per-recipient dedup keys; without it, multi-recipient
  events deliver to the first recipient only)
- `20261101131000_w8_notification_rpc_grants.sql` (W8:
  service-role-only EXECUTE on the two worker RPCs)

## B1 file — NOT applied to live

- `20261101180000_b1_checkout_gateway_lookup.sql` (B1:
  server-only `backend_get_gateway_order_for_payment_transaction`
  lookup for checkout retry recovery; service-role-only
  EXECUTE). This file only records the change. Before
  relying on checkout retries, verify at apply time with
  has_function_privilege that only service_role holds
  EXECUTE on it, and apply it in timestamp order after
  the W7 and W8 files (which remain pending their own
  approved process).

## Worker RPC revoke file — NOT applied to live

- `20261101190000_notification_worker_rpc_revoke_anon_authenticated.sql`
  (revokes EXECUTE on the two W7 worker RPCs from anon
  and authenticated. The W8 grants file only revoked
  PUBLIC, but Supabase default privileges grant EXECUTE
  directly to anon and authenticated at creation, so
  those direct grants survived it. This file only records
  the change. Apply it in timestamp order after the W7
  and W8 files, and verify at apply time with
  has_function_privilege that only service_role holds
  EXECUTE on both functions. Live remediation is handled
  separately; this PR does not apply anything.)

Before applying, verify at apply time: the notifications
type CHECK against live rows, EXECUTE privileges for
anon / authenticated / service_role on both worker RPCs,
and the live storage-bucket policies (not reproduced in
the baseline SQL).

## W9.1 file — NOT applied to live

- `20261101200000_w91_reservation_expiry.sql` (W9.1:
  tiered, bounded, idempotent expired-reservation
  cleanup — new `private.release_expired_reservations_v2`
  plus `public.backend_release_expired_reservations_v2`,
  service-role-only EXECUTE). This file only records
  the change; it does not apply anything, repair
  migration history, or touch the W7/W8/B1/revoke
  files or the consolidated baseline. Prerequisites:
  baseline tables only. Postconditions to verify at
  apply time: both functions exist with the documented
  signatures, and has_function_privilege shows EXECUTE
  only for service_role (and the owner) on the public
  function. The v1 cleanup functions are left intact;
  the new worker operation
  (backend/app/reservation_cleanup.py) calls v2, and
  no worker or scheduler is deployed by this PR.

## Baseline verification (live counts, 2026-10-31)

The consolidated file was checked against the live database:

- Tables: 41 (25 public + 16 private) — matches live
- Enum types: 16 (91 labels) — matches live
- Constraints: 204 — matches live
- Policies: 41 — matches live
- Functions: 45 (25 private implementations + 20 public wrappers/helpers)
- Triggers: 12 — matches live
- Non-constraint indexes: 86 — matches live
- RLS: enabled on all 25 public tables; disabled on all 16 private tables
  (private is service-role-only and must not be exposed through the API)
- Storage buckets: avatars (public), listing-media (public),
  incident-evidence (private), merchant-documents (private)
- Function grants recorded live for anon / authenticated / service_role:
  60 routine-privilege rows (summarised here, not reproduced as GRANT
  statements in the baseline)

Known limits of the consolidated pull:

- Some foreign-key definitions are unqualified in `pg_get_constraintdef`
  output (for example `REFERENCES merchants(id)`) and rely on the live
  `search_path` resolving them to `public`. The same applies to some
  trigger function references (`set_updated_at()`). This is faithful to
  the live definitions, not a change to them.
- Table/column GRANT statements and storage-bucket policies are not
  reproduced in the baseline SQL; they are summarised above and must be
  re-checked with the Supabase advisors after any approved schema change.
- Data state at inspection: 15 categories seeded; merchants, stores,
  listings, orders, profiles and service areas all 0. No demo data was
  added to fill discovery — real merchant onboarding must create it.
