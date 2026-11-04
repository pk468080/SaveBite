# W9.1.4 — RPC Permission Boundary Correction

Base: main `35b5dcec3289fd9b1dfedee67a6bfc1e8725b228` (merge of PR #28,
W9.1.3, 2026-11-03). Branch: `fix/w9-1-4-private-schema-permissions`.
PR: unmerged, against `main` (see §14). Nothing in this document was
applied to staging or production, and production was never contacted.

Status words in this document follow the brief exactly: PASSED means
executed and passed, FAILED means executed and failed, BLOCKED means
a required environment was unavailable, NOT TESTED means not executed,
STATIC REVIEW ONLY means inspected without execution.

## 1. Original 403 failure

W9.1.3 (docs/w9-1-3-staging-validation.md §3) found, while building a
real PostgREST harness, that the first real PostgREST call to a public
`backend_*` wrapper failed with:

```
403 permission denied for schema private
```

Root cause, verified from the migration files (not from live, which
was never inspected — see the caveat below):

- Every public `backend_*` wrapper is `LANGUAGE sql`,
  `SECURITY INVOKER` (`pg_proc.prosecdef = false` for all of them),
  with a pinned empty `search_path`, and its body is a single call
  to a `private.*` function.
- An invoker wrapper therefore requires the CALLER to hold `USAGE`
  on schema `private` and `EXECUTE` on the private function. The
  chain fails at name resolution before any function body runs.
- No migration in the chain grants `USAGE ON SCHEMA private` to
  anyone (grep over all `supabase/migrations/*.sql` finds nothing).
- The same invoker structure applies to the eight user-context
  wrappers, so the defect is not backend-only: any wrapper path
  whose caller lacks schema `USAGE` fails the same way.

Caveat, repeated because it matters: W9.1.3 did NOT independently
inspect the live production privilege state, and neither does this
task. Everything in §3/§7 about "current" state is the
migration-chain state as replayed in a disposable database. If live
Supabase defaults or a manual grant already give a role schema
`USAGE`, the live failure mode differs in detail — the migration
below is still correct, because it states the intended state
explicitly instead of relying on defaults.

A second defect rides along with the first: every private function
keeps PostgreSQL's default `PUBLIC EXECUTE` privilege, because no
migration ever revoked it. The missing `USAGE` grant was, until now,
the only thing stopping `anon`/`authenticated` from calling private
functions directly in any context where they hold schema `USAGE`
(or after any future broad grant). Fixing only the `USAGE` line, as
W9.1.3's disposable test did, would have fixed the symptom and
left that wider exposure in place. This task fixes both together.

## 2. Full public-to-private RPC graph

All function definitions were read from every migration file (the
baseline tracking copy plus the nine later migrations), from
`backend/app/supabase_client.py` (the RPC allowlists), and from
every router/worker call site. Security mode and search_path below
come from the definitions themselves, never from a name.

### 2.1 Public wrappers and their private callees

| Public wrapper | Mode / search_path | Private callee | Expected caller (PostgREST) | Business operation |
| --- | --- | --- | --- | --- |
| `public.apply_merchant_application(text, text, merchant_business_type, text, text)` | invoker / `''` | `private.apply_merchant_application` (definer) | authenticated | Merchant application; inserts merchant + owner membership; enforces `auth.uid() is not null` |
| `public.create_merchant_store(uuid, text×9, double precision×2, text×2)` | invoker / `''` | `private.create_merchant_store` (definer) | authenticated | Store creation; enforces `is_merchant_member` |
| `public.upsert_store_hours(uuid, jsonb)` | invoker / `''` | `private.upsert_store_hours` (definer) | authenticated | Store hours; enforces `can_manage_store` |
| `public.create_order_reservation(uuid, jsonb, text, text)` | invoker / `''` | `private.create_order_reservation` (definer) | authenticated | Customer reservation; enforces `auth.uid()`, store/merchant availability, inventory |
| `public.begin_payment_checkout(uuid, text)` | invoker / `''` | `private.begin_payment_checkout` (definer) | authenticated | Checkout initiation; enforces order ownership |
| `public.issue_pickup_token(uuid)` | invoker / `''` | `private.issue_pickup_token` (definer) | authenticated | Pickup token; enforces order ownership + status |
| `public.verify_pickup_token(uuid, text)` | invoker / `''` | `private.verify_pickup_token` (definer) | authenticated | Pickup verification; enforces `can_manage_store` |
| `public.request_refund(uuid, text, text)` | invoker / `''` | `private.request_order_refund` (definer) | authenticated | Refund request; enforces `auth.uid()` |
| `public.backend_attach_gateway_order(uuid, text)` | invoker / `''` | `private.attach_gateway_order` (definer) | service_role | Attach Razorpay order to a payment transaction |
| `public.backend_confirm_payment_capture(uuid, text, numeric, boolean)` | invoker / `''` | `private.confirm_payment_capture` (definer) | service_role | Payment capture; enforces `p_signature_verified is true` |
| `public.backend_mark_payment_failed(uuid, text, text)` | invoker / `''` | `private.mark_payment_failed` (definer) | service_role | Payment failure recording |
| `public.backend_post_ledger_transaction(text, uuid, text, character, jsonb)` | invoker / `''` | `private.post_ledger_transaction` (definer) | service_role | Ledger posting (balanced entries, known accounts) |
| `public.backend_record_payment_webhook_event(text, text, text, jsonb, boolean)` | invoker / `''` | `private.record_payment_webhook_event` (definer) | service_role | Webhook event audit row (idempotent by gateway event id) |
| `public.backend_release_expired_reservations(integer)` | invoker / `''` | `private.release_expired_inventory_reservations` (definer) | service_role | Legacy (v1) expiry release — no tier rules; the cleanup worker uses v2 only and must never call v1 |
| `public.backend_reverse_ledger_transaction(uuid, text, uuid)` | invoker / `''` | `private.reverse_ledger_transaction` (definer) | service_role | Ledger reversal; itself calls `private.post_ledger_transaction` (definer-nested, owner context) |
| `public.backend_review_merchant(uuid, merchant_status, verification_status, text, uuid)` | invoker / `''` | `private.review_merchant_application` (definer) | service_role | Admin merchant review; reviewer platform-role checked against `platform_user_roles` for `p_reviewer_id` |
| `public.backend_review_store(uuid, boolean, uuid, text)` | invoker / `''` | `private.review_store_activation` (definer) | service_role | Admin store activation review; same reviewer check |
| `public.backend_update_refund_status(uuid, refund_status, uuid, text, text, text)` | invoker / `''` | `private.update_refund_status` (definer) | service_role | Refund status transition; actor platform-role checked for `p_actor_user_id` |
| `public.backend_process_notification_outbox(text, integer)` | **definer** / `''` | none (reads/writes `private.notification_outbox` directly) | service_role | Notification worker: claim + deliver in-app outbox batch |
| `public.backend_enqueue_pickup_reminders(timestamptz, integer)` | **definer** / `''` | none (inserts into `private.notification_outbox` directly) | service_role | Notification worker: enqueue due pickup reminders |
| `public.backend_get_gateway_order_for_payment_transaction(uuid, uuid)` | invoker / `''` | `private.get_gateway_order_for_payment_transaction` (definer) | service_role | B1 checkout-retry lookup; transaction must match both ids and be Razorpay, else `payment_transaction_not_found` |
| `public.backend_release_expired_reservations_v2(integer)` | invoker / `''` | `private.release_expired_reservations_v2` (definer) | service_role | Cleanup worker: tiered expiry release (never touches authorised/captured money) |

