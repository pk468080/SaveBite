-- SaveBite — consolidated remote schema baseline (TRACKING COPY ONLY)
-- Generated from the live Supabase project surplus-food-marketplace
-- (ref zehnhqcfawagxbactvne, ap-south-1) on 2026-10-31 by introspecting
-- pg_catalog / information_schema via the Supabase Management API.
--
-- DO NOT APPLY THIS FILE TO THE LIVE PROJECT. The live project already has
-- these objects, applied by the 15 remote migrations listed in
-- supabase/migrations/README.md. Applying this file to live would fail on
-- duplicate objects and must never be done with `supabase db push`.
-- Purpose: repository tracking of the approved schema, so code (and generated
-- types) can be reviewed against the real database without recreating it.
-- Future changes go in NEW migration files on top of this baseline, with a
-- written change plan and explicit approval, per the project stop conditions.
--
-- Known limits of this consolidated pull (vs. a `supabase db pull`):
-- * It is one consolidated file, NOT the original 15 migration files.
--   The original migration SQL is not recoverable from the live database;
--   only their versions/names are recorded in supabase/migrations/README.md.
-- * Table/column grants and storage-bucket policies are summarised in
--   supabase/migrations/README.md, not reproduced as GRANT statements here.
-- * Extension creation is commented out: Supabase-managed extensions
--   (postgis, pgcrypto, uuid-ossp, etc.) are already present in the project.

-- Extensions present live (Supabase-managed; do not re-create blindly):
--   pgcrypto, uuid-ossp, postgis, pg_stat_statements, pgtap, plpgsql_check, supabase_vault

create schema if not exists private;

create type public.dietary_classification as enum ('vegetarian', 'non_vegetarian', 'vegan', 'egg', 'unknown');
create type public.incident_status as enum ('reported', 'triaged', 'investigating', 'action_required', 'resolved', 'closed');
create type public.listing_status as enum ('draft', 'scheduled', 'active', 'paused', 'sold_out', 'expired', 'cancelled');
create type public.listing_type as enum ('surprise_bag', 'individual_item');
create type public.merchant_business_type as enum ('restaurant', 'bakery', 'cafe', 'supermarket', 'hotel', 'cloud_kitchen', 'grocery_store', 'food_manufacturer', 'sweet_shop', 'other');
create type public.merchant_member_role as enum ('owner', 'admin', 'store_manager', 'inventory_manager', 'pickup_operator', 'finance_viewer');
create type public.merchant_status as enum ('pending_review', 'additional_information_required', 'approved', 'rejected', 'suspended');
create type public.order_status as enum ('pending_payment', 'confirmed', 'ready_for_pickup', 'collected', 'expired', 'cancelled', 'refund_pending', 'refunded');
create type public.payment_status as enum ('created', 'authorized', 'captured', 'failed', 'refund_pending', 'partially_refunded', 'refunded', 'reconciliation_required');
create type public.platform_role as enum ('support_agent', 'finance_admin', 'compliance_admin', 'operations_admin', 'super_admin');
create type public.refund_status as enum ('requested', 'approved', 'rejected', 'processing', 'succeeded', 'failed');
create type public.reservation_status as enum ('active', 'consumed', 'released', 'expired');
create type public.settlement_status as enum ('pending', 'processing', 'paid', 'failed', 'reversed');
create type public.store_status as enum ('draft', 'active', 'inactive', 'suspended');
create type public.support_ticket_status as enum ('open', 'in_progress', 'waiting_for_customer', 'resolved', 'closed');
create type public.verification_status as enum ('pending', 'under_review', 'verified', 'rejected', 'expired');

create table private."audit_logs" (
  "id" uuid default gen_random_uuid() not null,
  "actor_user_id" uuid,
  "actor_type" text not null,
  "action" text not null,
  "entity_type" text not null,
  "entity_id" uuid,
  "request_id" text,
  "before_data" jsonb,
  "after_data" jsonb,
  "ip_hash" text,
  "user_agent" text,
  "created_at" timestamp with time zone default now() not null
);

create table private."commission_rules" (
  "id" uuid default gen_random_uuid() not null,
  "name" text not null,
  "merchant_type" merchant_business_type,
  "commission_basis_points" integer not null,
  "fixed_fee_paise" integer default 0 not null,
  "starts_at" timestamp with time zone not null,
  "ends_at" timestamp with time zone,
  "is_active" boolean default true not null,
  "created_by" uuid,
  "created_at" timestamp with time zone default now() not null
);

create table private."idempotency_records" (
  "id" uuid default gen_random_uuid() not null,
  "actor_user_id" uuid,
  "operation" text not null,
  "idempotency_key" text not null,
  "request_hash" text not null,
  "response_body" jsonb,
  "status" text default 'processing'::text not null,
  "created_at" timestamp with time zone default now() not null,
  "expires_at" timestamp with time zone not null
);

create table private."ledger_accounts" (
  "id" uuid default gen_random_uuid() not null,
  "account_code" text not null,
  "account_name" text not null,
  "account_type" text not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "is_active" boolean default true not null,
  "created_at" timestamp with time zone default now() not null
);

create table private."ledger_entries" (
  "id" uuid default gen_random_uuid() not null,
  "transaction_id" uuid not null,
  "account_id" uuid not null,
  "merchant_id" uuid,
  "debit_amount" numeric(14,2) default 0 not null,
  "credit_amount" numeric(14,2) default 0 not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "created_at" timestamp with time zone default now() not null
);

create table private."ledger_transactions" (
  "id" uuid default gen_random_uuid() not null,
  "reference_type" text not null,
  "reference_id" uuid not null,
  "description" text not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "status" text default 'draft'::text not null,
  "posted_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null
);

create table private."merchant_payout_accounts" (
  "id" uuid default gen_random_uuid() not null,
  "merchant_id" uuid not null,
  "gateway" text not null,
  "linked_account_id" text not null,
  "verification_status" verification_status default 'pending'::verification_status not null,
  "is_default" boolean default false not null,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table private."notification_outbox" (
  "id" uuid default gen_random_uuid() not null,
  "user_id" uuid not null,
  "channel" text not null,
  "template_key" text not null,
  "payload" jsonb default '{}'::jsonb not null,
  "status" text default 'pending'::text not null,
  "attempts" smallint default 0 not null,
  "available_at" timestamp with time zone default now() not null,
  "sent_at" timestamp with time zone,
  "last_error" text,
  "created_at" timestamp with time zone default now() not null
);

create table private."payment_transactions" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "gateway" text not null,
  "gateway_order_id" text,
  "gateway_payment_id" text,
  "amount" numeric(12,2) not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "status" payment_status default 'created'::payment_status not null,
  "idempotency_key" text not null,
  "gateway_signature_verified" boolean default false not null,
  "captured_at" timestamp with time zone,
  "failure_code" text,
  "failure_description" text,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table private."payment_webhook_events" (
  "id" uuid default gen_random_uuid() not null,
  "gateway" text not null,
  "gateway_event_id" text not null,
  "event_type" text not null,
  "payload" jsonb not null,
  "signature_verified" boolean default false not null,
  "processing_status" text default 'received'::text not null,
  "processing_error" text,
  "received_at" timestamp with time zone default now() not null,
  "processed_at" timestamp with time zone
);

create table private."pickup_events" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "store_id" uuid not null,
  "verified_by" uuid,
  "verification_method" text not null,
  "result" text not null,
  "reason" text,
  "created_at" timestamp with time zone default now() not null
);

create table private."pickup_tokens" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "token_hash" text not null,
  "expires_at" timestamp with time zone not null,
  "used_at" timestamp with time zone,
  "invalidated_at" timestamp with time zone,
  "failed_attempts" integer default 0 not null,
  "created_at" timestamp with time zone default now() not null
);

create table private."refund_events" (
  "id" uuid default gen_random_uuid() not null,
  "refund_id" uuid not null,
  "from_status" refund_status,
  "to_status" refund_status not null,
  "actor_user_id" uuid,
  "actor_type" text not null,
  "reason" text,
  "gateway_reference" text,
  "created_at" timestamp with time zone default now() not null
);

create table private."refunds" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "payment_transaction_id" uuid,
  "requested_by" uuid,
  "amount" numeric(12,2) not null,
  "reason_code" text not null,
  "customer_description" text,
  "status" refund_status default 'requested'::refund_status not null,
  "gateway_refund_id" text,
  "approved_by" uuid,
  "processed_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table private."settlement_items" (
  "id" uuid default gen_random_uuid() not null,
  "settlement_id" uuid not null,
  "order_id" uuid,
  "line_type" text not null,
  "amount" numeric(14,2) not null,
  "description" text,
  "created_at" timestamp with time zone default now() not null
);

create table private."settlements" (
  "id" uuid default gen_random_uuid() not null,
  "merchant_id" uuid not null,
  "store_id" uuid,
  "period_start" timestamp with time zone not null,
  "period_end" timestamp with time zone not null,
  "gross_amount" numeric(14,2) default 0 not null,
  "commission_amount" numeric(14,2) default 0 not null,
  "refund_amount" numeric(14,2) default 0 not null,
  "adjustments_amount" numeric(14,2) default 0 not null,
  "net_amount" numeric(14,2) default 0 not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "status" settlement_status default 'pending'::settlement_status not null,
  "gateway_transfer_id" text,
  "failure_reason" text,
  "processed_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null
);

create table public."categories" (
  "id" uuid default gen_random_uuid() not null,
  "parent_id" uuid,
  "name" text not null,
  "slug" text not null,
  "display_order" integer default 0 not null,
  "is_active" boolean default true not null,
  "created_at" timestamp with time zone default now() not null
);

create table public."food_safety_evidence" (
  "id" uuid default gen_random_uuid() not null,
  "incident_id" uuid not null,
  "uploaded_by" uuid not null,
  "storage_path" text not null,
  "media_type" text,
  "created_at" timestamp with time zone default now() not null
);

create table public."food_safety_incidents" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid,
  "customer_id" uuid,
  "merchant_id" uuid not null,
  "store_id" uuid not null,
  "listing_id" uuid,
  "incident_type" text not null,
  "description" text not null,
  "priority" text default 'high'::text not null,
  "status" incident_status default 'reported'::incident_status not null,
  "assigned_to" uuid,
  "immediate_action" text,
  "resolution" text,
  "reported_at" timestamp with time zone default now() not null,
  "resolved_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."inventory_events" (
  "id" uuid default gen_random_uuid() not null,
  "listing_id" uuid not null,
  "order_id" uuid,
  "reservation_id" uuid,
  "event_type" text not null,
  "quantity_delta" integer not null,
  "actor_user_id" uuid,
  "reason" text,
  "created_at" timestamp with time zone default now() not null
);

create table public."inventory_reservations" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "order_item_id" uuid not null,
  "listing_id" uuid not null,
  "quantity" integer not null,
  "status" reservation_status default 'active'::reservation_status not null,
  "expires_at" timestamp with time zone not null,
  "consumed_at" timestamp with time zone,
  "released_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null
);

create table public."listing_images" (
  "id" uuid default gen_random_uuid() not null,
  "listing_id" uuid not null,
  "storage_path" text not null,
  "alt_text" text,
  "display_order" smallint default 0 not null,
  "created_at" timestamp with time zone default now() not null
);

