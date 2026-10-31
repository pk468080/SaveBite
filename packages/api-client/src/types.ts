/**
 * API response types for the SaveBite FastAPI backend.
 *
 * These are API response shapes (from backend Pydantic
 * schemas, milestones M2–M12), NOT database row types.
 * Database row types live in @savebite/types and must
 * never be exposed to browser code. Adjust these types
 * when the backend OpenAPI contract changes; do not
 * invent fields the backend does not return.
 */

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * Verified against backend/app/schemas.py (M5):
 * PublicListingSummary + PublicStoreSummary +
 * PublicListingImage. Images carry a STORAGE PATH in
 * the public listing-media bucket, never a URL — the
 * frontend resolves it (see apps/web lib/marketplace).
 * reference_value is the merchant-declared reference
 * value; a discount is only shown when it exceeds the
 * selling price. No created_by, created_at, or merchant
 * internals are ever returned.
 */
export interface PublicStoreSummary {
  id: string;
  name: string;
  locality?: string | null;
  city: string;
  state: string;
  pincode: string;
  timezone?: string;
}

export interface PublicListingImage {
  storage_path: string;
  alt_text?: string | null;
  display_order?: number;
}

export type ListingTypeValue = "surprise_bag" | "individual_item";
export type DietaryValue =
  | "vegetarian"
  | "non_vegetarian"
  | "vegan"
  | "egg"
  | "unknown";
export type MarketplaceSortValue =
  | "newest"
  | "lowest_price"
  | "highest_price"
  | "ending_soon";

export interface MarketplaceListing {
  id: string;
  store: PublicStoreSummary;
  listing_type: ListingTypeValue;
  category_id?: string | null;
  category_name?: string | null;
  title: string;
  description?: string | null;
  contents_description?: string | null;
  reference_value: string;
  selling_price: string;
  currency: string;
  available_quantity: number;
  dietary_classification: DietaryValue;
  allergen_codes: string[];
  storage_instructions?: string | null;
  sale_starts_at: string;
  sale_ends_at: string;
  pickup_starts_at: string;
  pickup_ends_at: string;
  prepared_at?: string | null;
  best_before_at?: string | null;
  images: PublicListingImage[];
}

export interface MarketplaceCategory {
  id: string;
  parent_id?: string | null;
  name: string;
  slug: string;
  display_order?: number;
  is_active?: boolean;
}

export interface PublicReview {
  id: string;
  rating: number;
  comment?: string | null;
  created_at: string;
}

export interface OrderSummary {
  id: string;
  order_number: string;
  store_id: string;
  store_name?: string | null;
  status: string;
  payment_status: string;
  total_amount: string;
  currency: string;
  pickup_starts_at?: string | null;
  pickup_ends_at?: string | null;
  collected_at?: string | null;
  created_at: string;
}

export interface OrderDetail extends OrderSummary {
  items: Array<{
    title: string;
    quantity: number;
    unit_price: string;
    line_total: string;
  }>;
  events: Array<{
    from_status?: string | null;
    to_status: string;
    actor_type?: string | null;
    reason?: string | null;
    created_at: string;
  }>;
  reservation_expires_at?: string | null;
  pickup_available?: boolean;
}

export interface ReservationResponse {
  order_id: string;
  order_number?: string;
  status: string;
  total_amount?: string;
  reservation_expires_at?: string | null;
  idempotent_replay?: boolean;
}

export interface CheckoutResponse {
  payment_transaction_id?: string;
  razorpay_order_id?: string;
  amount_paise?: number;
  currency?: string;
  key_id?: string;
}

export interface ReviewResponse {
  id: string;
  store_id: string;
  order_id: string;
  rating: number;
  comment?: string | null;
  moderation_status: string;
  created_at: string;
}

/** Verified against backend StoreRatingSummary (M9):
 * aggregates over PUBLIC (visible) reviews only; a store
 * with no public reviews has average_rating null, never
 * a fabricated 5.0. No reviewer names exist in the
 * public contract and none are invented. */
export interface StoreRatingSummary {
  store_id: string;
  store_name: string;
  average_rating: number | null;
  total_reviews: number;
  five_star: number;
  four_star: number;
  three_star: number;
  two_star: number;
  one_star: number;
}

export interface MerchantSummary {
  id: string;
  legal_name: string;
  display_name: string;
  business_type?: string | null;
  status: string;
  verification_status: string;
  created_at: string;
}

export interface StoreSummary {
  id: string;
  merchant_id: string;
  name: string;
  status: string;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  locality?: string | null;
  created_at: string;
}

export interface ListingSummary {
  id: string;
  store_id: string;
  title: string;
  selling_price: string;
  currency: string;
  total_quantity: number;
  reserved_quantity: number;
  sold_quantity: number;
  available_quantity: number;
  status: string;
  sale_starts_at?: string | null;
  sale_ends_at?: string | null;
  created_at: string;
}

export interface MerchantDashboard {
  store_count?: number;
  total_orders?: number;
  captured_order_value?: string;
  [key: string]: unknown;
}

export interface AdminDashboard {
  merchants_total: number;
  merchants_approved: number;
  merchants_pending_review: number;
  stores_total: number;
  stores_active: number;
  listings_total: number;
  listings_published: number;
  orders_total: number;
  orders_collected: number;
  captured_payment_count: number;
  captured_order_value: string;
  failed_payment_count?: number;
  pending_payment_count?: number;
  reconciliation_count?: number;
  refund_pending_count: number;
  visible_reviews_total: number;
  average_visible_rating: number | null;
  recent_orders: OrderSummary[];
}

export interface NotificationItem {
  id: string;
  notification_type: string;
  title: string;
  body: string;
  reference_type?: string | null;
  reference_id?: string | null;
  read_at?: string | null;
  created_at: string;
  is_read: boolean;
}

export interface NotificationPreferences {
  preferences: Record<string, boolean>;
  mandatory_categories: string[];
  persisted: boolean;
}

export interface CurrentUser {
  id: string;
  email?: string | null;
}