Notes on the graph:

- The two W7 processor functions are the ONLY public wrappers that
  are `SECURITY DEFINER`. They need no private-function grant, and
  they are also the two functions that "trust their caller"
  (W8 header): the processor can claim/cancel/retry/dead-letter any
  in-app job, and the reminder function trusts caller-supplied
  `p_now`/`p_window_minutes`. That is exactly why their wrapper
  `EXECUTE` must remain service-role-only — the definer body runs
  as the function owner.
- `backend_release_expired_reservations` (v1) has no worker caller
  (the cleanup worker calls v2, and its own header says never call
  v1), but it IS in the backend allowlist
  (`backend/app/supabase_client.py` `BACKEND_RPCS`), so it stays a
  legitimate service-role RPC and is granted accordingly. Removing
  it from the allowlist is a separate code decision, not a
  permission-migration decision.
- `backend_post_ledger_transaction`,
  `backend_reverse_ledger_transaction` and
  `backend_update_refund_status` likewise have no route caller today
  (W7 header: `request_refund` has no route caller and
  `backend_update_refund_status` has no caller), but they are in the
  allowlist as finance/admin backend operations. They are granted
  to service_role only, not removed.
- No public wrapper calls a private function other than its own
  implementation, except the nested private-to-private calls in
  §2.3. There is no wrapper that reaches a second private function
  through its caller identity.

### 2.2 Private functions, classified

29 private functions exist in the chain (26 baseline + 3 later:
`w7_enqueue_notification`, `get_gateway_order_for_payment_transaction`,
`release_expired_reservations_v2`).

1. **Called by service-role backend wrappers (12):**
   `attach_gateway_order`, `confirm_payment_capture`,
   `mark_payment_failed`, `post_ledger_transaction`,
   `record_payment_webhook_event`,
   `release_expired_inventory_reservations`,
   `reverse_ledger_transaction`, `review_merchant_application`,
   `review_store_activation`, `update_refund_status`,
   `get_gateway_order_for_payment_transaction`,
   `release_expired_reservations_v2`. All `SECURITY DEFINER`,
   pinned empty `search_path`.
2. **Called by authenticated customer/merchant wrappers (8):**
   `apply_merchant_application`, `begin_payment_checkout`,
   `create_merchant_store`, `create_order_reservation`,
   `issue_pickup_token`, `request_order_refund`,
   `upsert_store_hours`, `verify_pickup_token`. All
   `SECURITY DEFINER`, pinned empty `search_path`, all enforcing
   authorisation inside the body via `auth.uid()` and/or
   `can_manage_store` / `is_merchant_member`.
3. **Called by anonymous/public operations (0 via RPC; 3 via RLS):**
   No private function is the target of an anonymous RPC wrapper.
   Three functions are called by RLS policies during anonymous
   table reads (see §2.4): `is_store_public`, `can_manage_store`,
   `has_platform_role`. All are `STABLE`, `SECURITY DEFINER`,
   pinned empty `search_path`, read-only boolean checks.
4. **`SECURITY DEFINER` internal functions (27):** every private
   function except the two trigger functions in class 5 that are
   invoker. In particular the five RLS helpers are all
   `STABLE SECURITY DEFINER`.
