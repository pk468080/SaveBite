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

/**
 * Verified against backend OrderSummary / OrderDetail
 * (M7). Item prices on detail are ORDER-TIME SNAPSHOTS,
 * never live listing prices. Timeline events are real
 * order_status_events rows only. payment.amount_paid is
 * the order total when payment_status is captured,
 * otherwise 0. No customer_id, gateway ids, or internal
 * fields are ever returned.
 */
export type OrderStatusValue =
  | "pending_payment"
  | "confirmed"
  | "ready_for_pickup"
  | "collected"
  | "expired"
  | "cancelled"
  | "refund_pending"
  | "refunded";

export type PaymentStatusValue =
  | "created"
  | "authorized"
  | "captured"
  | "failed"
  | "refund_pending"
  | "partially_refunded"
  | "refunded"
  | "reconciliation_required";

export interface OrderStoreSummary {
  id: string;
  name: string;
  locality?: string | null;
  city: string;
  state: string;
  pincode: string;
}

export interface OrderItemPreview {
  title: string;
  quantity: number;
}

export interface OrderSummary {
  id: string;
  order_number: string;
  status: OrderStatusValue;
  payment_status: PaymentStatusValue;
  total_amount: string;
  currency: string;
  created_at: string;
  updated_at: string;
  store: OrderStoreSummary;
  pickup_starts_at: string;
  pickup_ends_at: string;
  item_count: number;
  items_preview: OrderItemPreview[];
}

export interface OrderItemSnapshot {
  listing_id: string;
  listing_type: ListingTypeValue;
  title: string;
  description?: string | null;
  quantity: number;
  unit_price: string;
  line_total: string;
  reference_value: string;
  dietary_classification: DietaryValue;
  allergen_codes: string[];
  image_path?: string | null;
}

export interface OrderPaymentSummary {
  status: PaymentStatusValue;
  gateway_label?: string | null;
  amount_paid: string;
  paid_at?: string | null;
}

export interface OrderTimelineEvent {
  status: OrderStatusValue;
  label: string;
  occurred_at: string;
  actor_type: string;
}

export interface OrderStoreDetail extends OrderStoreSummary {
  address_line_1: string;
  address_line_2?: string | null;
  contact_phone?: string | null;
  pickup_instructions?: string | null;
}

export interface OrderDetail {
  id: string;
  order_number: string;
  status: OrderStatusValue;
  payment: OrderPaymentSummary;
  subtotal_amount: string;
  discount_amount: string;
  platform_fee_amount: string;
  tax_amount: string;
  total_amount: string;
  currency: string;
  created_at: string;
  updated_at: string;
  confirmed_at?: string | null;
  collected_at?: string | null;
  cancelled_at?: string | null;
  customer_note?: string | null;
  cancellation_reason?: string | null;
  store: OrderStoreDetail;
  pickup_starts_at: string;
  pickup_ends_at: string;
  reservation_expires_at?: string | null;
  pickup_available: boolean;
  items: OrderItemSnapshot[];
  timeline: OrderTimelineEvent[];
}

/**
 * Verified against backend ReservationResponse (M5):
 * a reservation is NOT a paid order. reservation_
 * expires_at is null on an idempotent replay, because
 * the RPC replay response carries no expiry — the
 * frontend must then read the order detail for the
 * authoritative expiry instead of inventing one.
 */
export interface ReservationResponse {
  order_id: string;
  order_number: string;
  status: OrderStatusValue;
  total_amount: string;
  currency: string;
  reservation_expires_at?: string | null;
  pickup_starts_at: string;
  pickup_ends_at: string;
  idempotent_replay: boolean;
}

/**
 * Verified against backend CheckoutResponse (M6):
 * safe fields only. key_id is the PUBLIC key and may
 * go to the browser; no secret ever appears here.
 * The amount comes from the database, never from
 * the request — the frontend must not choose it.
 */
export interface CheckoutResponse {
  order_id: string;
  payment_transaction_id: string;
  key_id: string;
  razorpay_order_id: string;
  amount_paise: number;
  currency: string;
  prefill_email?: string | null;
}

/**
 * Verified against backend VerifyPaymentResponse (M6).
 * verified=true means the signature, provider capture,
 * and confirm RPC all passed — but the ORDER's stored
 * status remains authoritative: the RPC routes amount
 * mismatches and non-live reservations to
 * reconciliation_required instead of capturing, so the
 * frontend must always re-read the order detail after
 * verification before showing success.
 */
