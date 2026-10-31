// SaveBite — TypeScript database types (generated, not hand-written)
// Generated 2026-10-31 from the live Supabase project surplus-food-marketplace
// (ref zehnhqcfawagxbactvne) by introspecting information_schema / pg_catalog.
// This file covers the public schema only, matching what Supabase's PostgREST
// API exposes. The private schema (payments, ledger, pickup tokens, etc.) is
// deliberately NOT typed here: it is service-role-only and must only be
// reached from FastAPI, never from Expo / Next.js browser code.
// Money: database columns are NUMERIC; these types use `number` following
// supabase-js conventions. INR arithmetic in FastAPI must still use decimal,
// never binary floating point, per the project rules.
// Regenerate after any approved schema change; do not hand-edit types to
// match code — change the schema (with approval) and regenerate.
export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  public: {
    Tables: {
      categories: {
        Row: {
        id: string
        parent_id: string | null
        name: string
        slug: string
        display_order: number
        is_active: boolean
        created_at: string
        }
        Insert: {
        id?: string
        parent_id?: string | null
        name: string
        slug: string
        display_order?: number
        is_active?: boolean
        created_at?: string
        }
        Update: {
        id?: string
        parent_id?: string | null
        name?: string
        slug?: string
        display_order?: number
        is_active?: boolean
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "categories_parent_id_fkey"
            columns: ["parent_id"]
            isOneToOne: false
            referencedRelation: "categories"
            referencedColumns: ["id"]
          },
        ]
      }
      food_safety_evidence: {
        Row: {
        id: string
        incident_id: string
        uploaded_by: string
        storage_path: string
        media_type: string | null
        created_at: string
        }
        Insert: {
        id?: string
        incident_id: string
        uploaded_by: string
        storage_path: string
        media_type?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        incident_id?: string
        uploaded_by?: string
        storage_path?: string
        media_type?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "food_safety_evidence_incident_id_fkey"
            columns: ["incident_id"]
            isOneToOne: false
            referencedRelation: "food_safety_incidents"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_safety_evidence_uploaded_by_fkey"
            columns: ["uploaded_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      food_safety_incidents: {
        Row: {
        id: string
        order_id: string | null
        customer_id: string | null
        merchant_id: string
        store_id: string
        listing_id: string | null
        incident_type: string
        description: string
        priority: string
        status: Database["public"]["Enums"]["incident_status"]
        assigned_to: string | null
        immediate_action: string | null
        resolution: string | null
        reported_at: string
        resolved_at: string | null
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        order_id?: string | null
        customer_id?: string | null
        merchant_id: string
        store_id: string
        listing_id?: string | null
        incident_type: string
        description: string
        priority?: string
        status?: Database["public"]["Enums"]["incident_status"]
        assigned_to?: string | null
        immediate_action?: string | null
        resolution?: string | null
        reported_at?: string
        resolved_at?: string | null
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        order_id?: string | null
        customer_id?: string | null
        merchant_id?: string
        store_id?: string
        listing_id?: string | null
        incident_type?: string
        description?: string
        priority?: string
        status?: Database["public"]["Enums"]["incident_status"]
        assigned_to?: string | null
        immediate_action?: string | null
        resolution?: string | null
        reported_at?: string
        resolved_at?: string | null
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "food_safety_incidents_assigned_to_fkey"
            columns: ["assigned_to"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_safety_incidents_customer_id_fkey"
            columns: ["customer_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_safety_incidents_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "listings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_safety_incidents_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_safety_incidents_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "food_safety_incidents_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      inventory_events: {
        Row: {
        id: string
        listing_id: string
        order_id: string | null
        reservation_id: string | null
        event_type: string
        quantity_delta: number
        actor_user_id: string | null
        reason: string | null
        created_at: string
        }
        Insert: {
        id?: string
        listing_id: string
        order_id?: string | null
        reservation_id?: string | null
        event_type: string
        quantity_delta: number
        actor_user_id?: string | null
        reason?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        listing_id?: string
        order_id?: string | null
        reservation_id?: string | null
        event_type?: string
        quantity_delta?: number
        actor_user_id?: string | null
        reason?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "inventory_events_actor_user_id_fkey"
            columns: ["actor_user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "inventory_events_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "listings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "inventory_events_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "inventory_events_reservation_id_fkey"
            columns: ["reservation_id"]
            isOneToOne: false
            referencedRelation: "inventory_reservations"
            referencedColumns: ["id"]
          },
        ]
      }
      inventory_reservations: {
        Row: {
        id: string
        order_id: string
        order_item_id: string
        listing_id: string
        quantity: number
        status: Database["public"]["Enums"]["reservation_status"]
        expires_at: string
        consumed_at: string | null
        released_at: string | null
        created_at: string
        }
        Insert: {
        id?: string
        order_id: string
        order_item_id: string
        listing_id: string
        quantity: number
        status?: Database["public"]["Enums"]["reservation_status"]
        expires_at: string
        consumed_at?: string | null
        released_at?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        order_id?: string
        order_item_id?: string
        listing_id?: string
        quantity?: number
        status?: Database["public"]["Enums"]["reservation_status"]
        expires_at?: string
        consumed_at?: string | null
        released_at?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "inventory_reservations_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "listings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "inventory_reservations_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "inventory_reservations_order_item_id_fkey"
            columns: ["order_item_id"]
            isOneToOne: false
            referencedRelation: "order_items"
            referencedColumns: ["id"]
          },
        ]
      }
      listing_images: {
        Row: {
        id: string
        listing_id: string
        storage_path: string
        alt_text: string | null
        display_order: number
        created_at: string
        }
        Insert: {
        id?: string
        listing_id: string
        storage_path: string
        alt_text?: string | null
        display_order?: number
        created_at?: string
        }
        Update: {
        id?: string
        listing_id?: string
        storage_path?: string
        alt_text?: string | null
        display_order?: number
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "listing_images_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "listings"
            referencedColumns: ["id"]
          },
        ]
      }
      listing_templates: {
        Row: {
        id: string
        store_id: string
        listing_type: Database["public"]["Enums"]["listing_type"]
        category_id: string | null
        title: string
        description: string | null
        reference_value: number
        default_selling_price: number
        contents_description: string | null
        allergen_codes: string[]
        dietary_classification: Database["public"]["Enums"]["dietary_classification"]
        storage_instructions: string | null
        is_active: boolean
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        store_id: string
        listing_type: Database["public"]["Enums"]["listing_type"]
        category_id?: string | null
        title: string
        description?: string | null
        reference_value: number
        default_selling_price: number
        contents_description?: string | null
        allergen_codes?: string[]
        dietary_classification?: Database["public"]["Enums"]["dietary_classification"]
        storage_instructions?: string | null
        is_active?: boolean
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        store_id?: string
        listing_type?: Database["public"]["Enums"]["listing_type"]
        category_id?: string | null
        title?: string
        description?: string | null
        reference_value?: number
        default_selling_price?: number
        contents_description?: string | null
        allergen_codes?: string[]
        dietary_classification?: Database["public"]["Enums"]["dietary_classification"]
        storage_instructions?: string | null
        is_active?: boolean
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "listing_templates_category_id_fkey"
            columns: ["category_id"]
            isOneToOne: false
            referencedRelation: "categories"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "listing_templates_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      listings: {
        Row: {
        id: string
        store_id: string
        template_id: string | null
        listing_type: Database["public"]["Enums"]["listing_type"]
        category_id: string | null
        title: string
        description: string | null
        contents_description: string | null
        reference_value: number
        selling_price: number
        currency: string
        total_quantity: number
        reserved_quantity: number
        sold_quantity: number
        available_quantity: number
        sale_starts_at: string
        sale_ends_at: string
        pickup_starts_at: string
        pickup_ends_at: string
        prepared_at: string | null
        best_before_at: string | null
        allergen_codes: string[]
        dietary_classification: Database["public"]["Enums"]["dietary_classification"]
        storage_instructions: string | null
        food_safety_notes: string | null
        status: Database["public"]["Enums"]["listing_status"]
        published_at: string | null
        created_by: string
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        store_id: string
        template_id?: string | null
        listing_type: Database["public"]["Enums"]["listing_type"]
        category_id?: string | null
        title: string
        description?: string | null
        contents_description?: string | null
        reference_value: number
        selling_price: number
        currency?: string
        total_quantity: number
        reserved_quantity?: number
        sold_quantity?: number
        sale_starts_at?: string
        sale_ends_at: string
        pickup_starts_at: string
        pickup_ends_at: string
        prepared_at?: string | null
        best_before_at?: string | null
        allergen_codes?: string[]
        dietary_classification?: Database["public"]["Enums"]["dietary_classification"]
        storage_instructions?: string | null
        food_safety_notes?: string | null
        status?: Database["public"]["Enums"]["listing_status"]
        published_at?: string | null
        created_by: string
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        store_id?: string
        template_id?: string | null
        listing_type?: Database["public"]["Enums"]["listing_type"]
        category_id?: string | null
        title?: string
        description?: string | null
        contents_description?: string | null
        reference_value?: number
        selling_price?: number
        currency?: string
        total_quantity?: number
        reserved_quantity?: number
        sold_quantity?: number
        sale_starts_at?: string
        sale_ends_at?: string
        pickup_starts_at?: string
        pickup_ends_at?: string
        prepared_at?: string | null
        best_before_at?: string | null
        allergen_codes?: string[]
        dietary_classification?: Database["public"]["Enums"]["dietary_classification"]
        storage_instructions?: string | null
        food_safety_notes?: string | null
        status?: Database["public"]["Enums"]["listing_status"]
        published_at?: string | null
        created_by?: string
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "listings_category_id_fkey"
            columns: ["category_id"]
            isOneToOne: false
            referencedRelation: "categories"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "listings_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "listings_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "listings_template_id_fkey"
            columns: ["template_id"]
            isOneToOne: false
            referencedRelation: "listing_templates"
            referencedColumns: ["id"]
          },
        ]
      }
      merchant_documents: {
        Row: {
        id: string
        merchant_id: string
        store_id: string | null
        document_type: string
        storage_path: string
        document_reference: string | null
        last_four: string | null
        valid_from: string | null
        valid_until: string | null
        verification_status: Database["public"]["Enums"]["verification_status"]
        review_notes: string | null
        reviewed_by: string | null
        reviewed_at: string | null
        created_at: string
        }
        Insert: {
        id?: string
        merchant_id: string
        store_id?: string | null
        document_type: string
        storage_path: string
        document_reference?: string | null
        last_four?: string | null
        valid_from?: string | null
        valid_until?: string | null
        verification_status?: Database["public"]["Enums"]["verification_status"]
        review_notes?: string | null
        reviewed_by?: string | null
        reviewed_at?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        merchant_id?: string
        store_id?: string | null
        document_type?: string
        storage_path?: string
        document_reference?: string | null
        last_four?: string | null
        valid_from?: string | null
        valid_until?: string | null
        verification_status?: Database["public"]["Enums"]["verification_status"]
        review_notes?: string | null
        reviewed_by?: string | null
        reviewed_at?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "merchant_documents_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "merchant_documents_reviewed_by_fkey"
            columns: ["reviewed_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "merchant_documents_store_fk"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      merchant_memberships: {
        Row: {
        id: string
        merchant_id: string
        user_id: string
        role: Database["public"]["Enums"]["merchant_member_role"]
        is_active: boolean
        invited_by: string | null
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        merchant_id: string
        user_id: string
        role: Database["public"]["Enums"]["merchant_member_role"]
        is_active?: boolean
        invited_by?: string | null
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        merchant_id?: string
        user_id?: string
        role?: Database["public"]["Enums"]["merchant_member_role"]
        is_active?: boolean
        invited_by?: string | null
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "merchant_memberships_invited_by_fkey"
            columns: ["invited_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "merchant_memberships_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "merchant_memberships_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      merchants: {
        Row: {
        id: string
        legal_name: string
        display_name: string
        business_type: Database["public"]["Enums"]["merchant_business_type"]
        business_email: string | null
        business_phone: string | null
        status: Database["public"]["Enums"]["merchant_status"]
        verification_status: Database["public"]["Enums"]["verification_status"]
        onboarding_notes: string | null
        created_by: string
        approved_at: string | null
        approved_by: string | null
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        legal_name: string
        display_name: string
        business_type: Database["public"]["Enums"]["merchant_business_type"]
        business_email?: string | null
        business_phone?: string | null
        status?: Database["public"]["Enums"]["merchant_status"]
        verification_status?: Database["public"]["Enums"]["verification_status"]
        onboarding_notes?: string | null
        created_by: string
        approved_at?: string | null
        approved_by?: string | null
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        legal_name?: string
        display_name?: string
        business_type?: Database["public"]["Enums"]["merchant_business_type"]
        business_email?: string | null
        business_phone?: string | null
        status?: Database["public"]["Enums"]["merchant_status"]
        verification_status?: Database["public"]["Enums"]["verification_status"]
        onboarding_notes?: string | null
        created_by?: string
        approved_at?: string | null
        approved_by?: string | null
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "merchants_approved_by_fkey"
            columns: ["approved_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "merchants_created_by_fkey"
            columns: ["created_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      notifications: {
        Row: {
        id: string
        user_id: string
        notification_type: string
        title: string
        body: string
        reference_type: string | null
        reference_id: string | null
        read_at: string | null
        created_at: string
        }
        Insert: {
        id?: string
        user_id: string
        notification_type: string
        title: string
        body: string
        reference_type?: string | null
        reference_id?: string | null
        read_at?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        user_id?: string
        notification_type?: string
        title?: string
        body?: string
        reference_type?: string | null
        reference_id?: string | null
        read_at?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "notifications_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      order_items: {
        Row: {
        id: string
        order_id: string
        listing_id: string
        listing_type: Database["public"]["Enums"]["listing_type"]
        listing_title_snapshot: string
        listing_description_snapshot: string | null
        allergen_codes_snapshot: string[]
        dietary_classification_snapshot: Database["public"]["Enums"]["dietary_classification"]
        quantity: number
        unit_price: number
        reference_value_snapshot: number
        line_total: number
        created_at: string
        }
        Insert: {
        id?: string
        order_id: string
        listing_id: string
        listing_type: Database["public"]["Enums"]["listing_type"]
        listing_title_snapshot: string
        listing_description_snapshot?: string | null
        allergen_codes_snapshot?: string[]
        dietary_classification_snapshot?: Database["public"]["Enums"]["dietary_classification"]
        quantity: number
        unit_price: number
        reference_value_snapshot: number
        line_total: number
        created_at?: string
        }
        Update: {
        id?: string
        order_id?: string
        listing_id?: string
        listing_type?: Database["public"]["Enums"]["listing_type"]
        listing_title_snapshot?: string
        listing_description_snapshot?: string | null
        allergen_codes_snapshot?: string[]
        dietary_classification_snapshot?: Database["public"]["Enums"]["dietary_classification"]
        quantity?: number
        unit_price?: number
        reference_value_snapshot?: number
        line_total?: number
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "order_items_listing_id_fkey"
            columns: ["listing_id"]
            isOneToOne: false
            referencedRelation: "listings"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_items_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
        ]
      }
      order_status_events: {
        Row: {
        id: string
        order_id: string
        from_status: Database["public"]["Enums"]["order_status"] | null
        to_status: Database["public"]["Enums"]["order_status"]
        actor_user_id: string | null
        actor_type: string
        reason: string | null
        created_at: string
        }
        Insert: {
        id?: string
        order_id: string
        from_status?: Database["public"]["Enums"]["order_status"] | null
        to_status: Database["public"]["Enums"]["order_status"]
        actor_user_id?: string | null
        actor_type: string
        reason?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        order_id?: string
        from_status?: Database["public"]["Enums"]["order_status"] | null
        to_status?: Database["public"]["Enums"]["order_status"]
        actor_user_id?: string | null
        actor_type?: string
        reason?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "order_status_events_actor_user_id_fkey"
            columns: ["actor_user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "order_status_events_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
        ]
      }
      orders: {
        Row: {
        id: string
        order_number: string
        customer_id: string
        merchant_id: string
        store_id: string
        status: Database["public"]["Enums"]["order_status"]
        payment_status: Database["public"]["Enums"]["payment_status"]
        currency: string
        subtotal_amount: number
        discount_amount: number
        platform_fee_amount: number
        tax_amount: number
        total_amount: number
        pickup_starts_at: string
        pickup_ends_at: string
        customer_note: string | null
        cancellation_reason: string | null
        request_idempotency_key: string
        confirmed_at: string | null
        collected_at: string | null
        cancelled_at: string | null
        created_at: string
        updated_at: string
        request_hash: string
        }
        Insert: {
        id?: string
        order_number: string
        customer_id: string
        merchant_id: string
        store_id: string
        status?: Database["public"]["Enums"]["order_status"]
        payment_status?: Database["public"]["Enums"]["payment_status"]
        currency?: string
        subtotal_amount: number
        discount_amount?: number
        platform_fee_amount?: number
        tax_amount?: number
        total_amount: number
        pickup_starts_at: string
        pickup_ends_at: string
        customer_note?: string | null
        cancellation_reason?: string | null
        request_idempotency_key: string
        confirmed_at?: string | null
        collected_at?: string | null
        cancelled_at?: string | null
        created_at?: string
        updated_at?: string
        request_hash: string
        }
        Update: {
        id?: string
        order_number?: string
        customer_id?: string
        merchant_id?: string
        store_id?: string
        status?: Database["public"]["Enums"]["order_status"]
        payment_status?: Database["public"]["Enums"]["payment_status"]
        currency?: string
        subtotal_amount?: number
        discount_amount?: number
        platform_fee_amount?: number
        tax_amount?: number
        total_amount?: number
        pickup_starts_at?: string
        pickup_ends_at?: string
        customer_note?: string | null
        cancellation_reason?: string | null
        request_idempotency_key?: string
        confirmed_at?: string | null
        collected_at?: string | null
        cancelled_at?: string | null
        created_at?: string
        updated_at?: string
        request_hash?: string
        }
        Relationships: [
          {
            foreignKeyName: "orders_customer_id_fkey"
            columns: ["customer_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "orders_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "orders_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      platform_service_areas: {
        Row: {
        id: string
        name: string
        city: string
        state: string
        pincode_prefix: string | null
        boundary: string | null
        is_active: boolean
        created_at: string
        }
        Insert: {
        id?: string
        name: string
        city: string
        state: string
        pincode_prefix?: string | null
        boundary?: string | null
        is_active?: boolean
        created_at?: string
        }
        Update: {
        id?: string
        name?: string
        city?: string
        state?: string
        pincode_prefix?: string | null
        boundary?: string | null
        is_active?: boolean
        created_at?: string
        }
        Relationships: []
      }
      platform_user_roles: {
        Row: {
        id: string
        user_id: string
        role: Database["public"]["Enums"]["platform_role"]
        granted_by: string | null
        granted_at: string
        revoked_at: string | null
        }
        Insert: {
        id?: string
        user_id: string
        role: Database["public"]["Enums"]["platform_role"]
        granted_by?: string | null
        granted_at?: string
        revoked_at?: string | null
        }
        Update: {
        id?: string
        user_id?: string
        role?: Database["public"]["Enums"]["platform_role"]
        granted_by?: string | null
        granted_at?: string
        revoked_at?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "platform_user_roles_granted_by_fkey"
            columns: ["granted_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "platform_user_roles_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
        id: string
        full_name: string | null
        phone_e164: string | null
        avatar_path: string | null
        preferred_language: string
        default_city: string | null
        account_status: string
        created_at: string
        updated_at: string
        }
        Insert: {
        id: string
        full_name?: string | null
        phone_e164?: string | null
        avatar_path?: string | null
        preferred_language?: string
        default_city?: string | null
        account_status?: string
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        full_name?: string | null
        phone_e164?: string | null
        avatar_path?: string | null
        preferred_language?: string
        default_city?: string | null
        account_status?: string
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "profiles_id_fkey"
            columns: ["id"]
            isOneToOne: true
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      reviews: {
        Row: {
        id: string
        order_id: string
        customer_id: string
        store_id: string
        merchant_id: string
        rating: number
        comment: string | null
        moderation_status: string
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        order_id: string
        customer_id: string
        store_id: string
        merchant_id: string
        rating: number
        comment?: string | null
        moderation_status?: string
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        order_id?: string
        customer_id?: string
        store_id?: string
        merchant_id?: string
        rating?: number
        comment?: string | null
        moderation_status?: string
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "reviews_customer_id_fkey"
            columns: ["customer_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "reviews_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "reviews_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: true
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "reviews_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      store_hours: {
        Row: {
        id: string
        store_id: string
        weekday: number
        opens_at: string | null
        closes_at: string | null
        is_closed: boolean
        created_at: string
        }
        Insert: {
        id?: string
        store_id: string
        weekday: number
        opens_at?: string | null
        closes_at?: string | null
        is_closed?: boolean
        created_at?: string
        }
        Update: {
        id?: string
        store_id?: string
        weekday?: number
        opens_at?: string | null
        closes_at?: string | null
        is_closed?: boolean
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "store_hours_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      store_staff_memberships: {
        Row: {
        id: string
        store_id: string
        user_id: string
        role: Database["public"]["Enums"]["merchant_member_role"]
        is_active: boolean
        granted_by: string | null
        created_at: string
        }
        Insert: {
        id?: string
        store_id: string
        user_id: string
        role: Database["public"]["Enums"]["merchant_member_role"]
        is_active?: boolean
        granted_by?: string | null
        created_at?: string
        }
        Update: {
        id?: string
        store_id?: string
        user_id?: string
        role?: Database["public"]["Enums"]["merchant_member_role"]
        is_active?: boolean
        granted_by?: string | null
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "store_staff_memberships_granted_by_fkey"
            columns: ["granted_by"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "store_staff_memberships_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "store_staff_memberships_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
      stores: {
        Row: {
        id: string
        merchant_id: string
        name: string
        slug: string
        address_line_1: string
        address_line_2: string | null
        locality: string | null
        city: string
        state: string
        pincode: string
        country_code: string
        location: string | null
        contact_phone: string | null
        pickup_instructions: string | null
        timezone: string
        status: Database["public"]["Enums"]["store_status"]
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        merchant_id: string
        name: string
        slug: string
        address_line_1: string
        address_line_2?: string | null
        locality?: string | null
        city: string
        state: string
        pincode: string
        country_code?: string
        location?: string | null
        contact_phone?: string | null
        pickup_instructions?: string | null
        timezone?: string
        status?: Database["public"]["Enums"]["store_status"]
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        merchant_id?: string
        name?: string
        slug?: string
        address_line_1?: string
        address_line_2?: string | null
        locality?: string | null
        city?: string
        state?: string
        pincode?: string
        country_code?: string
        location?: string | null
        contact_phone?: string | null
        pickup_instructions?: string | null
        timezone?: string
        status?: Database["public"]["Enums"]["store_status"]
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "stores_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
        ]
      }
      support_messages: {
        Row: {
        id: string
        ticket_id: string
        sender_user_id: string | null
        sender_type: string
        message: string
        is_internal: boolean
        created_at: string
        }
        Insert: {
        id?: string
        ticket_id: string
        sender_user_id?: string | null
        sender_type: string
        message: string
        is_internal?: boolean
        created_at?: string
        }
        Update: {
        id?: string
        ticket_id?: string
        sender_user_id?: string | null
        sender_type?: string
        message?: string
        is_internal?: boolean
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "support_messages_sender_user_id_fkey"
            columns: ["sender_user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "support_messages_ticket_id_fkey"
            columns: ["ticket_id"]
            isOneToOne: false
            referencedRelation: "support_tickets"
            referencedColumns: ["id"]
          },
        ]
      }
      support_tickets: {
        Row: {
        id: string
        customer_id: string
        order_id: string | null
        merchant_id: string | null
        store_id: string | null
        category: string
        subject: string
        description: string
        status: Database["public"]["Enums"]["support_ticket_status"]
        priority: string
        assigned_to: string | null
        resolved_at: string | null
        created_at: string
        updated_at: string
        }
        Insert: {
        id?: string
        customer_id: string
        order_id?: string | null
        merchant_id?: string | null
        store_id?: string | null
        category: string
        subject: string
        description: string
        status?: Database["public"]["Enums"]["support_ticket_status"]
        priority?: string
        assigned_to?: string | null
        resolved_at?: string | null
        created_at?: string
        updated_at?: string
        }
        Update: {
        id?: string
        customer_id?: string
        order_id?: string | null
        merchant_id?: string | null
        store_id?: string | null
        category?: string
        subject?: string
        description?: string
        status?: Database["public"]["Enums"]["support_ticket_status"]
        priority?: string
        assigned_to?: string | null
        resolved_at?: string | null
        created_at?: string
        updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "support_tickets_assigned_to_fkey"
            columns: ["assigned_to"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "support_tickets_customer_id_fkey"
            columns: ["customer_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "support_tickets_merchant_id_fkey"
            columns: ["merchant_id"]
            isOneToOne: false
            referencedRelation: "merchants"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "support_tickets_order_id_fkey"
            columns: ["order_id"]
            isOneToOne: false
            referencedRelation: "orders"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "support_tickets_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
        ]
      }
      user_favourites: {
        Row: {
        user_id: string
        store_id: string
        created_at: string
        }
        Insert: {
        user_id: string
        store_id: string
        created_at?: string
        }
        Update: {
        user_id?: string
        store_id?: string
        created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "user_favourites_store_id_fkey"
            columns: ["store_id"]
            isOneToOne: false
            referencedRelation: "stores"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "user_favourites_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "users"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      apply_merchant_application: {
        Args: {
          p_legal_name: string
          p_display_name: string
          p_business_type: Database["public"]["Enums"]["merchant_business_type"]
          p_business_email?: string
          p_business_phone?: string
        }
        Returns: string
      }
      backend_attach_gateway_order: {
        Args: {
          p_payment_transaction_id: string
          p_gateway_order_id: string
        }
        Returns: undefined
      }
      backend_confirm_payment_capture: {
        Args: {
          p_payment_transaction_id: string
          p_gateway_payment_id: string
          p_amount: number
          p_signature_verified: boolean
        }
        Returns: string
      }
      backend_mark_payment_failed: {
        Args: {
          p_payment_transaction_id: string
          p_failure_code: string
          p_failure_description?: string
        }
        Returns: string
      }
      backend_post_ledger_transaction: {
        Args: {
          p_reference_type: string
          p_reference_id: string
          p_description: string
          p_currency: string
          p_entries: Json
        }
        Returns: string
      }
      backend_record_payment_webhook_event: {
        Args: {
          p_gateway: string
          p_gateway_event_id: string
          p_event_type: string
          p_payload: Json
          p_signature_verified: boolean
        }
        Returns: string
      }
      backend_release_expired_reservations: {
        Args: {
          p_limit?: number
        }
        Returns: number
      }
      backend_reverse_ledger_transaction: {
        Args: {
          p_original_transaction_id: string
          p_reason: string
          p_reversal_reference_id: string
        }
        Returns: string
      }
      backend_review_merchant: {
        Args: {
          p_merchant_id: string
          p_new_status: Database["public"]["Enums"]["merchant_status"]
          p_verification_status: Database["public"]["Enums"]["verification_status"]
          p_review_notes: string
          p_reviewer_id: string
        }
        Returns: undefined
      }
      backend_review_store: {
        Args: {
          p_store_id: string
          p_activate: boolean
          p_reviewer_id: string
          p_reason?: string
        }
        Returns: undefined
      }
      backend_update_refund_status: {
        Args: {
          p_refund_id: string
          p_new_status: Database["public"]["Enums"]["refund_status"]
          p_actor_user_id: string
          p_actor_type: string
          p_reason?: string
          p_gateway_refund_id?: string
        }
        Returns: undefined
      }
      begin_payment_checkout: {
        Args: {
          p_order_id: string
          p_idempotency_key: string
        }
        Returns: Json
      }
      create_merchant_store: {
        Args: {
          p_merchant_id: string
          p_name: string
          p_slug: string
          p_address_line_1: string
          p_address_line_2: string
          p_locality: string
          p_city: string
          p_state: string
          p_pincode: string
          p_latitude: number
          p_longitude: number
          p_contact_phone?: string
          p_pickup_instructions?: string
        }
        Returns: string
      }
      create_order_reservation: {
        Args: {
          p_store_id: string
          p_items: Json
          p_idempotency_key: string
          p_customer_note?: string
        }
        Returns: Json
      }
      issue_pickup_token: {
        Args: {
          p_order_id: string
        }
        Returns: Json
      }
      request_refund: {
        Args: {
          p_order_id: string
          p_reason_code: string
          p_description?: string
        }
        Returns: string
      }
      upsert_store_hours: {
        Args: {
          p_store_id: string
          p_hours: Json
        }
        Returns: number
      }
      verify_pickup_token: {
        Args: {
          p_store_id: string
          p_pickup_token: string
        }
        Returns: Json
      }
    }
    Enums: {
      dietary_classification: "vegetarian" | "non_vegetarian" | "vegan" | "egg" | "unknown"
      incident_status: "reported" | "triaged" | "investigating" | "action_required" | "resolved" | "closed"
      listing_status: "draft" | "scheduled" | "active" | "paused" | "sold_out" | "expired" | "cancelled"
      listing_type: "surprise_bag" | "individual_item"
      merchant_business_type: "restaurant" | "bakery" | "cafe" | "supermarket" | "hotel" | "cloud_kitchen" | "grocery_store" | "food_manufacturer" | "sweet_shop" | "other"
      merchant_member_role: "owner" | "admin" | "store_manager" | "inventory_manager" | "pickup_operator" | "finance_viewer"
      merchant_status: "pending_review" | "additional_information_required" | "approved" | "rejected" | "suspended"
      order_status: "pending_payment" | "confirmed" | "ready_for_pickup" | "collected" | "expired" | "cancelled" | "refund_pending" | "refunded"
      payment_status: "created" | "authorized" | "captured" | "failed" | "refund_pending" | "partially_refunded" | "refunded" | "reconciliation_required"
      platform_role: "support_agent" | "finance_admin" | "compliance_admin" | "operations_admin" | "super_admin"
      refund_status: "requested" | "approved" | "rejected" | "processing" | "succeeded" | "failed"
      reservation_status: "active" | "consumed" | "released" | "expired"
      settlement_status: "pending" | "processing" | "paid" | "failed" | "reversed"
      store_status: "draft" | "active" | "inactive" | "suspended"
      support_ticket_status: "open" | "in_progress" | "waiting_for_customer" | "resolved" | "closed"
      verification_status: "pending" | "under_review" | "verified" | "rejected" | "expired"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

export type Tables<T extends keyof Database['public']['Tables']> = Database['public']['Tables'][T]['Row']