5. **Trigger functions (3 private + 4 public):**
   Private: `handle_new_auth_user` (definer; the auth.users
   trigger function — no trigger on an application table in this
   chain attaches it, it belongs to the auth system),
   `prevent_posted_ledger_entry_mutation` (invoker),
   `prevent_posted_ledger_transaction_mutation` (invoker).
   Public: `w7_enqueue_order_notifications`,
   `w7_enqueue_merchant_notifications`,
   `w7_enqueue_store_notifications` (all definer, firing on
   orders/merchants/stores transitions) and `set_updated_at`
   (invoker, firing on every `*_set_updated_at` trigger).
6. **Private helpers called only by other private functions:**
   `post_ledger_transaction` (called by
   `reverse_ledger_transaction`), `can_manage_store` and
   `has_platform_role` (called by `can_view_order`,
   `upsert_store_hours`, `verify_pickup_token`),
   `is_merchant_member` (called by `create_merchant_store`),
   `w7_enqueue_notification` (called only by the definer trigger
   functions and the definer outbox processor). Nested calls from
   a definer function run as the function owner, so they do NOT
   need a separate grant to the outer caller — but
   `post_ledger_transaction`, `can_manage_store`,
   `has_platform_role`, `is_merchant_member` are also granted
   directly where a wrapper or RLS path needs them, and
   `w7_enqueue_notification` is granted to nobody.
7. **Must never be directly callable by application roles:**
   `w7_enqueue_notification` (outbox writer),
   `prevent_posted_ledger_*` (trigger-only),
   `handle_new_auth_user` (auth-system-only), and every
   server-only implementation for `authenticated`/`anon`, and
   every customer/merchant implementation for `service_role`/
   `anon` (see §7).

### 2.3 Private-to-private and nested-call rules that decide grants

- Invoker wrapper → definer implementation: the wrapper call is
  checked against the caller (needs schema `USAGE` + `EXECUTE` on
  the private function); once inside, the definer body runs as the
  owner, so its table access and its nested private calls are
  checked against the owner, not the caller.
- Definer trigger → definer helper (`w7_*` triggers →
  `w7_enqueue_notification`): runs as the trigger owner; the
  original DML caller needs no grant on the helper. Revoking
  helper `EXECUTE` from application roles therefore cannot break
  triggers — proven by Test 8.
- Definer implementation → definer helper (`can_view_order` →
  `can_manage_store`/`has_platform_role`): same owner-context
  rule; the RLS grants in §7 are needed for direct policy
  evaluation, not for these nested calls.
- Trigger invocation itself does not check `EXECUTE` on the
  trigger function (PostgreSQL invokes trigger functions as the
  table owner). Revoking trigger-function `EXECUTE` from all
  application roles is therefore safe — proven by Test 8 — and
  removes a direct-RPC path to trigger functions.

### 2.4 RLS policies that call private functions

The baseline tracking copy's 41 policies are corrupted in one
mechanical way (the role list is rendered as
`to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, }`),
which is why the disposable bootstrap strips them; policy
*correctness* lives in the original live migrations, not in the
tracking copy, and this task does not rewrite any policy. What
the policy bodies show, and what the tests prove, is which
helpers a table read needs:

- Anonymous catalogue reads (listings, stores, store_hours,
  listing_images): policies call `is_store_public`,
  `can_manage_store`, `has_platform_role`.
- Authenticated reads: additionally `can_view_order`
  (orders/order_items/inventory_reservations) and
  `is_merchant_member` (merchants/stores/documents).
- `auth.uid()` in policies and in private bodies reads the JWT
  claims set by PostgREST (`request.jwt.claims`); `SECURITY
  DEFINER` does not clear that setting, so definer bodies still
  see the caller's identity. That is why converting wrappers to
  definer would not change nested authorisation — and why it was
  not needed (see §5).

## 3. Original permission model

From the migration chain (disposable replay; live state unproven):

- Schema `private`: `USAGE` granted to nobody by any migration.
  In a fresh replay the schema is owned by the migration owner
  and no application role holds `USAGE`.
- Private functions: no migration grants or revokes `EXECUTE`
  on any baseline private function, so all 26 carry default
  `PUBLIC EXECUTE`. Later migrations touch only public wrappers
  (W8 grants + the 20261101190000 revokes for the two W7 worker
  RPCs; B1 and W9.1/W9.1.1 for their own wrappers).
- Public wrappers: baseline wrappers carry default `PUBLIC
  EXECUTE`; the four newer server-only wrappers are
  service-role-only (W8/B1/W9.1/W9.1.1, with the W8 gap for direct
  anon/authenticated grants closed by the 20261101190000
  revokes). User-context wrappers carry default `PUBLIC
  EXECUTE` in the chain — the app allowlist, not the database,
  was the only thing separating user-context from server-only
  RPCs for direct PostgREST callers.
- `supabase/config.toml`: `schemas = ["public"]` only. Schema
  `private` is never exposed to PostgREST, so a direct
  `private.*` RPC is not a PostgREST endpoint even before this
  migration. The private grants below are defence in depth for
  any direct-SQL path and for a future config mistake, not the
  primary PostgREST control — the primary control is wrapper
  `EXECUTE` + schema `USAGE`.
- Backend allowlists (`backend/app/supabase_client.py`):
  `USER_CONTEXT_RPCS` (8 names) and `BACKEND_RPCS` (14 names, all
  `backend_*`); the service-role client rejects non-`backend_*`
  names and the user-context client rejects `backend_*` names
  before any HTTP call, and both reject any `private.*` table
  access. The database migration now enforces the same
  separation that the app code already claimed.