create table public."listing_templates" (
  "id" uuid default gen_random_uuid() not null,
  "store_id" uuid not null,
  "listing_type" listing_type not null,
  "category_id" uuid,
  "title" text not null,
  "description" text,
  "reference_value" numeric(12,2) not null,
  "default_selling_price" numeric(12,2) not null,
  "contents_description" text,
  "allergen_codes" text[] default '{}'::text[] not null,
  "dietary_classification" dietary_classification default 'unknown'::dietary_classification not null,
  "storage_instructions" text,
  "is_active" boolean default true not null,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."listings" (
  "id" uuid default gen_random_uuid() not null,
  "store_id" uuid not null,
  "template_id" uuid,
  "listing_type" listing_type not null,
  "category_id" uuid,
  "title" text not null,
  "description" text,
  "contents_description" text,
  "reference_value" numeric(12,2) not null,
  "selling_price" numeric(12,2) not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "total_quantity" integer not null,
  "reserved_quantity" integer default 0 not null,
  "sold_quantity" integer default 0 not null,
  "available_quantity" integer,
  "sale_starts_at" timestamp with time zone default now() not null,
  "sale_ends_at" timestamp with time zone not null,
  "pickup_starts_at" timestamp with time zone not null,
  "pickup_ends_at" timestamp with time zone not null,
  "prepared_at" timestamp with time zone,
  "best_before_at" timestamp with time zone,
  "allergen_codes" text[] default '{}'::text[] not null,
  "dietary_classification" dietary_classification default 'unknown'::dietary_classification not null,
  "storage_instructions" text,
  "food_safety_notes" text,
  "status" listing_status default 'draft'::listing_status not null,
  "published_at" timestamp with time zone,
  "created_by" uuid not null,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."merchant_documents" (
  "id" uuid default gen_random_uuid() not null,
  "merchant_id" uuid not null,
  "store_id" uuid,
  "document_type" text not null,
  "storage_path" text not null,
  "document_reference" text,
  "last_four" text,
  "valid_from" date,
  "valid_until" date,
  "verification_status" verification_status default 'pending'::verification_status not null,
  "review_notes" text,
  "reviewed_by" uuid,
  "reviewed_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null
);

create table public."merchant_memberships" (
  "id" uuid default gen_random_uuid() not null,
  "merchant_id" uuid not null,
  "user_id" uuid not null,
  "role" merchant_member_role not null,
  "is_active" boolean default true not null,
  "invited_by" uuid,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."merchants" (
  "id" uuid default gen_random_uuid() not null,
  "legal_name" text not null,
  "display_name" text not null,
  "business_type" merchant_business_type not null,
  "business_email" text,
  "business_phone" text,
  "status" merchant_status default 'pending_review'::merchant_status not null,
  "verification_status" verification_status default 'pending'::verification_status not null,
  "onboarding_notes" text,
  "created_by" uuid not null,
  "approved_at" timestamp with time zone,
  "approved_by" uuid,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."notifications" (
  "id" uuid default gen_random_uuid() not null,
  "user_id" uuid not null,
  "notification_type" text not null,
  "title" text not null,
  "body" text not null,
  "reference_type" text,
  "reference_id" uuid,
  "read_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null
);

create table public."order_items" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "listing_id" uuid not null,
  "listing_type" listing_type not null,
  "listing_title_snapshot" text not null,
  "listing_description_snapshot" text,
  "allergen_codes_snapshot" text[] default '{}'::text[] not null,
  "dietary_classification_snapshot" dietary_classification default 'unknown'::dietary_classification not null,
  "quantity" integer not null,
  "unit_price" numeric(12,2) not null,
  "reference_value_snapshot" numeric(12,2) not null,
  "line_total" numeric(12,2) not null,
  "created_at" timestamp with time zone default now() not null
);

create table public."order_status_events" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "from_status" order_status,
  "to_status" order_status not null,
  "actor_user_id" uuid,
  "actor_type" text not null,
  "reason" text,
  "created_at" timestamp with time zone default now() not null
);

create table public."orders" (
  "id" uuid default gen_random_uuid() not null,
  "order_number" text not null,
  "customer_id" uuid not null,
  "merchant_id" uuid not null,
  "store_id" uuid not null,
  "status" order_status default 'pending_payment'::order_status not null,
  "payment_status" payment_status default 'created'::payment_status not null,
  "currency" character(3) default 'INR'::bpchar not null,
  "subtotal_amount" numeric(12,2) not null,
  "discount_amount" numeric(12,2) default 0 not null,
  "platform_fee_amount" numeric(12,2) default 0 not null,
  "tax_amount" numeric(12,2) default 0 not null,
  "total_amount" numeric(12,2) not null,
  "pickup_starts_at" timestamp with time zone not null,
  "pickup_ends_at" timestamp with time zone not null,
  "customer_note" text,
  "cancellation_reason" text,
  "request_idempotency_key" text not null,
  "confirmed_at" timestamp with time zone,
  "collected_at" timestamp with time zone,
  "cancelled_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null,
  "request_hash" text not null
);

create table public."platform_service_areas" (
  "id" uuid default gen_random_uuid() not null,
  "name" text not null,
  "city" text not null,
  "state" text not null,
  "pincode_prefix" text,
  "boundary" geography,
  "is_active" boolean default false not null,
  "created_at" timestamp with time zone default now() not null
);

create table public."platform_user_roles" (
  "id" uuid default gen_random_uuid() not null,
  "user_id" uuid not null,
  "role" platform_role not null,
  "granted_by" uuid,
  "granted_at" timestamp with time zone default now() not null,
  "revoked_at" timestamp with time zone
);

create table public."profiles" (
  "id" uuid not null,
  "full_name" text,
  "phone_e164" text,
  "avatar_path" text,
  "preferred_language" text default 'en'::text not null,
  "default_city" text,
  "account_status" text default 'active'::text not null,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."reviews" (
  "id" uuid default gen_random_uuid() not null,
  "order_id" uuid not null,
  "customer_id" uuid not null,
  "store_id" uuid not null,
  "merchant_id" uuid not null,
  "rating" smallint not null,
  "comment" text,
  "moderation_status" text default 'visible'::text not null,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."store_hours" (
  "id" uuid default gen_random_uuid() not null,
  "store_id" uuid not null,
  "weekday" smallint not null,
  "opens_at" time without time zone,
  "closes_at" time without time zone,
  "is_closed" boolean default false not null,
  "created_at" timestamp with time zone default now() not null
);

create table public."store_staff_memberships" (
  "id" uuid default gen_random_uuid() not null,
  "store_id" uuid not null,
  "user_id" uuid not null,
  "role" merchant_member_role not null,
  "is_active" boolean default true not null,
  "granted_by" uuid,
  "created_at" timestamp with time zone default now() not null
);

create table public."stores" (
  "id" uuid default gen_random_uuid() not null,
  "merchant_id" uuid not null,
  "name" text not null,
  "slug" text not null,
  "address_line_1" text not null,
  "address_line_2" text,
  "locality" text,
  "city" text not null,
  "state" text not null,
  "pincode" text not null,
  "country_code" character(2) default 'IN'::bpchar not null,
  "location" geography,
  "contact_phone" text,
  "pickup_instructions" text,
  "timezone" text default 'Asia/Kolkata'::text not null,
  "status" store_status default 'draft'::store_status not null,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."support_messages" (
  "id" uuid default gen_random_uuid() not null,
  "ticket_id" uuid not null,
  "sender_user_id" uuid,
  "sender_type" text not null,
  "message" text not null,
  "is_internal" boolean default false not null,
  "created_at" timestamp with time zone default now() not null
);

create table public."support_tickets" (
  "id" uuid default gen_random_uuid() not null,
  "customer_id" uuid not null,
  "order_id" uuid,
  "merchant_id" uuid,
  "store_id" uuid,
  "category" text not null,
  "subject" text not null,
  "description" text not null,
  "status" support_ticket_status default 'open'::support_ticket_status not null,
  "priority" text default 'normal'::text not null,
  "assigned_to" uuid,
  "resolved_at" timestamp with time zone,
  "created_at" timestamp with time zone default now() not null,
  "updated_at" timestamp with time zone default now() not null
);

create table public."user_favourites" (
  "user_id" uuid not null,
  "store_id" uuid not null,
  "created_at" timestamp with time zone default now() not null
);

alter table private."audit_logs" add constraint "audit_logs_actor_type_check" CHECK ((actor_type = ANY (ARRAY['customer'::text, 'merchant'::text, 'admin'::text, 'system'::text, 'webhook'::text])));
alter table private."audit_logs" add constraint "audit_logs_actor_user_id_fkey" FOREIGN KEY (actor_user_id) REFERENCES auth.users(id);
alter table private."audit_logs" add constraint "audit_logs_pkey" PRIMARY KEY (id);
alter table private."commission_rules" add constraint "commission_rules_check" CHECK (((ends_at IS NULL) OR (ends_at > starts_at)));
alter table private."commission_rules" add constraint "commission_rules_commission_basis_points_check" CHECK (((commission_basis_points >= 0) AND (commission_basis_points <= 10000)));
alter table private."commission_rules" add constraint "commission_rules_created_by_fkey" FOREIGN KEY (created_by) REFERENCES auth.users(id);
alter table private."commission_rules" add constraint "commission_rules_fixed_fee_paise_check" CHECK ((fixed_fee_paise >= 0));
alter table private."commission_rules" add constraint "commission_rules_pkey" PRIMARY KEY (id);
alter table private."idempotency_records" add constraint "idempotency_records_actor_user_id_fkey" FOREIGN KEY (actor_user_id) REFERENCES auth.users(id);
alter table private."idempotency_records" add constraint "idempotency_records_actor_user_id_operation_idempotency_key_key" UNIQUE (actor_user_id, operation, idempotency_key);
alter table private."idempotency_records" add constraint "idempotency_records_pkey" PRIMARY KEY (id);
alter table private."idempotency_records" add constraint "idempotency_records_status_check" CHECK ((status = ANY (ARRAY['processing'::text, 'completed'::text, 'failed'::text])));
alter table private."ledger_accounts" add constraint "ledger_accounts_account_code_key" UNIQUE (account_code);
alter table private."ledger_accounts" add constraint "ledger_accounts_account_type_check" CHECK ((account_type = ANY (ARRAY['asset'::text, 'liability'::text, 'equity'::text, 'revenue'::text, 'expense'::text])));
alter table private."ledger_accounts" add constraint "ledger_accounts_pkey" PRIMARY KEY (id);
alter table private."ledger_entries" add constraint "ledger_entries_account_id_fkey" FOREIGN KEY (account_id) REFERENCES private.ledger_accounts(id) ON DELETE RESTRICT;
alter table private."ledger_entries" add constraint "ledger_entries_check" CHECK ((((debit_amount > (0)::numeric) AND (credit_amount = (0)::numeric)) OR ((credit_amount > (0)::numeric) AND (debit_amount = (0)::numeric))));
alter table private."ledger_entries" add constraint "ledger_entries_credit_amount_check" CHECK ((credit_amount >= (0)::numeric));
alter table private."ledger_entries" add constraint "ledger_entries_debit_amount_check" CHECK ((debit_amount >= (0)::numeric));
alter table private."ledger_entries" add constraint "ledger_entries_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id);
alter table private."ledger_entries" add constraint "ledger_entries_pkey" PRIMARY KEY (id);
alter table private."ledger_entries" add constraint "ledger_entries_transaction_id_fkey" FOREIGN KEY (transaction_id) REFERENCES private.ledger_transactions(id) ON DELETE RESTRICT;
alter table private."ledger_transactions" add constraint "ledger_transactions_pkey" PRIMARY KEY (id);
alter table private."ledger_transactions" add constraint "ledger_transactions_reference_type_reference_id_key" UNIQUE (reference_type, reference_id);
alter table private."ledger_transactions" add constraint "ledger_transactions_status_check" CHECK ((status = ANY (ARRAY['draft'::text, 'posted'::text, 'reversed'::text])));
alter table private."merchant_payout_accounts" add constraint "merchant_payout_accounts_gateway_linked_account_id_key" UNIQUE (gateway, linked_account_id);
alter table private."merchant_payout_accounts" add constraint "merchant_payout_accounts_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE;
alter table private."merchant_payout_accounts" add constraint "merchant_payout_accounts_pkey" PRIMARY KEY (id);
alter table private."notification_outbox" add constraint "notification_outbox_channel_check" CHECK ((channel = ANY (ARRAY['push'::text, 'email'::text, 'sms'::text, 'whatsapp'::text])));
alter table private."notification_outbox" add constraint "notification_outbox_pkey" PRIMARY KEY (id);
alter table private."notification_outbox" add constraint "notification_outbox_status_check" CHECK ((status = ANY (ARRAY['pending'::text, 'processing'::text, 'sent'::text, 'failed'::text, 'cancelled'::text])));
alter table private."notification_outbox" add constraint "notification_outbox_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table private."payment_transactions" add constraint "payment_transactions_amount_check" CHECK ((amount >= (0)::numeric));
alter table private."payment_transactions" add constraint "payment_transactions_currency_check" CHECK ((currency = 'INR'::bpchar));
alter table private."payment_transactions" add constraint "payment_transactions_gateway_check" CHECK ((gateway = ANY (ARRAY['razorpay'::text, 'other'::text])));
alter table private."payment_transactions" add constraint "payment_transactions_idempotency_key_key" UNIQUE (idempotency_key);
alter table private."payment_transactions" add constraint "payment_transactions_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table private."payment_transactions" add constraint "payment_transactions_pkey" PRIMARY KEY (id);
alter table private."payment_webhook_events" add constraint "payment_webhook_events_gateway_gateway_event_id_key" UNIQUE (gateway, gateway_event_id);
alter table private."payment_webhook_events" add constraint "payment_webhook_events_pkey" PRIMARY KEY (id);
alter table private."payment_webhook_events" add constraint "payment_webhook_events_processing_status_check" CHECK ((processing_status = ANY (ARRAY['received'::text, 'processing'::text, 'processed'::text, 'failed'::text, 'ignored'::text])));
alter table private."pickup_events" add constraint "pickup_events_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table private."pickup_events" add constraint "pickup_events_pkey" PRIMARY KEY (id);
alter table private."pickup_events" add constraint "pickup_events_result_check" CHECK ((result = ANY (ARRAY['accepted'::text, 'rejected'::text])));
alter table private."pickup_events" add constraint "pickup_events_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE RESTRICT;
alter table private."pickup_events" add constraint "pickup_events_verification_method_check" CHECK ((verification_method = ANY (ARRAY['qr'::text, 'numeric_code'::text, 'admin_override'::text])));
alter table private."pickup_events" add constraint "pickup_events_verified_by_fkey" FOREIGN KEY (verified_by) REFERENCES auth.users(id);
alter table private."pickup_tokens" add constraint "pickup_tokens_failed_attempts_check" CHECK ((failed_attempts >= 0));
alter table private."pickup_tokens" add constraint "pickup_tokens_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table private."pickup_tokens" add constraint "pickup_tokens_pkey" PRIMARY KEY (id);
alter table private."pickup_tokens" add constraint "pickup_tokens_token_hash_key" UNIQUE (token_hash);
alter table private."refund_events" add constraint "refund_events_actor_type_check" CHECK ((actor_type = ANY (ARRAY['customer'::text, 'admin'::text, 'system'::text, 'webhook'::text])));
alter table private."refund_events" add constraint "refund_events_actor_user_id_fkey" FOREIGN KEY (actor_user_id) REFERENCES auth.users(id);
alter table private."refund_events" add constraint "refund_events_pkey" PRIMARY KEY (id);
alter table private."refund_events" add constraint "refund_events_refund_id_fkey" FOREIGN KEY (refund_id) REFERENCES private.refunds(id) ON DELETE RESTRICT;
alter table private."refunds" add constraint "refunds_amount_check" CHECK ((amount > (0)::numeric));
alter table private."refunds" add constraint "refunds_approved_by_fkey" FOREIGN KEY (approved_by) REFERENCES auth.users(id);
alter table private."refunds" add constraint "refunds_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table private."refunds" add constraint "refunds_payment_transaction_id_fkey" FOREIGN KEY (payment_transaction_id) REFERENCES private.payment_transactions(id) ON DELETE RESTRICT;
alter table private."refunds" add constraint "refunds_pkey" PRIMARY KEY (id);
alter table private."refunds" add constraint "refunds_requested_by_fkey" FOREIGN KEY (requested_by) REFERENCES auth.users(id);
alter table private."settlement_items" add constraint "settlement_items_line_type_check" CHECK ((line_type = ANY (ARRAY['order_proceeds'::text, 'commission'::text, 'refund'::text, 'adjustment'::text])));
alter table private."settlement_items" add constraint "settlement_items_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table private."settlement_items" add constraint "settlement_items_pkey" PRIMARY KEY (id);
alter table private."settlement_items" add constraint "settlement_items_settlement_id_fkey" FOREIGN KEY (settlement_id) REFERENCES private.settlements(id) ON DELETE RESTRICT;
alter table private."settlements" add constraint "settlements_check" CHECK ((period_end > period_start));
alter table private."settlements" add constraint "settlements_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id);
alter table private."settlements" add constraint "settlements_pkey" PRIMARY KEY (id);
alter table private."settlements" add constraint "settlements_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id);
alter table public."categories" add constraint "categories_parent_id_fkey" FOREIGN KEY (parent_id) REFERENCES categories(id);
alter table public."categories" add constraint "categories_pkey" PRIMARY KEY (id);
alter table public."categories" add constraint "categories_slug_key" UNIQUE (slug);
alter table public."food_safety_evidence" add constraint "food_safety_evidence_incident_id_fkey" FOREIGN KEY (incident_id) REFERENCES food_safety_incidents(id) ON DELETE CASCADE;
alter table public."food_safety_evidence" add constraint "food_safety_evidence_pkey" PRIMARY KEY (id);
alter table public."food_safety_evidence" add constraint "food_safety_evidence_uploaded_by_fkey" FOREIGN KEY (uploaded_by) REFERENCES auth.users(id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_assigned_to_fkey" FOREIGN KEY (assigned_to) REFERENCES auth.users(id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES auth.users(id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_incident_type_check" CHECK ((incident_type = ANY (ARRAY['suspected_illness'::text, 'allergen_issue'::text, 'spoiled_food'::text, 'unsafe_packaging'::text, 'temperature_storage'::text, 'foreign_object'::text, 'expired_food'::text, 'other'::text])));
alter table public."food_safety_incidents" add constraint "food_safety_incidents_listing_id_fkey" FOREIGN KEY (listing_id) REFERENCES listings(id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_pkey" PRIMARY KEY (id);
alter table public."food_safety_incidents" add constraint "food_safety_incidents_priority_check" CHECK ((priority = ANY (ARRAY['normal'::text, 'high'::text, 'critical'::text])));
alter table public."food_safety_incidents" add constraint "food_safety_incidents_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id);
alter table public."inventory_events" add constraint "inventory_events_actor_user_id_fkey" FOREIGN KEY (actor_user_id) REFERENCES auth.users(id);
alter table public."inventory_events" add constraint "inventory_events_event_type_check" CHECK ((event_type = ANY (ARRAY['listing_created'::text, 'quantity_increased'::text, 'quantity_decreased'::text, 'reserved'::text, 'reservation_released'::text, 'sold'::text, 'manual_adjustment'::text, 'listing_cancelled'::text])));
alter table public."inventory_events" add constraint "inventory_events_listing_id_fkey" FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE RESTRICT;
alter table public."inventory_events" add constraint "inventory_events_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table public."inventory_events" add constraint "inventory_events_pkey" PRIMARY KEY (id);
alter table public."inventory_events" add constraint "inventory_events_reservation_id_fkey" FOREIGN KEY (reservation_id) REFERENCES inventory_reservations(id) ON DELETE RESTRICT;
alter table public."inventory_reservations" add constraint "inventory_reservations_listing_id_fkey" FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE RESTRICT;
alter table public."inventory_reservations" add constraint "inventory_reservations_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table public."inventory_reservations" add constraint "inventory_reservations_order_item_id_fkey" FOREIGN KEY (order_item_id) REFERENCES order_items(id) ON DELETE RESTRICT;
alter table public."inventory_reservations" add constraint "inventory_reservations_pkey" PRIMARY KEY (id);
alter table public."inventory_reservations" add constraint "inventory_reservations_quantity_check" CHECK ((quantity > 0));
alter table public."listing_images" add constraint "listing_images_listing_id_fkey" FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE CASCADE;
alter table public."listing_images" add constraint "listing_images_listing_id_storage_path_key" UNIQUE (listing_id, storage_path);
alter table public."listing_images" add constraint "listing_images_pkey" PRIMARY KEY (id);
alter table public."listing_templates" add constraint "listing_templates_category_id_fkey" FOREIGN KEY (category_id) REFERENCES categories(id);
alter table public."listing_templates" add constraint "listing_templates_default_selling_price_check" CHECK ((default_selling_price >= (0)::numeric));
alter table public."listing_templates" add constraint "listing_templates_pkey" PRIMARY KEY (id);
alter table public."listing_templates" add constraint "listing_templates_reference_value_check" CHECK ((reference_value >= (0)::numeric));
alter table public."listing_templates" add constraint "listing_templates_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
alter table public."listings" add constraint "listings_category_id_fkey" FOREIGN KEY (category_id) REFERENCES categories(id);
alter table public."listings" add constraint "listings_check" CHECK (((reserved_quantity + sold_quantity) <= total_quantity));
alter table public."listings" add constraint "listings_check1" CHECK ((sale_ends_at > sale_starts_at));
alter table public."listings" add constraint "listings_check2" CHECK ((pickup_ends_at > pickup_starts_at));
alter table public."listings" add constraint "listings_check3" CHECK ((pickup_ends_at >= sale_ends_at));
alter table public."listings" add constraint "listings_check4" CHECK (((best_before_at IS NULL) OR (best_before_at >= prepared_at)));
alter table public."listings" add constraint "listings_created_by_fkey" FOREIGN KEY (created_by) REFERENCES auth.users(id);
alter table public."listings" add constraint "listings_currency_check" CHECK ((currency = 'INR'::bpchar));
alter table public."listings" add constraint "listings_pkey" PRIMARY KEY (id);
alter table public."listings" add constraint "listings_reference_value_check" CHECK ((reference_value >= (0)::numeric));
alter table public."listings" add constraint "listings_reserved_quantity_check" CHECK ((reserved_quantity >= 0));
alter table public."listings" add constraint "listings_selling_price_check" CHECK ((selling_price >= (0)::numeric));
alter table public."listings" add constraint "listings_sold_quantity_check" CHECK ((sold_quantity >= 0));
alter table public."listings" add constraint "listings_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
alter table public."listings" add constraint "listings_template_id_fkey" FOREIGN KEY (template_id) REFERENCES listing_templates(id) ON DELETE SET NULL;
alter table public."listings" add constraint "listings_total_quantity_check" CHECK ((total_quantity > 0));
alter table public."merchant_documents" add constraint "merchant_documents_document_type_check" CHECK ((document_type = ANY (ARRAY['fssai_registration'::text, 'fssai_license'::text, 'pan'::text, 'gstin'::text, 'business_proof'::text, 'bank_proof'::text, 'other'::text])));
alter table public."merchant_documents" add constraint "merchant_documents_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE;
alter table public."merchant_documents" add constraint "merchant_documents_pkey" PRIMARY KEY (id);
alter table public."merchant_documents" add constraint "merchant_documents_reviewed_by_fkey" FOREIGN KEY (reviewed_by) REFERENCES auth.users(id);
alter table public."merchant_documents" add constraint "merchant_documents_store_fk" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
alter table public."merchant_memberships" add constraint "merchant_memberships_invited_by_fkey" FOREIGN KEY (invited_by) REFERENCES auth.users(id);
alter table public."merchant_memberships" add constraint "merchant_memberships_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE;
alter table public."merchant_memberships" add constraint "merchant_memberships_merchant_id_user_id_key" UNIQUE (merchant_id, user_id);
alter table public."merchant_memberships" add constraint "merchant_memberships_pkey" PRIMARY KEY (id);
alter table public."merchant_memberships" add constraint "merchant_memberships_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table public."merchants" add constraint "merchants_approved_by_fkey" FOREIGN KEY (approved_by) REFERENCES auth.users(id);
alter table public."merchants" add constraint "merchants_created_by_fkey" FOREIGN KEY (created_by) REFERENCES auth.users(id);
alter table public."merchants" add constraint "merchants_pkey" PRIMARY KEY (id);
alter table public."notifications" add constraint "notifications_pkey" PRIMARY KEY (id);
alter table public."notifications" add constraint "notifications_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table public."order_items" add constraint "order_items_line_total_check" CHECK ((line_total >= (0)::numeric));
alter table public."order_items" add constraint "order_items_listing_id_fkey" FOREIGN KEY (listing_id) REFERENCES listings(id) ON DELETE RESTRICT;
alter table public."order_items" add constraint "order_items_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table public."order_items" add constraint "order_items_pkey" PRIMARY KEY (id);
alter table public."order_items" add constraint "order_items_quantity_check" CHECK ((quantity > 0));
alter table public."order_items" add constraint "order_items_reference_value_snapshot_check" CHECK ((reference_value_snapshot >= (0)::numeric));
alter table public."order_items" add constraint "order_items_unit_price_check" CHECK ((unit_price >= (0)::numeric));
alter table public."order_status_events" add constraint "order_status_events_actor_type_check" CHECK ((actor_type = ANY (ARRAY['customer'::text, 'merchant'::text, 'admin'::text, 'system'::text])));
alter table public."order_status_events" add constraint "order_status_events_actor_user_id_fkey" FOREIGN KEY (actor_user_id) REFERENCES auth.users(id);
alter table public."order_status_events" add constraint "order_status_events_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table public."order_status_events" add constraint "order_status_events_pkey" PRIMARY KEY (id);
alter table public."orders" add constraint "orders_check" CHECK ((pickup_ends_at > pickup_starts_at));
alter table public."orders" add constraint "orders_currency_check" CHECK ((currency = 'INR'::bpchar));
alter table public."orders" add constraint "orders_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES auth.users(id);
alter table public."orders" add constraint "orders_customer_id_request_idempotency_key_key" UNIQUE (customer_id, request_idempotency_key);
alter table public."orders" add constraint "orders_discount_amount_check" CHECK ((discount_amount >= (0)::numeric));
alter table public."orders" add constraint "orders_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id);
alter table public."orders" add constraint "orders_order_number_key" UNIQUE (order_number);
alter table public."orders" add constraint "orders_pkey" PRIMARY KEY (id);
alter table public."orders" add constraint "orders_platform_fee_amount_check" CHECK ((platform_fee_amount >= (0)::numeric));
alter table public."orders" add constraint "orders_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id);
alter table public."orders" add constraint "orders_subtotal_amount_check" CHECK ((subtotal_amount >= (0)::numeric));
alter table public."orders" add constraint "orders_tax_amount_check" CHECK ((tax_amount >= (0)::numeric));
alter table public."orders" add constraint "orders_total_amount_check" CHECK ((total_amount >= (0)::numeric));
alter table public."platform_service_areas" add constraint "platform_service_areas_pkey" PRIMARY KEY (id);
alter table public."platform_user_roles" add constraint "platform_user_roles_granted_by_fkey" FOREIGN KEY (granted_by) REFERENCES auth.users(id);
alter table public."platform_user_roles" add constraint "platform_user_roles_pkey" PRIMARY KEY (id);
alter table public."platform_user_roles" add constraint "platform_user_roles_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table public."platform_user_roles" add constraint "platform_user_roles_user_id_role_key" UNIQUE (user_id, role);
alter table public."profiles" add constraint "profiles_account_status_check" CHECK ((account_status = ANY (ARRAY['active'::text, 'restricted'::text, 'deactivated'::text])));
alter table public."profiles" add constraint "profiles_id_fkey" FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table public."profiles" add constraint "profiles_pkey" PRIMARY KEY (id);
alter table public."reviews" add constraint "reviews_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES auth.users(id);
alter table public."reviews" add constraint "reviews_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id);
alter table public."reviews" add constraint "reviews_moderation_status_check" CHECK ((moderation_status = ANY (ARRAY['visible'::text, 'hidden'::text, 'under_review'::text])));
alter table public."reviews" add constraint "reviews_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE RESTRICT;
alter table public."reviews" add constraint "reviews_order_id_key" UNIQUE (order_id);
alter table public."reviews" add constraint "reviews_pkey" PRIMARY KEY (id);
alter table public."reviews" add constraint "reviews_rating_check" CHECK (((rating >= 1) AND (rating <= 5)));
alter table public."reviews" add constraint "reviews_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id);
alter table public."store_hours" add constraint "store_hours_check" CHECK ((((is_closed = true) AND (opens_at IS NULL) AND (closes_at IS NULL)) OR ((is_closed = false) AND (opens_at IS NOT NULL) AND (closes_at IS NOT NULL) AND (opens_at <> closes_at))));
alter table public."store_hours" add constraint "store_hours_pkey" PRIMARY KEY (id);
alter table public."store_hours" add constraint "store_hours_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
alter table public."store_hours" add constraint "store_hours_store_id_weekday_key" UNIQUE (store_id, weekday);
alter table public."store_hours" add constraint "store_hours_weekday_check" CHECK (((weekday >= 0) AND (weekday <= 6)));
alter table public."store_staff_memberships" add constraint "store_staff_memberships_granted_by_fkey" FOREIGN KEY (granted_by) REFERENCES auth.users(id);
alter table public."store_staff_memberships" add constraint "store_staff_memberships_pkey" PRIMARY KEY (id);
alter table public."store_staff_memberships" add constraint "store_staff_memberships_role_check" CHECK ((role = ANY (ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role, 'pickup_operator'::merchant_member_role, 'finance_viewer'::merchant_member_role])));
alter table public."store_staff_memberships" add constraint "store_staff_memberships_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
alter table public."store_staff_memberships" add constraint "store_staff_memberships_store_id_user_id_key" UNIQUE (store_id, user_id);
alter table public."store_staff_memberships" add constraint "store_staff_memberships_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
alter table public."stores" add constraint "stores_country_code_check" CHECK ((country_code = 'IN'::bpchar));
alter table public."stores" add constraint "stores_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE;
alter table public."stores" add constraint "stores_merchant_id_slug_key" UNIQUE (merchant_id, slug);
alter table public."stores" add constraint "stores_pkey" PRIMARY KEY (id);
alter table public."support_messages" add constraint "support_messages_pkey" PRIMARY KEY (id);
alter table public."support_messages" add constraint "support_messages_sender_type_check" CHECK ((sender_type = ANY (ARRAY['customer'::text, 'merchant'::text, 'support'::text, 'system'::text])));
alter table public."support_messages" add constraint "support_messages_sender_user_id_fkey" FOREIGN KEY (sender_user_id) REFERENCES auth.users(id);
alter table public."support_messages" add constraint "support_messages_ticket_id_fkey" FOREIGN KEY (ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE;
alter table public."support_tickets" add constraint "support_tickets_assigned_to_fkey" FOREIGN KEY (assigned_to) REFERENCES auth.users(id);
alter table public."support_tickets" add constraint "support_tickets_category_check" CHECK ((category = ANY (ARRAY['order_problem'::text, 'merchant_unavailable'::text, 'incorrect_listing'::text, 'payment'::text, 'refund'::text, 'pickup_problem'::text, 'food_quality'::text, 'food_safety'::text, 'other'::text])));
alter table public."support_tickets" add constraint "support_tickets_customer_id_fkey" FOREIGN KEY (customer_id) REFERENCES auth.users(id);
alter table public."support_tickets" add constraint "support_tickets_merchant_id_fkey" FOREIGN KEY (merchant_id) REFERENCES merchants(id);
alter table public."support_tickets" add constraint "support_tickets_order_id_fkey" FOREIGN KEY (order_id) REFERENCES orders(id);
alter table public."support_tickets" add constraint "support_tickets_pkey" PRIMARY KEY (id);
alter table public."support_tickets" add constraint "support_tickets_priority_check" CHECK ((priority = ANY (ARRAY['low'::text, 'normal'::text, 'high'::text, 'urgent'::text])));
alter table public."support_tickets" add constraint "support_tickets_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id);
alter table public."user_favourites" add constraint "user_favourites_pkey" PRIMARY KEY (user_id, store_id);
alter table public."user_favourites" add constraint "user_favourites_store_id_fkey" FOREIGN KEY (store_id) REFERENCES stores(id) ON DELETE CASCADE;
alter table public."user_favourites" add constraint "user_favourites_user_id_fkey" FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

CREATE INDEX audit_logs_actor_idx ON private.audit_logs USING btree (actor_user_id, created_at DESC);
CREATE INDEX audit_logs_entity_idx ON private.audit_logs USING btree (entity_type, entity_id, created_at DESC);
CREATE INDEX commission_rules_active_idx ON private.commission_rules USING btree (is_active, starts_at, ends_at);
CREATE INDEX idx_commission_rules_created_by_fk ON private.commission_rules USING btree (created_by);
CREATE INDEX idx_ledger_entries_account_id_fk ON private.ledger_entries USING btree (account_id);
CREATE INDEX ledger_entries_merchant_idx ON private.ledger_entries USING btree (merchant_id, created_at DESC);
CREATE INDEX ledger_entries_transaction_idx ON private.ledger_entries USING btree (transaction_id);
CREATE UNIQUE INDEX merchant_one_default_payout ON private.merchant_payout_accounts USING btree (merchant_id) WHERE is_default;
CREATE INDEX idx_notification_outbox_user_id_fk ON private.notification_outbox USING btree (user_id);
CREATE INDEX notification_outbox_ready_idx ON private.notification_outbox USING btree (available_at) WHERE (status = ANY (ARRAY['pending'::text, 'failed'::text]));
CREATE UNIQUE INDEX payment_gateway_order_unique ON private.payment_transactions USING btree (gateway, gateway_order_id) WHERE (gateway_order_id IS NOT NULL);
CREATE UNIQUE INDEX payment_gateway_payment_unique ON private.payment_transactions USING btree (gateway, gateway_payment_id) WHERE (gateway_payment_id IS NOT NULL);
CREATE INDEX payment_transactions_order_idx ON private.payment_transactions USING btree (order_id, created_at DESC);
CREATE INDEX payment_webhook_unprocessed_idx ON private.payment_webhook_events USING btree (received_at) WHERE (processing_status = ANY (ARRAY['received'::text, 'failed'::text]));
CREATE INDEX idx_pickup_events_store_id_fk ON private.pickup_events USING btree (store_id);
CREATE INDEX idx_pickup_events_verified_by_fk ON private.pickup_events USING btree (verified_by);
CREATE INDEX pickup_events_order_idx ON private.pickup_events USING btree (order_id, created_at DESC);
CREATE INDEX pickup_tokens_order_idx ON private.pickup_tokens USING btree (order_id);
CREATE INDEX refund_events_actor_user_idx ON private.refund_events USING btree (actor_user_id, created_at DESC);
CREATE INDEX refund_events_refund_idx ON private.refund_events USING btree (refund_id, created_at);
CREATE INDEX idx_refunds_approved_by_fk ON private.refunds USING btree (approved_by);
CREATE INDEX idx_refunds_payment_transaction_id_fk ON private.refunds USING btree (payment_transaction_id);
CREATE INDEX idx_refunds_requested_by_fk ON private.refunds USING btree (requested_by);
CREATE UNIQUE INDEX refunds_gateway_refund_unique ON private.refunds USING btree (gateway_refund_id) WHERE (gateway_refund_id IS NOT NULL);
CREATE UNIQUE INDEX refunds_one_open_per_order ON private.refunds USING btree (order_id) WHERE (status = ANY (ARRAY['requested'::refund_status, 'approved'::refund_status, 'processing'::refund_status]));
CREATE INDEX refunds_order_idx ON private.refunds USING btree (order_id, created_at DESC);
CREATE INDEX idx_settlement_items_order_id_fk ON private.settlement_items USING btree (order_id);
CREATE INDEX idx_settlement_items_settlement_id_fk ON private.settlement_items USING btree (settlement_id);
CREATE INDEX idx_settlements_store_id_fk ON private.settlements USING btree (store_id);
CREATE UNIQUE INDEX settlements_gateway_transfer_unique ON private.settlements USING btree (gateway_transfer_id) WHERE (gateway_transfer_id IS NOT NULL);
CREATE INDEX settlements_merchant_period_idx ON private.settlements USING btree (merchant_id, period_start DESC);
CREATE INDEX idx_categories_parent_id_fk ON public.categories USING btree (parent_id);
CREATE INDEX idx_food_safety_evidence_incident_id_fk ON public.food_safety_evidence USING btree (incident_id);
CREATE INDEX idx_food_safety_evidence_uploaded_by_fk ON public.food_safety_evidence USING btree (uploaded_by);
CREATE INDEX food_safety_incidents_merchant_idx ON public.food_safety_incidents USING btree (merchant_id, reported_at DESC);
CREATE INDEX food_safety_incidents_status_idx ON public.food_safety_incidents USING btree (status, priority, reported_at DESC);
CREATE INDEX idx_food_safety_incidents_assigned_to_fk ON public.food_safety_incidents USING btree (assigned_to);
CREATE INDEX idx_food_safety_incidents_customer_id_fk ON public.food_safety_incidents USING btree (customer_id);
CREATE INDEX idx_food_safety_incidents_listing_id_fk ON public.food_safety_incidents USING btree (listing_id);
CREATE INDEX idx_food_safety_incidents_order_id_fk ON public.food_safety_incidents USING btree (order_id);
CREATE INDEX idx_food_safety_incidents_store_id_fk ON public.food_safety_incidents USING btree (store_id);
CREATE INDEX idx_inventory_events_actor_user_id_fk ON public.inventory_events USING btree (actor_user_id);
CREATE INDEX idx_inventory_events_order_id_fk ON public.inventory_events USING btree (order_id);
CREATE INDEX idx_inventory_events_reservation_id_fk ON public.inventory_events USING btree (reservation_id);
CREATE INDEX inventory_events_listing_created_idx ON public.inventory_events USING btree (listing_id, created_at DESC);
CREATE INDEX idx_inventory_reservations_order_id_fk ON public.inventory_reservations USING btree (order_id);
CREATE UNIQUE INDEX inventory_one_active_reservation_per_item ON public.inventory_reservations USING btree (order_item_id) WHERE (status = 'active'::reservation_status);
CREATE INDEX inventory_reservations_expiry_idx ON public.inventory_reservations USING btree (expires_at) WHERE (status = 'active'::reservation_status);
CREATE INDEX inventory_reservations_listing_status_idx ON public.inventory_reservations USING btree (listing_id, status);
CREATE INDEX listing_images_listing_idx ON public.listing_images USING btree (listing_id, display_order);
CREATE INDEX idx_listing_templates_category_id_fk ON public.listing_templates USING btree (category_id);
CREATE INDEX listing_templates_store_idx ON public.listing_templates USING btree (store_id, is_active);
CREATE INDEX idx_listings_created_by_fk ON public.listings USING btree (created_by);
CREATE INDEX idx_listings_template_id_fk ON public.listings USING btree (template_id);
CREATE INDEX listings_category_idx ON public.listings USING btree (category_id, status);
CREATE INDEX listings_discovery_idx ON public.listings USING btree (status, sale_starts_at, sale_ends_at, pickup_starts_at);
CREATE INDEX listings_store_status_pickup_idx ON public.listings USING btree (store_id, status, pickup_starts_at);
CREATE INDEX listings_type_idx ON public.listings USING btree (listing_type, status);
CREATE INDEX idx_merchant_documents_reviewed_by_fk ON public.merchant_documents USING btree (reviewed_by);
CREATE INDEX idx_merchant_documents_store_id_fk ON public.merchant_documents USING btree (store_id);
CREATE INDEX merchant_documents_merchant_idx ON public.merchant_documents USING btree (merchant_id, verification_status);
CREATE INDEX idx_merchant_memberships_invited_by_fk ON public.merchant_memberships USING btree (invited_by);
CREATE INDEX merchant_memberships_user_idx ON public.merchant_memberships USING btree (user_id, is_active);
CREATE INDEX idx_merchants_approved_by_fk ON public.merchants USING btree (approved_by);
CREATE INDEX idx_merchants_created_by_fk ON public.merchants USING btree (created_by);
CREATE INDEX merchants_status_idx ON public.merchants USING btree (status);
CREATE INDEX notifications_user_unread_idx ON public.notifications USING btree (user_id, created_at DESC) WHERE (read_at IS NULL);
CREATE INDEX order_items_listing_idx ON public.order_items USING btree (listing_id);
CREATE INDEX order_items_order_idx ON public.order_items USING btree (order_id);
CREATE INDEX idx_order_status_events_actor_user_id_fk ON public.order_status_events USING btree (actor_user_id);
CREATE INDEX order_status_events_order_idx ON public.order_status_events USING btree (order_id, created_at);
CREATE INDEX orders_customer_created_idx ON public.orders USING btree (customer_id, created_at DESC);
CREATE INDEX orders_merchant_created_idx ON public.orders USING btree (merchant_id, created_at DESC);
CREATE INDEX orders_store_status_created_idx ON public.orders USING btree (store_id, status, created_at DESC);
CREATE INDEX platform_service_areas_boundary_gix ON public.platform_service_areas USING gist (boundary);
CREATE INDEX idx_platform_user_roles_granted_by_fk ON public.platform_user_roles USING btree (granted_by);
CREATE INDEX idx_reviews_customer_id_fk ON public.reviews USING btree (customer_id);
CREATE INDEX idx_reviews_merchant_id_fk ON public.reviews USING btree (merchant_id);
CREATE INDEX reviews_store_created_idx ON public.reviews USING btree (store_id, created_at DESC);
CREATE INDEX idx_store_staff_memberships_granted_by_fk ON public.store_staff_memberships USING btree (granted_by);
CREATE INDEX store_staff_store_idx ON public.store_staff_memberships USING btree (store_id, is_active);
CREATE INDEX store_staff_user_idx ON public.store_staff_memberships USING btree (user_id, is_active);
CREATE INDEX stores_location_gix ON public.stores USING gist (location);
CREATE INDEX stores_status_city_idx ON public.stores USING btree (status, city);
CREATE INDEX idx_support_messages_sender_user_id_fk ON public.support_messages USING btree (sender_user_id);
CREATE INDEX support_messages_ticket_idx ON public.support_messages USING btree (ticket_id, created_at);
CREATE INDEX idx_support_tickets_assigned_to_fk ON public.support_tickets USING btree (assigned_to);
CREATE INDEX idx_support_tickets_merchant_id_fk ON public.support_tickets USING btree (merchant_id);
CREATE INDEX idx_support_tickets_order_id_fk ON public.support_tickets USING btree (order_id);
CREATE INDEX idx_support_tickets_store_id_fk ON public.support_tickets USING btree (store_id);
CREATE INDEX support_tickets_customer_idx ON public.support_tickets USING btree (customer_id, created_at DESC);
CREATE INDEX support_tickets_status_idx ON public.support_tickets USING btree (status, priority, created_at);
CREATE INDEX idx_user_favourites_store_id_fk ON public.user_favourites USING btree (store_id);

alter table public."categories" enable row level security;
alter table public."food_safety_evidence" enable row level security;
alter table public."food_safety_incidents" enable row level security;
alter table public."inventory_events" enable row level security;
alter table public."inventory_reservations" enable row level security;
alter table public."listing_images" enable row level security;
alter table public."listing_templates" enable row level security;
alter table public."listings" enable row level security;
alter table public."merchant_documents" enable row level security;
alter table public."merchant_memberships" enable row level security;
alter table public."merchants" enable row level security;
alter table public."notifications" enable row level security;
alter table public."order_items" enable row level security;
alter table public."order_status_events" enable row level security;
alter table public."orders" enable row level security;
alter table public."platform_service_areas" enable row level security;
alter table public."platform_user_roles" enable row level security;
alter table public."profiles" enable row level security;
alter table public."reviews" enable row level security;
alter table public."store_hours" enable row level security;
alter table public."store_staff_memberships" enable row level security;
alter table public."stores" enable row level security;
alter table public."support_messages" enable row level security;
alter table public."support_tickets" enable row level security;
alter table public."user_favourites" enable row level security;

create policy "categories_select_active" on public."categories" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (is_active);
create policy "incident_evidence_insert_customer" on public."food_safety_evidence" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (((uploaded_by = ( SELECT auth.uid() AS uid)) AND (EXISTS ( SELECT 1
   FROM food_safety_incidents i
  WHERE ((i.id = food_safety_evidence.incident_id) AND (i.customer_id = ( SELECT auth.uid() AS uid)))))));
create policy "incident_evidence_select_authorized" on public."food_safety_evidence" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((uploaded_by = ( SELECT auth.uid() AS uid)) OR (EXISTS ( SELECT 1
   FROM food_safety_incidents i
  WHERE ((i.id = food_safety_evidence.incident_id) AND ((i.customer_id = ( SELECT auth.uid() AS uid)) OR private.has_platform_role(ARRAY['compliance_admin'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role])))))));
create policy "incidents_insert_customer" on public."food_safety_incidents" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (((customer_id = ( SELECT auth.uid() AS uid)) AND ((order_id IS NULL) OR (EXISTS ( SELECT 1
   FROM orders o
  WHERE ((o.id = food_safety_incidents.order_id) AND (o.customer_id = ( SELECT auth.uid() AS uid)) AND (o.store_id = food_safety_incidents.store_id) AND (o.merchant_id = food_safety_incidents.merchant_id)))))));
create policy "incidents_select_authorized" on public."food_safety_incidents" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((customer_id = ( SELECT auth.uid() AS uid)) OR private.can_manage_store(store_id, ARRAY['owner'::merchant_member_role, 'admin'::merchant_member_role, 'store_manager'::merchant_member_role]) OR private.has_platform_role(ARRAY['compliance_admin'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "inventory_events_select_authorized" on public."inventory_events" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((EXISTS ( SELECT 1
   FROM listings l
  WHERE ((l.id = inventory_events.listing_id) AND private.can_manage_store(l.store_id, ARRAY['owner'::merchant_member_role, 'admin'::merchant_member_role, 'store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role, 'finance_viewer'::merchant_member_role])))) OR private.has_platform_role(ARRAY['operations_admin'::platform_role, 'finance_admin'::platform_role, 'super_admin'::platform_role])));
create policy "inventory_reservations_select_authorized" on public."inventory_reservations" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (private.can_view_order(order_id));
create policy "listing_images_insert_store_operator" on public."listing_images" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check ((EXISTS ( SELECT 1
   FROM listings l
  WHERE ((l.id = listing_images.listing_id) AND private.can_manage_store(l.store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role])))));
create policy "listing_images_select_public_or_member" on public."listing_images" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((EXISTS ( SELECT 1
   FROM listings l
  WHERE ((l.id = listing_images.listing_id) AND (((l.status = 'active'::listing_status) AND (l.sale_starts_at <= now()) AND (l.sale_ends_at > now()) AND (l.available_quantity > 0) AND private.is_store_public(l.store_id)) OR private.can_manage_store(l.store_id, NULL::merchant_member_role[]))))));
create policy "listing_templates_insert_member" on public."listing_templates" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role]));
create policy "listing_templates_select_member" on public."listing_templates" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role]) OR private.has_platform_role(ARRAY['operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "listing_templates_update_member" on public."listing_templates" for UPDATE to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role])) with check (private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role]));
create policy "listings_insert_store_operator" on public."listings" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (((created_by = ( SELECT auth.uid() AS uid)) AND private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role])));
create policy "listings_select_public_or_member" on public."listings" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((((status = 'active'::listing_status) AND (sale_starts_at <= now()) AND (sale_ends_at > now()) AND (available_quantity > 0) AND private.is_store_public(store_id)) OR private.can_manage_store(store_id, NULL::merchant_member_role[]) OR private.has_platform_role(ARRAY['operations_admin'::platform_role, 'compliance_admin'::platform_role, 'super_admin'::platform_role])));
create policy "listings_update_store_operator" on public."listings" for UPDATE to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role])) with check ((private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role, 'inventory_manager'::merchant_member_role]) AND ((status <> 'active'::listing_status) OR ((available_quantity > 0) AND private.is_store_public(store_id)))));
create policy "merchant_documents_insert_authorized" on public."merchant_documents" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (private.is_merchant_member(merchant_id, ARRAY['owner'::merchant_member_role, 'admin'::merchant_member_role]));
create policy "merchant_documents_select_authorized" on public."merchant_documents" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((private.is_merchant_member(merchant_id, ARRAY['owner'::merchant_member_role, 'admin'::merchant_member_role]) OR private.has_platform_role(ARRAY['compliance_admin'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "merchant_memberships_select_related" on public."merchant_memberships" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((user_id = ( SELECT auth.uid() AS uid)) OR private.is_merchant_member(merchant_id, ARRAY['owner'::merchant_member_role, 'admin'::merchant_member_role]) OR private.has_platform_role(ARRAY['operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "merchants_public_read_approved" on public."merchants" for SELECT to {, a, n, o, n, } using ((status = 'approved'::merchant_status));
create policy "merchants_select_approved_or_member" on public."merchants" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((status = 'approved'::merchant_status) OR private.is_merchant_member(id, NULL::merchant_member_role[]) OR private.has_platform_role(ARRAY['support_agent'::platform_role, 'finance_admin'::platform_role, 'compliance_admin'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "notifications_select_own" on public."notifications" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((user_id = ( SELECT auth.uid() AS uid)));
create policy "notifications_update_own" on public."notifications" for UPDATE to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((user_id = ( SELECT auth.uid() AS uid))) with check ((user_id = ( SELECT auth.uid() AS uid)));
create policy "order_items_select_authorized" on public."order_items" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (private.can_view_order(order_id));
create policy "order_status_events_select_authorized" on public."order_status_events" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (private.can_view_order(order_id));
create policy "orders_select_authorized" on public."orders" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((customer_id = ( SELECT auth.uid() AS uid)) OR private.can_manage_store(store_id, ARRAY['owner'::merchant_member_role, 'admin'::merchant_member_role, 'store_manager'::merchant_member_role, 'pickup_operator'::merchant_member_role, 'finance_viewer'::merchant_member_role]) OR private.has_platform_role(ARRAY['support_agent'::platform_role, 'finance_admin'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "service_areas_select_active" on public."platform_service_areas" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (is_active);
create policy "platform_roles_admin_read" on public."platform_user_roles" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (private.has_platform_role(ARRAY['super_admin'::platform_role, 'operations_admin'::platform_role]));
create policy "profiles_select_own" on public."profiles" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((id = ( SELECT auth.uid() AS uid)));
create policy "profiles_update_own" on public."profiles" for UPDATE to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((id = ( SELECT auth.uid() AS uid))) with check ((id = ( SELECT auth.uid() AS uid)));
create policy "reviews_insert_collected_order" on public."reviews" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (((customer_id = ( SELECT auth.uid() AS uid)) AND (EXISTS ( SELECT 1
   FROM orders o
  WHERE ((o.id = reviews.order_id) AND (o.customer_id = ( SELECT auth.uid() AS uid)) AND (o.store_id = reviews.store_id) AND (o.merchant_id = reviews.merchant_id) AND (o.status = 'collected'::order_status))))));
create policy "reviews_select_visible" on public."reviews" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((moderation_status = 'visible'::text) OR (customer_id = ( SELECT auth.uid() AS uid))));
create policy "store_hours_select_public_or_member" on public."store_hours" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((private.is_store_public(store_id) OR private.can_manage_store(store_id, NULL::merchant_member_role[])));
create policy "store_staff_select_related" on public."store_staff_memberships" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((user_id = ( SELECT auth.uid() AS uid)) OR private.can_manage_store(store_id, ARRAY['store_manager'::merchant_member_role]) OR private.has_platform_role(ARRAY['operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "stores_select_public_or_member" on public."stores" for SELECT to {, a, n, o, n, ,, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((private.is_store_public(id) OR private.is_merchant_member(merchant_id, NULL::merchant_member_role[]) OR private.has_platform_role(ARRAY['operations_admin'::platform_role, 'compliance_admin'::platform_role, 'super_admin'::platform_role])));
create policy "support_messages_insert_customer" on public."support_messages" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (((sender_user_id = ( SELECT auth.uid() AS uid)) AND (sender_type = 'customer'::text) AND (is_internal = false) AND (EXISTS ( SELECT 1
   FROM support_tickets t
  WHERE ((t.id = support_messages.ticket_id) AND (t.customer_id = ( SELECT auth.uid() AS uid)))))));
create policy "support_messages_select_authorized" on public."support_messages" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((EXISTS ( SELECT 1
   FROM support_tickets t
  WHERE ((t.id = support_messages.ticket_id) AND ((t.customer_id = ( SELECT auth.uid() AS uid)) OR private.has_platform_role(ARRAY['support_agent'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role]))))) AND ((is_internal = false) OR private.has_platform_role(ARRAY['support_agent'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role]))));
create policy "support_tickets_insert_customer" on public."support_tickets" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check (((customer_id = ( SELECT auth.uid() AS uid)) AND ((order_id IS NULL) OR (EXISTS ( SELECT 1
   FROM orders o
  WHERE ((o.id = support_tickets.order_id) AND (o.customer_id = ( SELECT auth.uid() AS uid))))))));
create policy "support_tickets_select_authorized" on public."support_tickets" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using (((customer_id = ( SELECT auth.uid() AS uid)) OR private.has_platform_role(ARRAY['support_agent'::platform_role, 'operations_admin'::platform_role, 'super_admin'::platform_role])));
create policy "favourites_delete_own" on public."user_favourites" for DELETE to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((user_id = ( SELECT auth.uid() AS uid)));
create policy "favourites_insert_own" on public."user_favourites" for INSERT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } with check ((user_id = ( SELECT auth.uid() AS uid)));
create policy "favourites_select_own" on public."user_favourites" for SELECT to {, a, u, t, h, e, n, t, i, c, a, t, e, d, } using ((user_id = ( SELECT auth.uid() AS uid)));

CREATE OR REPLACE FUNCTION private.apply_merchant_application(p_legal_name text, p_display_name text, p_business_type merchant_business_type, p_business_email text DEFAULT NULL::text, p_business_phone text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_user_id uuid := auth.uid();
  v_merchant_id uuid;
begin
  if v_user_id is null then raise exception 'authentication_required' using errcode = '28000'; end if;
  if nullif(trim(p_legal_name),'') is null or nullif(trim(p_display_name),'') is null then
    raise exception 'business_name_required' using errcode = '22023';
  end if;
  insert into public.merchants (
    legal_name, display_name, business_type, business_email, business_phone, created_by
  ) values (
    trim(p_legal_name), trim(p_display_name), p_business_type,
    nullif(trim(p_business_email),''), nullif(trim(p_business_phone),''), v_user_id
  ) returning id into v_merchant_id;
  insert into public.merchant_memberships (merchant_id, user_id, role)
  values (v_merchant_id, v_user_id, 'owner');
  return v_merchant_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.attach_gateway_order(p_payment_transaction_id uuid, p_gateway_order_id text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_payment private.payment_transactions%rowtype;
begin
  if nullif(trim(p_gateway_order_id),'') is null then
    raise exception 'gateway_order_id_required' using errcode='22023';
  end if;
  select * into v_payment from private.payment_transactions
  where id=p_payment_transaction_id for update;
  if not found then raise exception 'payment_transaction_not_found' using errcode='P0002'; end if;
  if v_payment.status <> 'created' then
    raise exception 'payment_transaction_not_attachable' using errcode='P0001';
  end if;
  if v_payment.gateway_order_id is not null and v_payment.gateway_order_id <> p_gateway_order_id then
    raise exception 'gateway_order_id_conflict' using errcode='22023';
  end if;
  update private.payment_transactions
    set gateway_order_id=p_gateway_order_id,updated_at=now()
    where id=p_payment_transaction_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.begin_payment_checkout(p_order_id uuid, p_idempotency_key text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_user_id uuid := auth.uid();
  v_order public.orders%rowtype;
  v_payment_id uuid;
  v_item_count integer;
  v_live_reservation_count integer;
begin
  if v_user_id is null then raise exception 'authentication_required' using errcode = '28000'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 then
    raise exception 'invalid_idempotency_key' using errcode = '22023';
  end if;

  select * into v_order from public.orders
  where id = p_order_id and customer_id = v_user_id for update;
  if not found then raise exception 'order_not_found' using errcode = 'P0002'; end if;
  if v_order.status <> 'pending_payment' then raise exception 'order_not_payable' using errcode = 'P0001'; end if;

  select count(*) into v_item_count from public.order_items where order_id = p_order_id;
  select count(*) into v_live_reservation_count
  from public.inventory_reservations
  where order_id = p_order_id and status = 'active' and expires_at > now();

  if v_item_count = 0 or v_live_reservation_count <> v_item_count then
    raise exception 'reservation_expired_or_incomplete' using errcode = 'P0001';
  end if;

  select id into v_payment_id
  from private.payment_transactions
  where idempotency_key = p_idempotency_key;

  if v_payment_id is null then
    insert into private.payment_transactions(order_id,gateway,amount,currency,status,idempotency_key)
    values (p_order_id,'razorpay',v_order.total_amount,v_order.currency,'created',p_idempotency_key)
    returning id into v_payment_id;
  elsif not exists (
    select 1 from private.payment_transactions
    where id = v_payment_id and order_id = p_order_id
  ) then
    raise exception 'payment_idempotency_conflict' using errcode = '22023';
  end if;

  return jsonb_build_object(
    'payment_transaction_id',v_payment_id,'order_id',p_order_id,
    'amount',v_order.total_amount,'currency',v_order.currency,'gateway','razorpay'
  );
end;
$function$;

CREATE OR REPLACE FUNCTION private.can_manage_store(p_store_id uuid, p_roles merchant_member_role[] DEFAULT NULL::merchant_member_role[])
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select auth.uid() is not null and exists (
    select 1
    from public.stores s
    join public.merchant_memberships mm on mm.merchant_id = s.merchant_id
    where s.id = p_store_id
      and mm.user_id = auth.uid()
      and mm.is_active
      and (
        mm.role in ('owner','admin')
        or (
          p_roles is not null
          and exists (
            select 1 from public.store_staff_memberships sm
            where sm.store_id = s.id
              and sm.user_id = auth.uid()
              and sm.is_active
              and sm.role = any(p_roles)
          )
        )
      )
  );
$function$;

CREATE OR REPLACE FUNCTION private.can_view_order(p_order_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select auth.uid() is not null and exists (
    select 1 from public.orders o
    where o.id = p_order_id
      and (
        o.customer_id = auth.uid()
        or private.can_manage_store(o.store_id, array[
          'owner','admin','store_manager','pickup_operator','finance_viewer'
        ]::public.merchant_member_role[])
        or private.has_platform_role(array[
          'support_agent','finance_admin','compliance_admin','operations_admin','super_admin'
        ]::public.platform_role[])
      )
  );
$function$;

CREATE OR REPLACE FUNCTION private.confirm_payment_capture(p_payment_transaction_id uuid, p_gateway_payment_id text, p_amount numeric, p_signature_verified boolean)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_payment private.payment_transactions%rowtype;
  v_order public.orders%rowtype;
  v_reservation record;
  v_item_count integer;
  v_live_reservation_count integer;
begin
  if p_signature_verified is not true then
    raise exception 'gateway_signature_not_verified' using errcode = '42501';
  end if;

  select * into v_payment from private.payment_transactions
  where id = p_payment_transaction_id for update;
  if not found then raise exception 'payment_transaction_not_found' using errcode = 'P0002'; end if;

  select * into v_order from public.orders where id = v_payment.order_id for update;
  if not found then raise exception 'order_not_found' using errcode = 'P0002'; end if;
  if v_payment.status = 'captured' then return v_order.id; end if;

  if p_amount <> v_payment.amount then
    update private.payment_transactions set status='reconciliation_required',
      gateway_payment_id=p_gateway_payment_id,gateway_signature_verified=true,
      failure_code='AMOUNT_MISMATCH',updated_at=now() where id=v_payment.id;
    update public.orders set payment_status='reconciliation_required' where id=v_order.id;
    return v_order.id;
  end if;

  select count(*) into v_item_count from public.order_items where order_id=v_order.id;
  select count(*) into v_live_reservation_count
  from public.inventory_reservations
  where order_id=v_order.id and status='active' and expires_at>now();

  if v_order.status <> 'pending_payment' or v_item_count = 0
    or v_live_reservation_count <> v_item_count then
    update private.payment_transactions set status='reconciliation_required',
      gateway_payment_id=p_gateway_payment_id,gateway_signature_verified=true,
      failure_code='RESERVATION_NOT_ACTIVE_OR_INCOMPLETE',updated_at=now()
      where id=v_payment.id;
    update public.orders set payment_status='reconciliation_required' where id=v_order.id;
    return v_order.id;
  end if;

  update private.payment_transactions set status='captured',
    gateway_payment_id=p_gateway_payment_id,gateway_signature_verified=true,
    captured_at=now(),updated_at=now() where id=v_payment.id;

  for v_reservation in
    select * from public.inventory_reservations
    where order_id=v_order.id and status='active' for update
  loop
    update public.listings set
      reserved_quantity=reserved_quantity-v_reservation.quantity,
      sold_quantity=sold_quantity+v_reservation.quantity
      where id=v_reservation.listing_id;
    update public.inventory_reservations set status='consumed',consumed_at=now()
      where id=v_reservation.id;
    insert into public.inventory_events(
      listing_id,order_id,reservation_id,event_type,quantity_delta,actor_user_id,reason
    ) values (
      v_reservation.listing_id,v_order.id,v_reservation.id,'sold',
      -v_reservation.quantity,null,'payment_captured'
    );
  end loop;

  update public.orders set payment_status='captured',status='confirmed',confirmed_at=now()
  where id=v_order.id;
  insert into public.order_status_events(order_id,from_status,to_status,actor_type,reason)
  values (v_order.id,'pending_payment','confirmed','system','payment_captured');
  return v_order.id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.create_merchant_store(p_merchant_id uuid, p_name text, p_slug text, p_address_line_1 text, p_address_line_2 text, p_locality text, p_city text, p_state text, p_pincode text, p_latitude double precision, p_longitude double precision, p_contact_phone text DEFAULT NULL::text, p_pickup_instructions text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_store_id uuid;
begin
  if auth.uid() is null then raise exception 'authentication_required' using errcode = '28000'; end if;
  if not private.is_merchant_member(
    p_merchant_id, array['owner','admin']::public.merchant_member_role[]
  ) then raise exception 'merchant_access_denied' using errcode = '42501'; end if;
  if p_latitude is not null and (p_latitude < -90 or p_latitude > 90) then
    raise exception 'invalid_latitude' using errcode = '22023';
  end if;
  if p_longitude is not null and (p_longitude < -180 or p_longitude > 180) then
    raise exception 'invalid_longitude' using errcode = '22023';
  end if;
  insert into public.stores (
    merchant_id,name,slug,address_line_1,address_line_2,locality,city,state,pincode,
    location,contact_phone,pickup_instructions,status
  ) values (
    p_merchant_id,trim(p_name),lower(trim(p_slug)),trim(p_address_line_1),
    nullif(trim(p_address_line_2),''),nullif(trim(p_locality),''),trim(p_city),
    trim(p_state),trim(p_pincode),
    case when p_latitude is null or p_longitude is null then null
      else extensions.st_setsrid(extensions.st_makepoint(p_longitude,p_latitude),4326)::extensions.geography
    end,
    p_contact_phone,p_pickup_instructions,'draft'
  ) returning id into v_store_id;
  return v_store_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.create_order_reservation(p_store_id uuid, p_items jsonb, p_idempotency_key text, p_customer_note text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_user_id uuid := auth.uid();
  v_store public.stores%rowtype;
  v_merchant_status public.merchant_status;
  v_item record;
  v_listing public.listings%rowtype;
  v_order_id uuid;
  v_order_number text;
  v_order_item_id uuid;
  v_item_count integer;
  v_distinct_count integer;
  v_subtotal numeric(12,2) := 0;
  v_pickup_start timestamptz := '1900-01-01 00:00:00+00'::timestamptz;
  v_pickup_end timestamptz := 'infinity'::timestamptz;
  v_expiry timestamptz := now() + interval '5 minutes';
  v_snapshots jsonb := '[]'::jsonb;
  v_request_hash text;
  v_existing_hash text;
  v_existing_status public.order_status;
  v_existing_total numeric(12,2);
  v_existing_pickup_start timestamptz;
  v_existing_pickup_end timestamptz;
begin
  if v_user_id is null then raise exception 'authentication_required' using errcode = '28000'; end if;
  if p_idempotency_key is null or length(trim(p_idempotency_key)) < 8 or length(p_idempotency_key) > 128 then
    raise exception 'invalid_idempotency_key' using errcode = '22023';
  end if;
  if jsonb_typeof(p_items) <> 'array' then raise exception 'items_must_be_array' using errcode = '22023'; end if;

  select count(*), count(distinct (e.value->>'listing_id')::uuid)
    into v_item_count, v_distinct_count
  from jsonb_array_elements(p_items) e(value);
  if v_item_count < 1 or v_item_count > 20 or v_item_count <> v_distinct_count then
    raise exception 'invalid_or_duplicate_order_items' using errcode = '22023';
  end if;

  v_request_hash := encode(extensions.digest(
    p_store_id::text || '|' || p_items::text || '|' || coalesce(p_customer_note,''), 'sha256'
  ), 'hex');

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(v_user_id::text || '|' || p_idempotency_key, 0)
  );

  select id, request_hash, order_number, status, total_amount, pickup_starts_at, pickup_ends_at
    into v_order_id, v_existing_hash, v_order_number, v_existing_status,
         v_existing_total, v_existing_pickup_start, v_existing_pickup_end
  from public.orders
  where customer_id = v_user_id and request_idempotency_key = p_idempotency_key;

  if found then
    if v_existing_hash <> v_request_hash then
      raise exception 'idempotency_key_reused_with_different_request' using errcode = '22023';
    end if;
    return jsonb_build_object(
      'order_id',v_order_id,'order_number',v_order_number,'status',v_existing_status,
      'total_amount',v_existing_total,'pickup_starts_at',v_existing_pickup_start,
      'pickup_ends_at',v_existing_pickup_end,'idempotent_replay',true
    );
  end if;

  select * into v_store from public.stores where id = p_store_id;
  if not found or v_store.status <> 'active' then raise exception 'store_unavailable' using errcode = 'P0001'; end if;
  select status into v_merchant_status from public.merchants where id = v_store.merchant_id;
  if v_merchant_status <> 'approved' then raise exception 'merchant_unavailable' using errcode = 'P0001'; end if;

  for v_item in
    select (e.value->>'listing_id')::uuid as listing_id,
           (e.value->>'quantity')::integer as quantity
    from jsonb_array_elements(p_items) e(value)
    order by 1
  loop
    if v_item.quantity is null or v_item.quantity < 1 or v_item.quantity > 20 then
      raise exception 'invalid_item_quantity' using errcode = '22023';
    end if;
    select * into v_listing from public.listings where id = v_item.listing_id for update;
    if not found or v_listing.store_id <> p_store_id then
      raise exception 'listing_not_found_for_store' using errcode = 'P0001';
    end if;
    if v_listing.status <> 'active' or v_listing.sale_starts_at > now()
      or v_listing.sale_ends_at <= now() or v_listing.pickup_ends_at <= now() then
      raise exception 'listing_not_available' using errcode = 'P0001';
    end if;
    if v_listing.available_quantity < v_item.quantity then
      raise exception 'insufficient_inventory' using errcode = 'P0001';
    end if;

    v_subtotal := v_subtotal + (v_listing.selling_price * v_item.quantity);
    v_pickup_start := greatest(v_pickup_start,v_listing.pickup_starts_at);
    v_pickup_end := least(v_pickup_end,v_listing.pickup_ends_at);
    v_snapshots := v_snapshots || jsonb_build_array(jsonb_build_object(
      'listing_id',v_listing.id,'listing_type',v_listing.listing_type,
      'title',v_listing.title,'description',v_listing.description,
      'allergens',v_listing.allergen_codes,'dietary',v_listing.dietary_classification,
      'quantity',v_item.quantity,'unit_price',v_listing.selling_price,
      'reference_value',v_listing.reference_value
    ));
  end loop;

  if v_pickup_end <= v_pickup_start or v_pickup_end <= now() then
    raise exception 'no_common_pickup_window' using errcode = 'P0001';
  end if;

  v_order_number := 'SF-' || to_char(now() at time zone 'Asia/Kolkata','YYYYMMDD') || '-' ||
    lpad(nextval('public.order_number_seq')::text,6,'0');

  insert into public.orders (
    order_number,customer_id,merchant_id,store_id,status,payment_status,
    subtotal_amount,discount_amount,platform_fee_amount,tax_amount,total_amount,
    pickup_starts_at,pickup_ends_at,customer_note,request_idempotency_key,request_hash
  ) values (
    v_order_number,v_user_id,v_store.merchant_id,p_store_id,'pending_payment','created',
    v_subtotal,0,0,0,v_subtotal,v_pickup_start,v_pickup_end,p_customer_note,p_idempotency_key,v_request_hash
  ) returning id into v_order_id;

  for v_item in select e.value from jsonb_array_elements(v_snapshots) e(value)
  loop
    insert into public.order_items (
      order_id,listing_id,listing_type,listing_title_snapshot,listing_description_snapshot,
      allergen_codes_snapshot,dietary_classification_snapshot,quantity,unit_price,
      reference_value_snapshot,line_total
    ) values (
      v_order_id,(v_item.value->>'listing_id')::uuid,
      (v_item.value->>'listing_type')::public.listing_type,
      v_item.value->>'title',v_item.value->>'description',
      array(select jsonb_array_elements_text(v_item.value->'allergens')),
      (v_item.value->>'dietary')::public.dietary_classification,
      (v_item.value->>'quantity')::integer,(v_item.value->>'unit_price')::numeric,
      (v_item.value->>'reference_value')::numeric,
      (v_item.value->>'unit_price')::numeric * (v_item.value->>'quantity')::integer
    ) returning id into v_order_item_id;

    update public.listings
      set reserved_quantity = reserved_quantity + (v_item.value->>'quantity')::integer
      where id = (v_item.value->>'listing_id')::uuid;

    insert into public.inventory_reservations(order_id,order_item_id,listing_id,quantity,expires_at)
    values (
      v_order_id,v_order_item_id,(v_item.value->>'listing_id')::uuid,
      (v_item.value->>'quantity')::integer,v_expiry
    );

    insert into public.inventory_events(listing_id,order_id,event_type,quantity_delta,actor_user_id,reason)
    values (
      (v_item.value->>'listing_id')::uuid,v_order_id,'reserved',
      -(v_item.value->>'quantity')::integer,v_user_id,'customer_checkout'
    );
  end loop;

  insert into public.order_status_events(order_id,from_status,to_status,actor_user_id,actor_type,reason)
  values (v_order_id,null,'pending_payment',v_user_id,'customer','reservation_created');

  return jsonb_build_object(
    'order_id',v_order_id,'order_number',v_order_number,'status','pending_payment',
    'total_amount',v_subtotal,'currency','INR','reservation_expires_at',v_expiry,
    'pickup_starts_at',v_pickup_start,'pickup_ends_at',v_pickup_end,'idempotent_replay',false
  );
end;
$function$;

CREATE OR REPLACE FUNCTION private.handle_new_auth_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  insert into public.profiles (id, full_name, phone_e164)
  values (
    new.id,
    nullif(new.raw_user_meta_data ->> 'full_name',''),
    new.phone
  )
  on conflict (id) do nothing;
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION private.has_platform_role(p_roles platform_role[])
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select auth.uid() is not null and exists (
    select 1 from public.platform_user_roles r
    where r.user_id = auth.uid()
      and r.revoked_at is null
      and r.role = any(p_roles)
  );
$function$;

CREATE OR REPLACE FUNCTION private.is_merchant_member(p_merchant_id uuid, p_roles merchant_member_role[] DEFAULT NULL::merchant_member_role[])
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select auth.uid() is not null and exists (
    select 1 from public.merchant_memberships mm
    where mm.merchant_id = p_merchant_id
      and mm.user_id = auth.uid()
      and mm.is_active
      and (p_roles is null or mm.role = any(p_roles))
  );
$function$;

CREATE OR REPLACE FUNCTION private.is_store_public(p_store_id uuid)
 RETURNS boolean
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
  select exists (
    select 1
    from public.stores s
    join public.merchants m on m.id = s.merchant_id
    where s.id = p_store_id
      and s.status = 'active'
      and m.status = 'approved'
  );
$function$;

CREATE OR REPLACE FUNCTION private.issue_pickup_token(p_order_id uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_user_id uuid := auth.uid();
  v_order public.orders%rowtype;
  v_token text;
  v_token_id uuid;
begin
  if v_user_id is null then raise exception 'authentication_required' using errcode = '28000'; end if;
  select * into v_order from public.orders
  where id = p_order_id and customer_id = v_user_id for update;
  if not found or v_order.status not in ('confirmed','ready_for_pickup') then
    raise exception 'pickup_not_available' using errcode = 'P0001';
  end if;
  if now() > v_order.pickup_ends_at + interval '30 minutes' then
    raise exception 'pickup_window_expired' using errcode = 'P0001';
  end if;

  update private.pickup_tokens set invalidated_at = now()
  where order_id = p_order_id and used_at is null and invalidated_at is null;

  v_token := encode(extensions.gen_random_bytes(32),'hex');
  insert into private.pickup_tokens(order_id,token_hash,expires_at)
  values (p_order_id,encode(extensions.digest(v_token,'sha256'),'hex'),v_order.pickup_ends_at + interval '30 minutes')
  returning id into v_token_id;

  return jsonb_build_object(
    'pickup_token_id',v_token_id,'pickup_token',v_token,
    'expires_at',v_order.pickup_ends_at + interval '30 minutes'
  );
end;
$function$;

CREATE OR REPLACE FUNCTION private.mark_payment_failed(p_payment_transaction_id uuid, p_failure_code text, p_failure_description text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_payment private.payment_transactions%rowtype;
begin
  select * into v_payment from private.payment_transactions
  where id=p_payment_transaction_id for update;
  if not found then raise exception 'payment_transaction_not_found' using errcode='P0002'; end if;
  if v_payment.status='captured' then
    raise exception 'captured_payment_cannot_be_failed' using errcode='P0001';
  end if;
  update private.payment_transactions
    set status='failed',failure_code=p_failure_code,
        failure_description=p_failure_description,updated_at=now()
    where id=p_payment_transaction_id;
  update public.orders
    set payment_status='failed'
    where id=v_payment.order_id and status='pending_payment'
      and not exists (
        select 1 from private.payment_transactions p
        where p.order_id=v_payment.order_id
          and p.id<>p_payment_transaction_id
          and p.status in ('created','authorized','captured','reconciliation_required')
      );
  return v_payment.order_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.post_ledger_transaction(p_reference_type text, p_reference_id uuid, p_description text, p_currency character, p_entries jsonb)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_transaction_id uuid;
  v_existing_status text;
  v_entry jsonb;
  v_account_id uuid;
  v_merchant_id uuid;
  v_debit numeric(14,2);
  v_credit numeric(14,2);
  v_total_debits numeric(14,2) := 0;
  v_total_credits numeric(14,2) := 0;
  v_count integer := 0;
begin
  if nullif(trim(p_reference_type),'') is null or p_reference_id is null then
    raise exception 'ledger_reference_required' using errcode='22023';
  end if;
  if p_currency <> 'INR' then raise exception 'unsupported_ledger_currency' using errcode='22023'; end if;
  if jsonb_typeof(p_entries)<>'array' or jsonb_array_length(p_entries)<2 or jsonb_array_length(p_entries)>50 then
    raise exception 'ledger_entries_must_be_array_of_2_to_50' using errcode='22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_reference_type || '|' || p_reference_id::text,0)
  );

  select id,status into v_transaction_id,v_existing_status
  from private.ledger_transactions
  where reference_type=p_reference_type and reference_id=p_reference_id
  for update;

  if found then
    if v_existing_status='posted' then return v_transaction_id; end if;
    raise exception 'ledger_reference_already_exists_unposted' using errcode='P0001';
  end if;

  insert into private.ledger_transactions(reference_type,reference_id,description,currency,status)
  values (p_reference_type,p_reference_id,p_description,p_currency,'draft')
  returning id into v_transaction_id;

  for v_entry in select value from jsonb_array_elements(p_entries)
  loop
    v_count := v_count+1;
    v_debit := coalesce((v_entry->>'debit')::numeric,0);
    v_credit := coalesce((v_entry->>'credit')::numeric,0);
    v_merchant_id := nullif(v_entry->>'merchant_id','')::uuid;

    if v_debit<0 or v_credit<0 or
       ((v_debit>0 and v_credit>0) or (v_debit=0 and v_credit=0)) then
      raise exception 'invalid_ledger_entry_amount' using errcode='22023';
    end if;

    select id into v_account_id
    from private.ledger_accounts
    where account_code=v_entry->>'account_code'
      and is_active and currency=p_currency;

    if v_account_id is null then
      raise exception 'ledger_account_not_found_or_inactive: %',v_entry->>'account_code'
        using errcode='P0001';
    end if;

    insert into private.ledger_entries(
      transaction_id,account_id,merchant_id,debit_amount,credit_amount,currency
    ) values (
      v_transaction_id,v_account_id,v_merchant_id,v_debit,v_credit,p_currency
    );

    v_total_debits := v_total_debits+v_debit;
    v_total_credits := v_total_credits+v_credit;
  end loop;

  if v_count<2 or v_total_debits<=0 or v_total_debits<>v_total_credits then
    raise exception 'ledger_transaction_not_balanced: debits %, credits %',
      v_total_debits,v_total_credits using errcode='22023';
  end if;

  update private.ledger_transactions
  set status='posted',posted_at=now()
  where id=v_transaction_id;

  return v_transaction_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.prevent_posted_ledger_entry_mutation()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
declare v_status text;
begin
  select status into v_status
  from private.ledger_transactions
  where id=coalesce(old.transaction_id,new.transaction_id);

  if v_status='posted' then
    raise exception 'posted_ledger_entries_are_immutable' using errcode='55000';
  end if;

  if tg_op='DELETE' then return old; end if;
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION private.prevent_posted_ledger_transaction_mutation()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  if old.status='posted' then
    raise exception 'posted_ledger_transactions_are_immutable_use_reversal' using errcode='55000';
  end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION private.record_payment_webhook_event(p_gateway text, p_gateway_event_id text, p_event_type text, p_payload jsonb, p_signature_verified boolean)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_event_id uuid;
begin
  if p_signature_verified is not true then
    raise exception 'webhook_signature_not_verified' using errcode='42501';
  end if;
  if nullif(trim(p_gateway_event_id),'') is null then
    raise exception 'gateway_event_id_required' using errcode='22023';
  end if;
  insert into private.payment_webhook_events(
    gateway,gateway_event_id,event_type,payload,signature_verified
  ) values (
    p_gateway,p_gateway_event_id,p_event_type,coalesce(p_payload,'{}'::jsonb),true
  )
  on conflict (gateway,gateway_event_id) do update
    set gateway_event_id=excluded.gateway_event_id
  returning id into v_event_id;
  return v_event_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.release_expired_inventory_reservations(p_limit integer DEFAULT 100)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_reservation record;
  v_count integer := 0;
begin
  if p_limit < 1 or p_limit > 1000 then raise exception 'invalid_batch_limit' using errcode='22023'; end if;

  for v_reservation in
    select r.id,r.order_id,r.listing_id,r.quantity
    from public.inventory_reservations r
    join public.orders o on o.id=r.order_id
    where r.status='active' and r.expires_at<=now() and o.status='pending_payment'
      and not exists (
        select 1 from private.payment_transactions p
        where p.order_id=o.id and p.status in ('created','authorized','captured','reconciliation_required')
      )
    order by r.expires_at
    for update of r skip locked
    limit p_limit
  loop
    update public.listings set reserved_quantity=reserved_quantity-v_reservation.quantity
    where id=v_reservation.listing_id;
    update public.inventory_reservations set status='expired',released_at=now()
    where id=v_reservation.id;
    insert into public.inventory_events(
      listing_id,order_id,reservation_id,event_type,quantity_delta,actor_user_id,reason
    ) values (
      v_reservation.listing_id,v_reservation.order_id,v_reservation.id,
      'reservation_released',v_reservation.quantity,null,'reservation_expired_after_payment_failure_or_no_payment'
    );

    if not exists (
      select 1 from public.inventory_reservations r
      where r.order_id=v_reservation.order_id and r.status='active'
    ) then
      update public.orders set status='expired',payment_status='failed'
      where id=v_reservation.order_id and status='pending_payment';
      insert into public.order_status_events(order_id,from_status,to_status,actor_type,reason)
      values (v_reservation.order_id,'pending_payment','expired','system','reservation_expired');
    end if;
    v_count := v_count + 1;
  end loop;
  return v_count;
end;
$function$;

CREATE OR REPLACE FUNCTION private.request_order_refund(p_order_id uuid, p_reason_code text, p_description text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_user_id uuid := auth.uid();
  v_order public.orders%rowtype;
  v_payment_id uuid;
  v_refund_id uuid;
begin
  if v_user_id is null then raise exception 'authentication_required' using errcode='28000'; end if;
  if nullif(trim(p_reason_code),'') is null then raise exception 'refund_reason_required' using errcode='22023'; end if;

  select * into v_order from public.orders
  where id=p_order_id and customer_id=v_user_id for update;
  if not found then raise exception 'order_not_found' using errcode='P0002'; end if;
  if v_order.payment_status <> 'captured'
    or v_order.status not in ('confirmed','ready_for_pickup','collected') then
    raise exception 'order_not_eligible_for_refund' using errcode='P0001';
  end if;

  select id into v_payment_id from private.payment_transactions
  where order_id=p_order_id and status='captured'
  order by captured_at desc limit 1;
  if v_payment_id is null then raise exception 'captured_payment_not_found' using errcode='P0001'; end if;

  insert into private.refunds(
    order_id,payment_transaction_id,requested_by,amount,reason_code,customer_description,status
  ) values (
    p_order_id,v_payment_id,v_user_id,v_order.total_amount,
    p_reason_code,left(p_description,2000),'requested'
  ) returning id into v_refund_id;

  update public.orders
    set payment_status='refund_pending',
        status=case when status='collected' then status else 'refund_pending'::public.order_status end
    where id=p_order_id;

  insert into private.refund_events(refund_id,from_status,to_status,actor_user_id,actor_type,reason)
  values (v_refund_id,null,'requested',v_user_id,'customer',p_reason_code);

  return v_refund_id;
exception
  when unique_violation then
    raise exception 'refund_already_open_for_order' using errcode='23505';
end;
$function$;

CREATE OR REPLACE FUNCTION private.reverse_ledger_transaction(p_original_transaction_id uuid, p_reason text, p_reversal_reference_id uuid)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_original private.ledger_transactions%rowtype;
  v_entries jsonb;
  v_reversal_id uuid;
begin
  select * into v_original
  from private.ledger_transactions
  where id=p_original_transaction_id and status='posted';
  if not found then raise exception 'posted_original_ledger_transaction_required' using errcode='P0001'; end if;

  select jsonb_agg(jsonb_build_object(
    'account_code',a.account_code,
    'merchant_id',e.merchant_id,
    'debit',e.credit_amount,
    'credit',e.debit_amount
  ))
  into v_entries
  from private.ledger_entries e
  join private.ledger_accounts a on a.id=e.account_id
  where e.transaction_id=p_original_transaction_id;

  v_reversal_id := private.post_ledger_transaction(
    'reversal:'||v_original.reference_type,
    p_reversal_reference_id,
    'Reversal of '||v_original.id::text||': '||coalesce(p_reason,''),
    v_original.currency,
    v_entries
  );

  return v_reversal_id;
end;
$function$;

CREATE OR REPLACE FUNCTION private.review_merchant_application(p_merchant_id uuid, p_new_status merchant_status, p_verification_status verification_status, p_review_notes text, p_reviewer_id uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
  if p_reviewer_id is null or not exists (
    select 1 from public.platform_user_roles r
    where r.user_id=p_reviewer_id and r.revoked_at is null
      and r.role in ('compliance_admin','operations_admin','super_admin')
  ) then
    raise exception 'reviewer_not_authorized' using errcode='42501';
  end if;

  if p_new_status='approved' then
    if p_verification_status <> 'verified' then
      raise exception 'merchant_documents_must_be_verified' using errcode='22023';
    end if;
    if not exists (
      select 1 from public.merchant_documents d
      where d.merchant_id=p_merchant_id
        and d.document_type in ('fssai_registration','fssai_license')
        and d.verification_status='verified'
        and (d.valid_until is null or d.valid_until >= current_date)
    ) then
      raise exception 'verified_fssai_document_required' using errcode='P0001';
    end if;
  end if;

  update public.merchants
  set status=p_new_status,
      verification_status=p_verification_status,
      onboarding_notes=p_review_notes,
      approved_at=case when p_new_status='approved' then now() else approved_at end,
      approved_by=case when p_new_status='approved' then p_reviewer_id else approved_by end,
      updated_at=now()
  where id=p_merchant_id;

  if not found then raise exception 'merchant_not_found' using errcode='P0002'; end if;

  insert into private.audit_logs(
    actor_user_id,actor_type,action,entity_type,entity_id,after_data
  ) values (
    p_reviewer_id,'admin','merchant_application_reviewed','merchant',p_merchant_id,
    jsonb_build_object('status',p_new_status,'verification_status',p_verification_status,'review_notes',p_review_notes)
  );
end;
$function$;

CREATE OR REPLACE FUNCTION private.review_store_activation(p_store_id uuid, p_activate boolean, p_reviewer_id uuid, p_reason text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_merchant_id uuid;
begin
  if p_reviewer_id is null or not exists (
    select 1 from public.platform_user_roles r
    where r.user_id=p_reviewer_id and r.revoked_at is null
      and r.role in ('operations_admin','compliance_admin','super_admin')
  ) then
    raise exception 'reviewer_not_authorized' using errcode='42501';
  end if;

  select merchant_id into v_merchant_id from public.stores where id=p_store_id for update;
  if not found then raise exception 'store_not_found' using errcode='P0002'; end if;

  if p_activate then
    if not exists (
      select 1 from public.merchants m
      where m.id=v_merchant_id and m.status='approved' and m.verification_status='verified'
    ) then
      raise exception 'merchant_not_approved_and_verified' using errcode='P0001';
    end if;
    if not exists (
      select 1 from public.stores s where s.id=p_store_id and s.location is not null
    ) then
      raise exception 'store_location_required' using errcode='P0001';
    end if;
    if not exists (select 1 from public.store_hours h where h.store_id=p_store_id) then
      raise exception 'store_hours_required' using errcode='P0001';
    end if;
    update public.stores set status='active',updated_at=now() where id=p_store_id;
  else
    update public.stores set status='inactive',updated_at=now() where id=p_store_id;
  end if;

  insert into private.audit_logs(
    actor_user_id,actor_type,action,entity_type,entity_id,after_data
  ) values (
    p_reviewer_id,'admin',case when p_activate then 'store_activated' else 'store_deactivated' end,
    'store',p_store_id,jsonb_build_object('reason',p_reason)
  );
end;
$function$;

CREATE OR REPLACE FUNCTION private.update_refund_status(p_refund_id uuid, p_new_status refund_status, p_actor_user_id uuid, p_actor_type text, p_reason text DEFAULT NULL::text, p_gateway_refund_id text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare v_refund private.refunds%rowtype;
begin
  if p_actor_type not in ('admin','system','webhook') then
    raise exception 'invalid_refund_actor_type' using errcode='22023';
  end if;

  if p_actor_type='admin' and (
    p_actor_user_id is null or not exists (
      select 1 from public.platform_user_roles r
      where r.user_id=p_actor_user_id and r.revoked_at is null
        and r.role in ('finance_admin','operations_admin','super_admin')
    )
  ) then
    raise exception 'refund_actor_not_authorized' using errcode='42501';
  end if;

  select * into v_refund from private.refunds where id=p_refund_id for update;
  if not found then raise exception 'refund_not_found' using errcode='P0002'; end if;

  if not (
    (v_refund.status='requested' and p_new_status in ('approved','rejected'))
    or (v_refund.status='approved' and p_new_status='processing')
    or (v_refund.status='processing' and p_new_status in ('succeeded','failed'))
    or (v_refund.status='failed' and p_new_status='processing')
  ) then
    raise exception 'invalid_refund_state_transition' using errcode='P0001';
  end if;

  update private.refunds
  set status=p_new_status,
      approved_by=case when p_new_status='approved' then p_actor_user_id else approved_by end,
      gateway_refund_id=coalesce(p_gateway_refund_id,gateway_refund_id),
      processed_at=case when p_new_status in ('succeeded','failed','rejected') then now() else processed_at end,
      updated_at=now()
  where id=p_refund_id;

  if p_new_status='succeeded' then
    update private.payment_transactions
      set status='refunded',updated_at=now()
      where id=v_refund.payment_transaction_id;
    update public.orders
      set payment_status='refunded',
          status=case when status='collected' then status else 'refunded'::public.order_status end
      where id=v_refund.order_id;
  elsif p_new_status in ('rejected','failed') then
    update public.orders
      set payment_status='captured',
          status=case when status='refund_pending' then 'confirmed'::public.order_status else status end
      where id=v_refund.order_id;
  end if;

  insert into private.refund_events(
    refund_id,from_status,to_status,actor_user_id,actor_type,reason,gateway_reference
  ) values (
    p_refund_id,v_refund.status,p_new_status,p_actor_user_id,p_actor_type,p_reason,p_gateway_refund_id
  );

  insert into private.audit_logs(
    actor_user_id,actor_type,action,entity_type,entity_id,after_data
  ) values (
    p_actor_user_id,p_actor_type,'refund_status_changed','refund',p_refund_id,
    jsonb_build_object('from',v_refund.status,'to',p_new_status,'reason',p_reason)
  );
end;
$function$;

CREATE OR REPLACE FUNCTION private.upsert_store_hours(p_store_id uuid, p_hours jsonb)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_item jsonb;
  v_count integer := 0;
  v_weekday integer;
  v_closed boolean;
  v_open time;
  v_close time;
begin
  if auth.uid() is null then raise exception 'authentication_required' using errcode='28000'; end if;
  if not private.can_manage_store(
    p_store_id,array['store_manager']::public.merchant_member_role[]
  ) then raise exception 'store_access_denied' using errcode='42501'; end if;
  if jsonb_typeof(p_hours)<>'array' or jsonb_array_length(p_hours)<1 or jsonb_array_length(p_hours)>7 then
    raise exception 'hours_must_be_array_of_1_to_7_items' using errcode='22023';
  end if;

  for v_item in select value from jsonb_array_elements(p_hours)
  loop
    v_weekday := (v_item->>'weekday')::integer;
    v_closed := coalesce((v_item->>'is_closed')::boolean,false);
    v_open := nullif(v_item->>'opens_at','')::time;
    v_close := nullif(v_item->>'closes_at','')::time;

    if v_weekday<0 or v_weekday>6 then raise exception 'invalid_weekday' using errcode='22023'; end if;
    if v_closed and (v_open is not null or v_close is not null) then
      raise exception 'closed_day_must_not_have_opening_times' using errcode='22023';
    end if;
    if not v_closed and (v_open is null or v_close is null or v_open=v_close) then
      raise exception 'opening_and_closing_times_required' using errcode='22023';
    end if;

    insert into public.store_hours(store_id,weekday,opens_at,closes_at,is_closed)
    values (p_store_id,v_weekday,v_open,v_close,v_closed)
    on conflict (store_id,weekday) do update
      set opens_at=excluded.opens_at,
          closes_at=excluded.closes_at,
          is_closed=excluded.is_closed;
    v_count := v_count+1;
  end loop;
  return v_count;
end;
$function$;

CREATE OR REPLACE FUNCTION private.verify_pickup_token(p_store_id uuid, p_pickup_token text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
  v_token private.pickup_tokens%rowtype;
  v_order public.orders%rowtype;
  v_hash text;
begin
  if auth.uid() is null then raise exception 'authentication_required' using errcode = '28000'; end if;
  if p_pickup_token is null or length(p_pickup_token) < 32 then
    raise exception 'invalid_pickup_token' using errcode = '22023';
  end if;
  if not private.can_manage_store(
    p_store_id,array['store_manager','pickup_operator']::public.merchant_member_role[]
  ) then raise exception 'pickup_access_denied' using errcode = '42501'; end if;

  v_hash := encode(extensions.digest(p_pickup_token,'sha256'),'hex');
  select * into v_token from private.pickup_tokens where token_hash = v_hash for update;
  if not found or v_token.used_at is not null or v_token.invalidated_at is not null or v_token.expires_at <= now() then
    raise exception 'pickup_token_invalid_or_used' using errcode = 'P0001';
  end if;

  select * into v_order from public.orders where id = v_token.order_id for update;
  if not found or v_order.store_id <> p_store_id
    or v_order.status not in ('confirmed','ready_for_pickup')
    or v_order.payment_status <> 'captured' then
    raise exception 'order_not_collectable' using errcode = 'P0001';
  end if;
  if now() < v_order.pickup_starts_at - interval '15 minutes'
    or now() > v_order.pickup_ends_at + interval '30 minutes' then
    raise exception 'outside_pickup_window' using errcode = 'P0001';
  end if;

  update private.pickup_tokens set used_at = now() where id = v_token.id;
  update public.orders set status = 'collected', collected_at = now() where id = v_order.id;

  insert into public.order_status_events(order_id,from_status,to_status,actor_user_id,actor_type,reason)
  values (v_order.id,v_order.status,'collected',auth.uid(),'merchant','pickup_token_verified');

  insert into private.pickup_events(order_id,store_id,verified_by,verification_method,result,reason)
  values (v_order.id,p_store_id,auth.uid(),'qr','accepted','valid_one_time_token');

  return jsonb_build_object('order_id',v_order.id,'order_number',v_order.order_number,
    'status','collected','collected_at',now());
end;
$function$;

CREATE OR REPLACE FUNCTION public.apply_merchant_application(p_legal_name text, p_display_name text, p_business_type merchant_business_type, p_business_email text DEFAULT NULL::text, p_business_phone text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.apply_merchant_application($1,$2,$3,$4,$5); $function$;

CREATE OR REPLACE FUNCTION public.backend_attach_gateway_order(p_payment_transaction_id uuid, p_gateway_order_id text)
 RETURNS void
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.attach_gateway_order($1,$2); $function$;

CREATE OR REPLACE FUNCTION public.backend_confirm_payment_capture(p_payment_transaction_id uuid, p_gateway_payment_id text, p_amount numeric, p_signature_verified boolean)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.confirm_payment_capture($1,$2,$3,$4); $function$;

CREATE OR REPLACE FUNCTION public.backend_mark_payment_failed(p_payment_transaction_id uuid, p_failure_code text, p_failure_description text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.mark_payment_failed($1,$2,$3); $function$;

CREATE OR REPLACE FUNCTION public.backend_post_ledger_transaction(p_reference_type text, p_reference_id uuid, p_description text, p_currency character, p_entries jsonb)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.post_ledger_transaction($1,$2,$3,$4,$5); $function$;

CREATE OR REPLACE FUNCTION public.backend_record_payment_webhook_event(p_gateway text, p_gateway_event_id text, p_event_type text, p_payload jsonb, p_signature_verified boolean)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.record_payment_webhook_event($1,$2,$3,$4,$5); $function$;

CREATE OR REPLACE FUNCTION public.backend_release_expired_reservations(p_limit integer DEFAULT 100)
 RETURNS integer
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.release_expired_inventory_reservations($1); $function$;

CREATE OR REPLACE FUNCTION public.backend_reverse_ledger_transaction(p_original_transaction_id uuid, p_reason text, p_reversal_reference_id uuid)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.reverse_ledger_transaction($1,$2,$3); $function$;

CREATE OR REPLACE FUNCTION public.backend_review_merchant(p_merchant_id uuid, p_new_status merchant_status, p_verification_status verification_status, p_review_notes text, p_reviewer_id uuid)
 RETURNS void
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.review_merchant_application($1,$2,$3,$4,$5); $function$;

CREATE OR REPLACE FUNCTION public.backend_review_store(p_store_id uuid, p_activate boolean, p_reviewer_id uuid, p_reason text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.review_store_activation($1,$2,$3,$4); $function$;

CREATE OR REPLACE FUNCTION public.backend_update_refund_status(p_refund_id uuid, p_new_status refund_status, p_actor_user_id uuid, p_actor_type text, p_reason text DEFAULT NULL::text, p_gateway_refund_id text DEFAULT NULL::text)
 RETURNS void
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.update_refund_status($1,$2,$3,$4,$5,$6); $function$;

CREATE OR REPLACE FUNCTION public.begin_payment_checkout(p_order_id uuid, p_idempotency_key text)
 RETURNS jsonb
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.begin_payment_checkout($1,$2); $function$;

CREATE OR REPLACE FUNCTION public.create_merchant_store(p_merchant_id uuid, p_name text, p_slug text, p_address_line_1 text, p_address_line_2 text, p_locality text, p_city text, p_state text, p_pincode text, p_latitude double precision, p_longitude double precision, p_contact_phone text DEFAULT NULL::text, p_pickup_instructions text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.create_merchant_store($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13); $function$;

CREATE OR REPLACE FUNCTION public.create_order_reservation(p_store_id uuid, p_items jsonb, p_idempotency_key text, p_customer_note text DEFAULT NULL::text)
 RETURNS jsonb
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.create_order_reservation($1,$2,$3,$4); $function$;

CREATE OR REPLACE FUNCTION public.issue_pickup_token(p_order_id uuid)
 RETURNS jsonb
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.issue_pickup_token($1); $function$;

CREATE OR REPLACE FUNCTION public.request_refund(p_order_id uuid, p_reason_code text, p_description text DEFAULT NULL::text)
 RETURNS uuid
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.request_order_refund($1,$2,$3); $function$;

CREATE OR REPLACE FUNCTION public.set_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
begin
  new.updated_at = now();
  return new;
end;
$function$;

CREATE OR REPLACE FUNCTION public.upsert_store_hours(p_store_id uuid, p_hours jsonb)
 RETURNS integer
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.upsert_store_hours($1,$2); $function$;

CREATE OR REPLACE FUNCTION public.verify_pickup_token(p_store_id uuid, p_pickup_token text)
 RETURNS jsonb
 LANGUAGE sql
 SET search_path TO ''
AS $function$ select private.verify_pickup_token($1,$2); $function$;

CREATE TRIGGER ledger_entries_immutable BEFORE DELETE OR UPDATE ON private.ledger_entries FOR EACH ROW EXECUTE FUNCTION private.prevent_posted_ledger_entry_mutation();
CREATE TRIGGER ledger_transactions_immutable BEFORE DELETE OR UPDATE ON private.ledger_transactions FOR EACH ROW EXECUTE FUNCTION private.prevent_posted_ledger_transaction_mutation();
CREATE TRIGGER merchant_payout_accounts_set_updated_at BEFORE UPDATE ON private.merchant_payout_accounts FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER food_safety_incidents_set_updated_at BEFORE UPDATE ON public.food_safety_incidents FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER listing_templates_set_updated_at BEFORE UPDATE ON public.listing_templates FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER listings_set_updated_at BEFORE UPDATE ON public.listings FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER merchant_memberships_set_updated_at BEFORE UPDATE ON public.merchant_memberships FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER merchants_set_updated_at BEFORE UPDATE ON public.merchants FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER profiles_set_updated_at BEFORE UPDATE ON public.profiles FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER reviews_set_updated_at BEFORE UPDATE ON public.reviews FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER stores_set_updated_at BEFORE UPDATE ON public.stores FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER support_tickets_set_updated_at BEFORE UPDATE ON public.support_tickets FOR EACH ROW EXECUTE FUNCTION set_updated_at();