export interface VerifyPaymentResponse {
  order_id: string;
  payment_transaction_id: string;
  razorpay_payment_id: string;
  verified: boolean;
  amount_paise: number;
  currency: string;
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
  business_email?: string | null;
  business_phone?: string | null;
  status: string;
  verification_status: string;
  created_at: string;
  updated_at?: string | null;
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
  listing_type?: ListingTypeValue;
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

export type MerchantDashboard = MerchantDashboardOverview;

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

/** Verified against backend MeResponse (M2). Roles
 * come from the backend; the frontend never trusts a
 * role it was handed by the browser. */
export interface CurrentUser {
  id: string;
  email?: string | null;
  platform_roles: string[];
}

/**
 * Merchant portal types (W4). Verified against the
 * FastAPI schemas for M3 (merchants/stores/hours),
 * M4 (listings/images/inventory), M7 (merchant
 * orders), M8 (pickup verification), M9 (reviews)
 * and M10 (merchant dashboard). Money is a string
 * (Decimal on the backend), never a float.
 */

export type MerchantBusinessTypeValue =
  | "restaurant"
  | "bakery"
  | "cafe"
  | "supermarket"
  | "hotel"
  | "cloud_kitchen"
  | "grocery_store"
  | "food_manufacturer"
  | "sweet_shop"
  | "other";

export type MerchantStatusValue =
  | "pending_review"
  | "additional_information_required"
  | "approved"
  | "rejected"
  | "suspended";

export type MerchantVerificationValue =
  | "pending"
  | "under_review"
  | "verified"
  | "rejected"
  | "expired";

export type StoreStatusValue = "draft" | "active" | "inactive" | "suspended";

export type ListingStatusValue =
  | "draft"
  | "scheduled"
  | "active"
  | "paused"
  | "sold_out"
  | "expired"
  | "cancelled";

export interface MerchantApplicationCreate {
  legal_name: string;
  display_name: string;
  business_type: MerchantBusinessTypeValue;
  business_email?: string | null;
  business_phone?: string | null;
}

/** Full store record (StoreResponse). StoreSummary
 * stays the list shape; detail pages use this. */
export interface StoreDetail extends StoreSummary {
  slug: string;
  address_line_1: string;
  address_line_2?: string | null;
  country_code: string;
  contact_phone?: string | null;
  pickup_instructions?: string | null;
  timezone: string;
  updated_at?: string | null;
}

export interface StoreCreateBody {
  name: string;
  slug: string;
  address_line_1: string;
  address_line_2?: string | null;
  locality?: string | null;
  city: string;
  state: string;
  pincode: string;
  latitude?: number | null;
  longitude?: number | null;
  contact_phone?: string | null;
  pickup_instructions?: string | null;
}

/**
 * Store hours. Weekday is the backend integer 0-6.
 * The repository deliberately does NOT state whether
 * 0 is Monday or Sunday, so the UI shows the number
 * and never guesses a day name.
 */
export interface StoreHoursEntry {
  weekday: number;
  is_closed: boolean;
  opens_at?: string | null;
  closes_at?: string | null;
}

export interface StoreHoursResponse {
  store_id: string;
  hours: StoreHoursEntry[];
}

export interface StoreHoursUpdateResponse {
  store_id: string;
  processed: number;
  hours: StoreHoursEntry[];
}

/** Full listing record (ListingResponse). */
export interface ListingDetail {
  id: string;
  store_id: string;
  template_id?: string | null;
  listing_type: ListingTypeValue;
  category_id?: string | null;
  title: string;
  description?: string | null;
  contents_description?: string | null;
  reference_value: string;
  selling_price: string;
  currency: string;
  total_quantity: number;
  reserved_quantity: number;
  sold_quantity: number;
  available_quantity: number;
  sale_starts_at?: string | null;
  sale_ends_at: string;
  pickup_starts_at: string;
  pickup_ends_at: string;
  prepared_at?: string | null;
  best_before_at?: string | null;
  allergen_codes: string[];
  dietary_classification: DietaryValue;
  storage_instructions?: string | null;
  food_safety_notes?: string | null;
  status: ListingStatusValue;
  published_at?: string | null;
  created_by: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ListingCreateBody {
  listing_type: ListingTypeValue;
  category_id?: string | null;
  title: string;
  description?: string | null;
  contents_description?: string | null;
  reference_value: string;
  selling_price: string;
  total_quantity: number;
  sale_starts_at?: string | null;
  sale_ends_at: string;
  pickup_starts_at: string;
  pickup_ends_at: string;
  prepared_at?: string | null;
  best_before_at?: string | null;
  allergen_codes?: string[];
  dietary_classification?: DietaryValue;
  storage_instructions?: string | null;
  food_safety_notes?: string | null;
}

export type ListingUpdateBody = Partial<ListingCreateBody>;

export interface ListingImage {
  id: string;
  listing_id: string;
  storage_path: string;
  alt_text?: string | null;
  display_order: number;
  created_at?: string | null;
}

export interface InventoryAvailability {
  listing_id: string;
  store_id: string;
  status: ListingStatusValue;
  total_quantity: number;
  reserved_quantity: number;
  sold_quantity: number;
  available_quantity: number;
  sale_ends_at: string;
  pickup_ends_at: string;
}

export interface DashboardPeriod {
  from?: string | null;
  to?: string | null;
}

export interface DashboardStoreContext {
  store_id?: string | null;
  store_name?: string | null;
  store_status?: string | null;
  timezone: string;
  /** Null means unknown, never "closed": the
   * weekday convention is unverified, so the
   * backend deliberately returns null. */
  open_now?: boolean | null;
  store_count: number;
}

export interface DashboardOrderMetrics {
  total_orders: number;
  paid_orders: number;
  awaiting_payment_orders: number;
  collected_orders: number;
  cancelled_orders: number;
  expired_orders: number;
  refund_orders: number;
  /** Sum over captured payments only. This is NOT
   * earnings, settlement or payout revenue. */
  captured_order_value: string;
  currency: string;
}

export interface DashboardInventoryMetrics {
  total_listings: number;
  published_listings: number;
  draft_listings: number;
  paused_listings: number;
  sold_out_listings: number;
  total_available_units: number;
  total_reserved_units: number;
  total_sold_units: number;
}

export interface DashboardPickupMetrics {
  upcoming_pickups: number;
  in_window_pickups: number;
  completed_collections: number;
  /** Window closed without collection. Labelled
   * window_expired, never "missed": the database
   * records no no-show event. */
  window_expired_pickups: number;
}

export interface DashboardRatingMetrics {
  average_rating: number | null;
  total_visible_reviews: number;
  five_star: number;
  four_star: number;
  three_star: number;
  two_star: number;
  one_star: number;
}

export interface MerchantDashboardOverview {
  period: DashboardPeriod;
  store: DashboardStoreContext;
  orders: DashboardOrderMetrics;
  inventory: DashboardInventoryMetrics;
  pickups: DashboardPickupMetrics;
  ratings: DashboardRatingMetrics;
}

export interface SalesBucket {
  period_start: string;
  total_orders: number;
  captured_orders: number;
  pending_payment_orders: number;
  failed_payment_orders: number;
  collected_orders: number;
  cancelled_or_expired_orders: number;
  captured_order_value: string;
  currency: string;
}

export interface SalesAnalytics {
  period: DashboardPeriod;
  store: DashboardStoreContext;
  group_by: string;
  reporting_timezone: string;
  buckets: SalesBucket[];
  totals: SalesBucket;
}

export interface InventoryListingSummary {
  listing_id: string;
  title: string;
  status: string;
  available_quantity: number;
  reserved_quantity: number;
  sold_quantity: number;
  sale_ends_at?: string | null;
}

export interface InventoryDashboard {
  period: DashboardPeriod;
  store: DashboardStoreContext;
  summary: DashboardInventoryMetrics;
  /** Only populated when a low_stock_threshold
   * query is given. A reporting filter, not a
   * business definition of low stock. */
  low_stock_listings: InventoryListingSummary[];
}

export interface PickupOrderSummary {
  order_number: string;
  status: string;
  pickup_starts_at: string;
  pickup_ends_at: string;
  category: "upcoming" | "in_window" | "completed" | "window_expired";
  total_quantity: number;
}

export interface PickupDashboard {
  period: DashboardPeriod;
  store: DashboardStoreContext;
  counts: DashboardPickupMetrics;
  orders: PickupOrderSummary[];
}

export interface StoreComparisonRow {
  store_id: string;
  store_name: string;
  store_status: string;
  total_orders: number;
  captured_order_value: string;
  collected_orders: number;
  active_listings: number;
  available_units: number;
  average_rating: number | null;
  review_count: number;
}

export interface StoreComparison {
  period: DashboardPeriod;
  stores: StoreComparisonRow[];
}

export interface MerchantOrderSummary {
  id: string;
  order_number: string;
  status: OrderStatusValue;
  payment_status: PaymentStatusValue;
  total_amount: string;
  currency: string;
  created_at: string;
  store: OrderStoreSummary;
  pickup_starts_at: string;
  pickup_ends_at: string;
  item_count: number;
  items_preview: OrderItemPreview[];
}

export interface MerchantOrderQueueSummary {
  total: number;
  awaiting_payment: number;
  paid: number;
  upcoming_pickups: number;
  completed: number;
  cancelled_or_expired: number;
}

export interface PickupVerifyResponse {
  order_id: string;
  order_number: string;
  store_name: string;
  status: OrderStatusValue;
  collected_at: string;
  items: OrderItemPreview[];
}

/**
 * One-time pickup token, returned ONLY at
 * issuance (M8). The backend stores only the
 * SHA-256 hash, so the plaintext token cannot
 * be retrieved later: a lost token means issuing
 * a fresh one, which invalidates the old unused
 * one. qr_payload is the exact string to render
 * as a QR code ("SB1:<64-hex-token>").
 */
export interface PickupTokenResponse {
  order_id: string;
  order_number: string;
  pickup_token: string;
  qr_payload: string;
  expires_at: string;
  pickup_starts_at: string;
  pickup_ends_at: string;
  store_name: string;
  pickup_instructions?: string | null;
}