## 4. Security risks from default PUBLIC EXECUTE

1. **Direct private invocation if schema USAGE is ever granted
   broadly.** The W9.1.3 one-line fix, applied alone, would have
   made `service_role` work — but the same `USAGE` grant applied
   to the wrong role, or a future migration granting `USAGE` to
   `authenticated` for a new wrapper, would immediately expose
   every private function to that role, including
   `confirm_payment_capture` (which trusts
   `p_signature_verified`), `review_merchant_application` and
   `update_refund_status` (which trust a caller-supplied actor
   id, checked only against platform roles), and the ledger
   functions. `PUBLIC EXECUTE` makes the permission boundary
   rest on a single missing grant instead of on explicit grants.
2. **Wrapper EXECUTE wider than the allowlist.** Baseline
   `backend_*` wrappers were `PUBLIC`-executable in the chain.
   Any direct PostgREST caller — not just this repo's backend —
   could call `backend_confirm_payment_capture` with
   `p_signature_verified=true` without ever passing the webhook
   HMAC check, the router's gateway verification, or the RBAC
   reviewer rule, because the private body trusts that flag.
   (It would still have failed on schema `USAGE` in the replay
   — which is the only reason this was latent, not safe.)
3. **User-context wrappers callable by anon.** `create_order_
   reservation` etc. check `auth.uid() is not null` and would
   refuse an anonymous call, but defence in depth says the
   database should not even allow the call: an anonymous
   caller should get a permission denial, not a business-logic
   refusal that depends on every body keeping its auth check.
4. **Trigger/helper exposure.** `w7_enqueue_notification`
   writes directly to the notification outbox; if it were
   callable, any caller could forge notifications for any user.
   It is protected today only by not being in the public schema
   and by the missing `USAGE` grant — both accidents of layout,
   not grants.
5. **Future-function leakage.** Any private function added by a
   later migration inherits `PUBLIC EXECUTE` by default, and
   §6 proves that no `ALTER DEFAULT PRIVILEGES` clause closes
   that gap in PostgreSQL 17 — only an explicit per-function
   `REVOKE` in that function's own migration does.

## 5. Selected security design and alternatives rejected

### Selected: hybrid Option A (selective grants, invoker preserved)

- Grant `USAGE ON SCHEMA private` only to `authenticated` and
  `service_role`.
- `REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA private` from
  `PUBLIC`, `anon`, `authenticated` and `service_role`, then
  re-grant exactly the functions in §7 (this also removes any
  Supabase direct grants to `anon`/`authenticated`/`service_role`
  that a bare `REVOKE FROM PUBLIC` would miss — the exact gap
  the 20261101190000 migration closed for the two worker RPCs).
- Re-assert public wrappers: user-context → `authenticated`
  only; `backend_*` → `service_role` only; public trigger
  functions → nobody.
- No default-privileges clause (proven ineffective for this
  purpose in PostgreSQL 17 — see §6); future functions must
  revoke explicitly in their own migrations.
- No function is created, altered, or dropped; no owner, mode,
  search_path, signature, return type, policy, or trigger
  changes. The migration is grant/revoke-only, so it is
  idempotent (re-running a `GRANT`/`REVOKE` is a no-op) and its
  failure mode is loud: a grant on a missing function aborts
  the file instead of partially applying.

Why this is the safest design supported by the real graph:

- It preserves the existing authorisation model exactly. Every
  private body already enforces its own checks via `auth.uid()`
  and membership/role helpers, and every body already runs as
  definer with a pinned empty `search_path`. Nothing about
  RLS, `auth.uid()`, or trigger behaviour changes, so the
  regression surface is grants only.
- It keeps two independent gates on every path: wrapper
  `EXECUTE` (who may call the public name) AND private
  `EXECUTE` + schema `USAGE` (who may resolve the
  implementation). Removing either gate alone no longer opens
  the path.
- It is the smallest change that fixes both defects (missing
  `USAGE` + default `PUBLIC EXECUTE`) without touching business
  logic.

### Option A alone (selective grants, as above) — adopted, with two extensions

The pure Option A in the brief is exactly what was adopted. The
two extensions beyond a minimal reading are (a) revoking from
`anon`/`authenticated`/`service_role` directly, not just
`PUBLIC`, because Supabase default privileges grant directly to
those roles; and (b) revoking public trigger-function `EXECUTE`,
because trigger invocation does not need it. Both are proven
safe by Tests 8–9.

### Option B (SECURITY DEFINER for server-only wrappers) — rejected

Converting the 12 invoker `backend_*` wrappers to definer would
remove the service-role private `USAGE`/`EXECUTE` requirement
for those paths — but:

- It would NOT remove the authenticated `USAGE`/`EXECUTE`
  requirement for the eight user-context wrappers (unless those
  were converted too, which the brief forbids indiscriminately
  and which would change the customer/merchant trust model).
  The schema grant to `authenticated` would still be needed, so
  the marginal benefit is small.
- The private bodies are already definer, so conversion changes
  no nested authorisation (`auth.uid()` still reads the JWT
  setting) — it only collapses the two gates into one. A future
  loosening of a single wrapper grant would then silently expose
  definer execution, including for the W7 processor-style
  trust-the-caller functions.
- The two W7 processor wrappers are already definer and already
  service-role-only; converting the rest would make the wrapper
  set inconsistent (some definer, some invoker) for no
  functional gain.
- Conversion is a function-definition change (new
  `CREATE OR REPLACE FUNCTION` per wrapper), which risks
  signature/search_path drift and is not idempotent in the same
  trivial way as grants. It is the right tool if a future
  wrapper must be callable by a role that must NOT hold private
  `EXECUTE` — that case does not exist in the current graph.

### The one-line fix — rejected as a complete solution

`GRANT USAGE ON SCHEMA private TO service_role` alone fixes the
W9.1.3 403 and is, in fact, included in §6 (service_role is one
of the two `USAGE` grantees). As a complete solution it is
rejected because it leaves default `PUBLIC EXECUTE` on all 29
private functions, leaves baseline `backend_*` wrappers
`PUBLIC`-executable, leaves user-context wrappers
`PUBLIC`-executable, and leaves future private functions
`PUBLIC`-executable by default. The 403 would be gone and the
boundary would be weaker.

## 6. New schema and function grants

File: `supabase/migrations/20261104120000_w914_rpc_permission_boundary.sql`
(forward-only, unapplied; see §11–§13).

Schema:

```sql
REVOKE USAGE ON SCHEMA private FROM PUBLIC;
REVOKE USAGE ON SCHEMA private FROM anon;
GRANT USAGE ON SCHEMA private TO authenticated;
GRANT USAGE ON SCHEMA private TO service_role;
```

Private functions (explicit signatures in the file; summaries here):

```sql
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA private FROM PUBLIC, anon, authenticated, service_role;
-- service_role (12): attach_gateway_order, confirm_payment_capture,
--   mark_payment_failed, post_ledger_transaction,
--   record_payment_webhook_event, release_expired_inventory_reservations,
--   reverse_ledger_transaction, review_merchant_application,
--   review_store_activation, update_refund_status,
--   get_gateway_order_for_payment_transaction, release_expired_reservations_v2
-- authenticated (8 + 5 RLS): apply_merchant_application,
--   begin_payment_checkout, create_merchant_store, create_order_reservation,
--   issue_pickup_token, request_order_refund, upsert_store_hours,
--   verify_pickup_token, can_manage_store, can_view_order,
--   has_platform_role, is_merchant_member, is_store_public
-- anon (3 RLS only): can_manage_store, has_platform_role, is_store_public
-- nobody: w7_enqueue_notification, prevent_posted_ledger_*,
--   handle_new_auth_user
```

Public wrappers:

```sql
-- user-context (8): REVOKE FROM PUBLIC, anon, service_role; GRANT TO authenticated
-- backend_* (14): REVOKE FROM PUBLIC, anon, authenticated; GRANT TO service_role
-- public trigger functions (w7_enqueue_*, set_updated_at):
--   REVOKE FROM PUBLIC, anon, authenticated, service_role; GRANT TO nobody
```

Future defaults: DELIBERATELY NO CLAUSE.

This was tested, not assumed, on disposable PostgreSQL 17.11:
`ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE EXECUTE ON
FUNCTIONS FROM PUBLIC` creates no `pg_default_acl` row and a
subsequently created private function is still
PUBLIC-executable (`has_function_privilege('anon', ...) = true`),
because default grants are unioned with the built-in PUBLIC
grant and a REVOKE in default privileges only removes grants
stored in the default ACL itself. The same holds for the
`FOR ROLE` variant, and granting a default to the owner does not
remove PUBLIC either (the new function's `proacl` still contains
the `=X` PUBLIC entry). The only removal that works is an
explicit `REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` per
function — exactly what §6 does for every existing function.
A default-privileges clause claiming otherwise would be
security theatre, so it is omitted on purpose, and Test 10
asserts the true behaviour. Consequence, stated plainly: every
future migration that creates a private function MUST include
its own explicit `REVOKE FROM PUBLIC` (and explicit `GRANT`s),
exactly as W8/B1/W9.1 already do for public wrappers.
Public-schema defaults are likewise untouched.

## 7. Role-by-role privilege matrix

`✓` = EXECUTE (or USAGE for the schema row). Owner always holds
EXECUTE on its own functions regardless of grants. Before = the
migration-chain state in a disposable replay (default `PUBLIC`
EXECUTE; no schema `USAGE` grants). After = after applying §6.
Every cell below is asserted by `test_privilege_matrix_matches_
migration` (Test 9) via `has_function_privilege`.

### Schema USAGE

| Schema | Before: PUBLIC / anon / authenticated / service_role | After |
| --- | --- | --- |
| `private` | — / — / — / — (owner only) | — / — / ✓ / ✓ |
| `public` | ✓ (Supabase/PG default; unchanged by this migration) | unchanged |

### Private functions (before: every cell ✓ via PUBLIC, except where noted)

| Private function | After: anon | After: authenticated | After: service_role | Why (wrapper / RLS / trigger) |
| --- | --- | --- | --- | --- |
| `attach_gateway_order` | — | — | ✓ | `backend_attach_gateway_order` |
| `confirm_payment_capture` | — | — | ✓ | `backend_confirm_payment_capture` |
| `mark_payment_failed` | — | — | ✓ | `backend_mark_payment_failed` |
| `post_ledger_transaction` | — | — | ✓ | `backend_post_ledger_transaction`; also nested from `reverse_ledger_transaction` (owner context) |
| `record_payment_webhook_event` | — | — | ✓ | `backend_record_payment_webhook_event` |
| `release_expired_inventory_reservations` | — | — | ✓ | `backend_release_expired_reservations` (v1, allowlisted) |
| `reverse_ledger_transaction` | — | — | ✓ | `backend_reverse_ledger_transaction` |
| `review_merchant_application` | — | — | ✓ | `backend_review_merchant` |
| `review_store_activation` | — | — | ✓ | `backend_review_store` |
| `update_refund_status` | — | — | ✓ | `backend_update_refund_status` |
| `get_gateway_order_for_payment_transaction` | — | — | ✓ | `backend_get_gateway_order_for_payment_transaction` |
| `release_expired_reservations_v2` | — | — | ✓ | `backend_release_expired_reservations_v2` |
| `apply_merchant_application` | — | ✓ | — | `apply_merchant_application` |
| `begin_payment_checkout` | — | ✓ | — | `begin_payment_checkout` |
| `create_merchant_store` | — | ✓ | — | `create_merchant_store` |
| `create_order_reservation` | — | ✓ | — | `create_order_reservation` |
| `issue_pickup_token` | — | ✓ | — | `issue_pickup_token` |
| `request_order_refund` | — | ✓ | — | `request_refund` |
| `upsert_store_hours` | — | ✓ | — | `upsert_store_hours` |
| `verify_pickup_token` | — | ✓ | — | `verify_pickup_token` |
| `can_manage_store` | ✓ | ✓ | — | RLS (listings/stores/hours/images; merchant ops) |
| `can_view_order` | — | ✓ | — | RLS (orders/items/reservations, authenticated only) |
| `has_platform_role` | ✓ | ✓ | — | RLS (catalogue + admin reads) |
| `is_merchant_member` | — | ✓ | — | RLS (merchant/store reads, authenticated only) |
| `is_store_public` | ✓ | ✓ | — | RLS (catalogue reads) |
| `w7_enqueue_notification` | — | — | — | Definer trigger/processor only; direct grant would forge notifications |
| `prevent_posted_ledger_entry_mutation` | — | — | — | Trigger-only; invocation needs no EXECUTE |
| `prevent_posted_ledger_transaction_mutation` | — | — | — | Trigger-only; invocation needs no EXECUTE |
| `handle_new_auth_user` | — | — | — | Auth-system trigger only |

Why no broader permission is necessary, per role:

- `service_role` bypasses RLS, so it needs no RLS-helper
  `EXECUTE`; it needs no customer/merchant implementation
  `EXECUTE`, because the app allowlist forbids the service-role
  client from calling user-context RPCs and the database now
  agrees (proven: service-role user-context calls are denied).
- `authenticated` needs no server-only implementation, because
  every server operation goes through the backend, which uses
  its own service-role identity after doing authentication,
  authorisation, validation and (for payments) gateway
  verification in application code.
- `anon` needs no business function at all: its only database
  surface is catalogue reads, whose policies need exactly the
  three boolean helpers. It needs no schema `USAGE` for those
  reads, because RLS policy evaluation invokes a `SECURITY
  DEFINER` helper as its owner (proven by Test 6 and by the
  negative control in `test_anon_rls_helpers_required`, which
  shows the read breaks if the three helper grants are removed
  and works again when restored — with `USAGE` denied throughout).
- No role needs `w7_enqueue_notification` or the trigger
  functions directly, for the reasons in §2.2 class 7.

### Public wrappers (before → after)

| Wrapper group | Before | After |
| --- | --- | --- |
| User-context (8) | PUBLIC | authenticated only |
| `backend_*` baseline (10) | PUBLIC | service_role only |
| `backend_process_notification_outbox`, `backend_enqueue_pickup_reminders` | service_role only (W8 + revokes) | service_role only (re-asserted) |
| `backend_get_gateway_order_for_payment_transaction` | service_role only (B1) | service_role only (re-asserted) |
| `backend_release_expired_reservations_v2` | service_role only (W9.1/W9.1.1) | service_role only (re-asserted) |
| Public trigger functions (`w7_enqueue_*`, `set_updated_at`) | PUBLIC | nobody (triggers unaffected) |

RLS-protected data: every private implementation that touches
`public.orders`, `private.payment_transactions`,
`private.payment_webhook_events`, `private.ledger_*` or
`private.notification_outbox` is definer and runs as the owner,
so RLS does not restrict the implementation itself — the
restriction is the wrapper `EXECUTE` gate plus the body's own
`auth.uid()`/membership/role checks. Table-level RLS still
governs direct PostgREST table reads by `anon`/`authenticated`,
unchanged by this migration.

## 8. Trigger compatibility test results

PASSED (Test 8, disposable PostgreSQL 17.11, after applying §6):

- A merchant `pending_review → approved` transition writes new
  rows to `private.notification_outbox` through
  `public.w7_enqueue_merchant_notifications` →
  `private.w7_enqueue_notification`, with no application role
  holding `EXECUTE` on either function (outbox count strictly
  increased across the transition).
- A balanced ledger transaction posted as service_role cannot
  be mutated: both the `ledger_transactions` row update and the
  `ledger_entries` row update are refused by the baseline
  `prevent_posted_ledger_*` triggers, with no application role
  holding `EXECUTE` on them.
- `set_updated_at` triggers were exercised implicitly by every
  fixture update in Tests 4–6 (no `updated_at` error surfaced);
  no dedicated `set_updated_at` timestamp assertion is claimed
  beyond that.

## 9. PostgREST integration results

PASSED (Stage G, real PostgREST 12.2.3 binary, real locally
minted JWTs with a throwaway per-session secret, disposable
PostgreSQL 17.11, `db-schemas = "public"`):

- Service-role `POST /rest/v1/rpc/backend_record_payment_webhook_event`
  returns 2xx and writes the event row (verified by the direct
  service-role call in Test 1 returning a new event id, and by
  the PostgREST test returning 2xx for the same RPC).
- Anonymous (no token) and authenticated (user JWT) calls to the
  same endpoint return 401/403/404, never 2xx.
- A `private.*` RPC path returns 404, proving schema `private`
  needs no PostgREST exposure: the test config uses
  `db-schemas = "public"`, matching `supabase/config.toml`.
- No service-only endpoint becomes publicly callable: the
  negative PostgREST tests above cover the webhook-event
  endpoint, and the direct-role Tests 2–3 cover the remaining
  server-only wrappers at the database layer.

## 10. RLS regression results

PASSED (Tests 4–6, disposable PostgreSQL 17.11):

- Authenticated reservation creation + checkout initiation work
  for the order owner through the public wrappers (reservation
  returns `pending_payment`; checkout returns a transaction).
- Authenticated merchant application + store creation work for
  an owner member (application returns a merchant id; store
  creation returns a store id).
- Another authenticated user cannot checkout the first user's
  order (function-level ownership check refuses).
- Anonymous catalogue reads (listings) still return the public
  row, via the three RLS helpers, with schema `USAGE` denied —
  proven both before the migration (PUBLIC EXECUTE helpers, no
  USAGE) and after it (explicit helper grants, no USAGE).
- Removing the three anon helper grants breaks the anonymous
  read, and restoring them fixes it — proving the grants are
  load-bearing, not decorative.
- Direct private invocation by anon is denied at the schema
  level even for the granted helpers (Test 7): the anon helper
  grants exist for RLS policy evaluation only, not for direct
  calls. Authenticated direct helper calls succeed (it holds
  schema `USAGE`).

## 11. Migration application preconditions

1. Apply in timestamp order after every earlier migration
   (baseline live equivalents, W7, W8, B1, W9.1, W9.1.1). Do
   NOT replay the consolidated baseline tracking copy
   (`20261031060000`) against any live database.
2. Roles `anon`, `authenticated`, `service_role` must exist.
3. Run as the function owner (Supabase: `postgres`) or a
   superuser; otherwise `REVOKE FROM PUBLIC` on owner functions
   fails and the file aborts — do not force it.
4. Staging first, with its own approval. Production approval is
   separate and is NOT granted by this PR.
5. After applying, run these verification queries (as the owner)
   and compare with §7 — every row must match:

```sql
SELECT has_schema_privilege('service_role', 'private', 'USAGE'),
       has_schema_privilege('authenticated', 'private', 'USAGE'),
       has_schema_privilege('anon', 'private', 'USAGE');
SELECT n.nspname, p.proname,
       has_function_privilege('anon', p.oid, 'EXECUTE') AS anon,
       has_function_privilege('authenticated', p.oid, 'EXECUTE') AS authenticated,
       has_function_privilege('service_role', p.oid, 'EXECUTE') AS service_role
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'private' ORDER BY 1, 2;
SELECT n.nspname, p.proname, p.prosecdef, p.proconfig, r.rolname
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
JOIN pg_roles r ON r.oid = p.proowner
WHERE n.nspname IN ('private', 'public') AND p.proname LIKE 'backend_%';
SELECT * FROM pg_default_acl WHERE defaclobjtype = 'f';
```

6. Scan for future-function leakage (see §6): no private
   function created after this migration may carry a PUBLIC
   (`=X`) entry in `proacl`. If one does, its own migration
   must add an explicit `REVOKE FROM PUBLIC` — do not add an
   `ALTER DEFAULT PRIVILEGES` clause, which does not work for
   this purpose in PostgreSQL 17.
7. Re-run the W9.1.4 test module against the staging database
   only if a disposable-equivalent harness is pointed at staging
   with explicit approval — never point the disposable test
   fixtures at production.

## 12. Staging verification commands

See §11, step 5, for the privilege queries. Functional staging
checks (each needs its own approval; none is done by this PR):

```bash
# After staging apply, from the staging backend (service-role key):
# 1. Webhook event recording + confirm + mark-failed via backend_* RPCs
# 2. Cleanup worker --once (backend_release_expired_reservations_v2)
# 3. Notification worker --once (both W7 RPCs)
# 4. Customer reservation + checkout via user-context RPCs
# 5. Anonymous catalogue read (listings) via the public API
# 6. Authenticated attempt at backend_record_payment_webhook_event
#    must fail (PostgREST 403), and anon attempt must fail
```

## 13. Production application restrictions

- Never apply this migration to production on the basis of
  disposable-database evidence alone. Production application
  needs a separate owner approval, a staging apply + verification
  first, and a live privilege check (the §11 queries) before and
  after.
- Never run `supabase db push` from this branch.
- Never repair migration history, change production secrets or
  configuration, deploy workers, initiate payments, or change
  the Razorpay dashboard as part of this task.
- Never merge this PR from the agent side; the owner merges on
  their side, as with W9.1–W9.1.3.

## 14. Remaining risks and follow-up actions

- **Live ACL state still unproven.** The migration states the
  intended state explicitly, so it is safe to apply even if live
  already differs in detail — but the §11 before/after check on
  staging (and, later, production) is mandatory, because a live
  direct grant that this file does not revoke (e.g. a grant to
  a role other than `PUBLIC`/`anon`/`authenticated`/
  `service_role`, or a grant on a future function) would survive
  it. The file revokes from exactly the four grantees the chain
  could have created; it does not audit arbitrary roles.
- **Future private functions default to PUBLIC EXECUTE.**
  See §6: no default-privileges clause can prevent this in
  PostgreSQL 17, so every future migration must revoke
  explicitly. The staging check should include a scan for any
  private function whose `proacl` contains a PUBLIC (`=X`) entry.
- **RLS policies from the tracking copy are not replayable.**
  The disposable tests strip the 41 corrupted baseline policies
  (same deviation as W9.1.2/W9.1.3) and re-create only the
  policies needed for the tested reads through the W7 prefs
  migration and the fixture data. Full RLS policy correctness
  still lives in the original live migrations and needs a
  staging check, not a disposable claim.
- **`begin_payment_checkout` and other auth-gated paths in
  production** still need a staging run with real Supabase
  `auth.uid()` (the disposable tests use a claims-aware stub
  with the documented Supabase semantics).
- **W7 dedup limitation carries forward** (second identical
  decision for the same entity reuses the dedup key; see the W7
  header) — unrelated to permissions, noted here so it is not
  lost.
- **No worker heartbeat / last-success record** (W9.1.3 §7 gap)
  — unchanged by this task.
- **CI (GitHub Actions) is not verified** — never claim CI green
  without an observed successful run (the billing-lock history
  from W9.1.3 means runs may never start).
- **Staging checklist update:** docs/w9-1-3-staging-validation.md
  §11, first item, is updated by this PR to point at the W9.1.4
  migration + its privilege matrix instead of the one-line
  `USAGE` proposal — but the item stays UNCHECKED. No staging
  prerequisite is marked complete by this PR.
- **Follow-up (separate approval):** audit live roles beyond
  the four covered here; decide whether the legacy v1 cleanup
  wrapper should leave the backend allowlist; add a staging
  RLS-policy replay test once a staging database exists.

## Appendix: classified test results

Environment: disposable PostgreSQL 17.11
(`PostgreSQL 17.11 (Ubuntu 17.11-1.pgdg24.04+2)`, pg_bootstrap
cluster on port 54400) + real PostgREST 12.2.3. Full backend
suite: **459 passed, 0 failed** (437 prior + 22 new), ruff
check + ruff format clean on both changed test files,
`pglast` parse clean on the migration, migration replayed
twice (idempotent) on the disposable cluster.

| Test | Result | Evidence |
| --- | --- | --- |
| Test 1 — server-only RPC success (direct role + PostgREST) | PASSED | Webhook event, v2 cleanup, reminders, outbox processor all succeed as service_role |
| Test 2 — anonymous denied | PASSED | Server wrappers + private business functions denied (function or schema denial) |
| Test 3 — authenticated denied where appropriate | PASSED | Server wrappers + private business functions denied; service_role denied user-context wrappers |
| Test 4 — customer RPCs still work | PASSED | Reservation (`pending_payment`) + checkout initiation for the owner |
| Test 5 — merchant/admin RPCs still work | PASSED | Merchant application + store creation for an owner member; admin review wrappers are service-role-only by matrix (no live admin user exists to drive a full review end-to-end in the disposable DB, so review bodies are covered by matrix + W9.1.3 webhook races, not by a dedicated review test) |
| Test 6 — RLS/authorization preserved | PASSED | Cross-customer checkout refused; anon catalogue read works; helper-revocation negative control fails as expected |
| Test 7 — private direct invocation (+/−) | PASSED | Granted combinations succeed; all other combinations denied; anon direct helper call denied at schema (RLS-only grant) |
| Test 8 — triggers after revocation | PASSED | Outbox trigger fires; posted-ledger triggers refuse mutations |
| Test 9 — ownership/security mode unchanged | PASSED | `prosecdef`, pinned `search_path`, signatures and return types verified; migration contains no function definition |
| Test 10 — future function defaults | PASSED | Future function still gets PUBLIC EXECUTE (proven PG17 behaviour); migration claims no default-privilege protection |
| Stage G — PostgREST integration | PASSED | Service-role 2xx + event row; anon/authenticated non-2xx; private path 404 |
| W9.1.2 concurrency suite | PASSED | 15/15 on the W9.1.4-applied cluster |
| W9.1.3 webhook/payment-race suite | PASSED | 14/14 (default ports on re-run; one earlier run was blocked by transient port-3002 occupancy, not a product failure) |
| Full backend pytest suite | PASSED | 459 passed (see above) |
| Ruff check + format | PASSED | Both changed test files clean |
| SQL/migration validation | PASSED | `pglast` parse clean; migration replayed twice, idempotent |
| Geography path (non-NULL lat/lon store creation) | NOT TESTED | Disposable wrappers cover the geography cast, but no test passes non-NULL coordinates; staging must cover it |
| Live staging / production verification | NOT TESTED | No staging environment exists; production never contacted (by rule) |
| GitHub Actions CI | NOT TESTED | No observed successful run; never claimed green |
| Razorpay test-mode checkout | NOT TESTED | Out of scope for this task (W9.1.3 BLOCKED item carries forward) |
