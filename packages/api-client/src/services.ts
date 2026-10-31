/**
 * Typed service modules over the shared ApiClient.
 *
 * Routes are the verified FastAPI routes from backend
 * milestones M2–M12. Each module starts with the
 * methods W1 needs (mostly reads) and is extended by
 * later milestones. No business rules are duplicated
 * here: the backend remains the authority.
 */

import type { ApiClient, RequestOptions } from "./client";
import type {
  AdminDashboard,
  CheckoutResponse,
  CurrentUser,
  InventoryAvailability,
  InventoryDashboard,
  ListingDetail,
  ListingImage,
  ListingSummary,
  MarketplaceCategory,
  MarketplaceListing,
  MerchantApplicationCreate,
  MerchantDashboard,
  MerchantOrderQueueSummary,
  MerchantOrderSummary,
  MerchantSummary,
  NotificationItem,
  NotificationPreferences,
  OrderDetail,
  OrderSummary,
  Page,
  PickupDashboard,
  PickupVerifyResponse,
  PublicReview,
  ReservationResponse,
  ReviewResponse,
  SalesAnalytics,
  StoreComparison,
  StoreCreateBody,
  StoreDetail,
  StoreHoursResponse,
  StoreHoursUpdateResponse,
  StoreRatingSummary,
  StoreSummary,
  VerifyPaymentResponse,
} from "./types";

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** Authentication and user information (M2). */
export const authService = (client: ApiClient) => ({
  me: () => client.get<CurrentUser>("/v1/me"),
});

/** Public marketplace (M5). Guest/anonymous: no session
 * required. Filters are the exact backend parameters:
 * single category_id only (the API does not support
 * multi-category), exact city match on the store, and
 * pincode validated by the backend pattern. No distance
 * sorting exists and none is offered. */
export const marketplaceService = (client: ApiClient) => ({
  listListings: (params: {
    city?: string;
    pincode?: string;
    category_id?: string;
    listing_type?: "surprise_bag" | "individual_item";
    search?: string;
    min_price?: number;
    max_price?: number;
    dietary?: "vegetarian" | "non_vegetarian" | "vegan" | "egg" | "unknown";
    sort?: "newest" | "lowest_price" | "highest_price" | "ending_soon";
    page?: number;
    page_size?: number;
  } = {}, options?: RequestOptions) =>
    client.get<Page<MarketplaceListing>>(
      `/v1/marketplace/listings${query(params)}`,
      options,
    ),
  getListing: (id: string) =>
    client.get<MarketplaceListing>(`/v1/marketplace/listings/${id}`),
  listCategories: () =>
    client.get<MarketplaceCategory[]>("/v1/marketplace/categories"),
});

/** Customer orders (M5, M7). */
/** Orders (M5 reservations, M7 customer orders).
 * Reservation body verified against ReservationCreate:
 * store_id + items[{listing_id, quantity}] (+ optional
 * customer_note). 1–20 unique listings, quantity 1–20
 * each, same-store enforced by the database. The
 * Idempotency-Key header (8–128 chars) is required. */
export const ordersService = (client: ApiClient) => ({
  createReservation: (body: {
    store_id: string;
    items: Array<{ listing_id: string; quantity: number }>;
    customer_note?: string;
  }, idempotencyKey: string) =>
    client.post<ReservationResponse>("/v1/orders/reservations", body, {
      idempotencyKey,
    }),
  listOrders: (params: { status?: string; payment_status?: string; created_from?: string; created_to?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<OrderSummary>>(`/v1/orders${query(params)}`),
  getOrder: (id: string) => client.get<OrderDetail>(`/v1/orders/${id}`),
  listMerchantOrders: (params: {
    store_id?: string;
    status?: string;
    payment_status?: string;
    pickup_from?: string;
    pickup_to?: string;
    search?: string;
    page?: number;
    page_size?: number;
  } = {}) =>
    client.get<Page<MerchantOrderSummary>>(`/v1/merchant/orders${query(params)}`),
  getMerchantOrder: (id: string) =>
    client.get<OrderDetail>(`/v1/merchant/orders/${id}`),
  getMerchantOrderSummary: (params: {
    store_id?: string;
    created_from?: string;
    created_to?: string;
  } = {}) =>
    client.get<MerchantOrderQueueSummary>(
      `/v1/merchant/orders/summary${query(params)}`,
    ),
});

/** Payments (M6). Checkout requires an Idempotency-Key
 * header (8–128 chars); retrying with the SAME key
 * returns the same transaction instead of creating a
 * second Razorpay order. Verification is authenticated
 * and server-side only — the frontend never confirms
 * payment from the checkout callback alone. */
export const paymentsService = (client: ApiClient) => ({
  checkout: (orderId: string, idempotencyKey: string) =>
    client.post<CheckoutResponse>(`/v1/orders/${orderId}/checkout`, {}, {
      idempotencyKey,
    }),
  verifyPayment: (body: {
    razorpay_order_id: string;
    razorpay_payment_id: string;
    razorpay_signature: string;
  }) => client.post<VerifyPaymentResponse>("/v1/payments/verify", body),
});

/** Pickup verification (M8). */
export const pickupService = (client: ApiClient) => ({
  issuePickupToken: (orderId: string) =>
    client.post<{ pickup_token: string; qr_payload: string }>(
      `/v1/orders/${orderId}/pickup-token`,
      {},
    ),
  verifyPickupToken: (body: { store_id: string; pickup_token: string }) =>
    client.post<PickupVerifyResponse>("/v1/merchant/pickups/verify", body),
});

/** Reviews and ratings (M9). */
export const reviewsService = (client: ApiClient) => ({
  createReview: (orderId: string, body: { rating: number; comment?: string }) =>
    client.post<ReviewResponse>(`/v1/orders/${orderId}/review`, body),
  listMyReviews: (params: { rating?: number; moderation_status?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<ReviewResponse>>(`/v1/my/reviews${query(params)}`),
  listStoreReviews: (storeId: string, params: { sort?: "newest" | "highest" | "lowest"; rating?: number; page?: number; page_size?: number } = {}) =>
    client.get<Page<PublicReview> & { store_name: string }>(`/v1/stores/${storeId}/reviews${query(params)}`),
  getStoreRatingSummary: (storeId: string) =>
    client.get<StoreRatingSummary>(`/v1/stores/${storeId}/rating-summary`),
});

/** Merchants, stores, listings, inventory (M3, M4). */
/** Merchants, stores, listings, inventory (M3, M4).
 * Store detail has no dedicated endpoint: detail
 * pages assemble a store from listStores and match
 * by id, so an id outside the caller's memberships
 * simply is not found. */
export const merchantsService = (client: ApiClient) => ({
  listMerchants: () => client.get<MerchantSummary[]>("/v1/merchants"),
  getMerchant: (id: string) => client.get<MerchantSummary>(`/v1/merchants/${id}`),
  submitApplication: (body: MerchantApplicationCreate) =>
    client.post<MerchantSummary>("/v1/merchants/applications", body),
  listStores: (merchantId: string) =>
    client.get<StoreDetail[]>(`/v1/merchants/${merchantId}/stores`),
  createStore: (merchantId: string, body: StoreCreateBody) =>
    client.post<StoreDetail>(`/v1/merchants/${merchantId}/stores`, body),
  getStoreHours: (storeId: string) =>
    client.get<StoreHoursResponse>(`/v1/stores/${storeId}/hours`),
  updateStoreHours: (
    storeId: string,
    hours: Array<{
      weekday: number;
      is_closed: boolean;
      opens_at?: string | null;
      closes_at?: string | null;
    }>,
  ) =>
    client.put<StoreHoursUpdateResponse>(`/v1/stores/${storeId}/hours`, { hours }),
  listCategories: () =>
    client.get<MarketplaceCategory[]>("/v1/categories"),
  listStoreListings: (storeId: string) =>
    client.get<ListingSummary[]>(`/v1/stores/${storeId}/listings`),
});

/** Merchant dashboard and analytics (M10). */
export const merchantDashboardService = (client: ApiClient) => ({
  getDashboard: (params: { store_id?: string; from?: string; to?: string } = {}) =>
    client.get<MerchantDashboard>(`/v1/merchant/dashboard${query(params)}`),
  getSales: (params: {
    store_id?: string;
    from?: string;
    to?: string;
    group_by?: "day" | "week" | "month";
  } = {}) =>
    client.get<SalesAnalytics>(`/v1/merchant/dashboard/sales${query(params)}`),
  getInventory: (params: {
    store_id?: string;
    low_stock_threshold?: number;
  } = {}) =>
    client.get<InventoryDashboard>(
      `/v1/merchant/dashboard/inventory${query(params)}`,
    ),
  getPickups: (params: {
    store_id?: string;
    from?: string;
    to?: string;
    category?: "upcoming" | "in_window" | "completed" | "window_expired";
  } = {}) =>
    client.get<PickupDashboard>(`/v1/merchant/dashboard/pickups${query(params)}`),
  getStoreComparison: (params: { from?: string; to?: string } = {}) =>
    client.get<StoreComparison>(`/v1/merchant/dashboard/stores${query(params)}`),
});

/** Platform admin operations (M11). */
/** Listings: create, read, update, transitions,
 * inventory, images (M4). Listings are always
 * created as draft; status moves only through the
 * transition endpoints. Images are registered only
 * after the file itself is uploaded to the
 * listing-media bucket at <listing_id>/<file>;
 * listing_images has no UPDATE or DELETE policy,
 * so images can never be edited or removed here. */
export const listingsService = (client: ApiClient) => ({
  createListing: (storeId: string, body: Record<string, unknown>) =>
    client.post<ListingDetail>(`/v1/stores/${storeId}/listings`, body),
  getListing: (id: string) =>
    client.get<ListingDetail>(`/v1/listings/${id}`),
  updateListing: (id: string, body: Record<string, unknown>) =>
    client.patch<ListingDetail>(`/v1/listings/${id}`, body),
  publish: (id: string) =>
    client.post<ListingDetail>(`/v1/listings/${id}/publish`, {}),
  pause: (id: string) =>
    client.post<ListingDetail>(`/v1/listings/${id}/pause`, {}),
  resume: (id: string) =>
    client.post<ListingDetail>(`/v1/listings/${id}/resume`, {}),
  cancel: (id: string) =>
    client.post<ListingDetail>(`/v1/listings/${id}/cancel`, {}),
  getInventory: (id: string) =>
    client.get<InventoryAvailability>(`/v1/listings/${id}/inventory`),
  listImages: (id: string) =>
    client.get<ListingImage[]>(`/v1/listings/${id}/images`),
  addImage: (
    id: string,
    body: { storage_path: string; alt_text?: string | null; display_order?: number },
  ) => client.post<ListingImage>(`/v1/listings/${id}/images`, body),
});

export const adminService = (client: ApiClient) => ({
  getDashboard: () => client.get<AdminDashboard>("/v1/admin/dashboard"),
  listMerchants: (params: { status?: string; verification_status?: string; search?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<MerchantSummary>>(`/v1/admin/merchants${query(params)}`),
  reviewMerchant: (id: string, body: { action: "approve" | "reject"; review_notes?: string }) =>
    client.post(`/v1/admin/merchants/${id}/review`, body),
  listStores: (params: { merchant_id?: string; status?: string; city?: string; pincode?: string; search?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<StoreSummary>>(`/v1/admin/stores${query(params)}`),
  reviewStore: (id: string, body: { activate: boolean; reason?: string }) =>
    client.post(`/v1/admin/stores/${id}/review`, body),
  listOrders: (params: { order_number?: string; status?: string; payment_status?: string; store_id?: string; merchant_id?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<OrderSummary>>(`/v1/admin/orders${query(params)}`),
  listPayments: (params: { payment_status?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<OrderSummary>>(`/v1/admin/payments${query(params)}`),
  listRefunds: (params: { page?: number; page_size?: number } = {}) =>
    client.get<Page<OrderSummary>>(`/v1/admin/refunds${query(params)}`),
  listReviews: (params: { store_id?: string; rating?: number; moderation_status?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<ReviewResponse>>(`/v1/admin/reviews${query(params)}`),
  listActivity: (params: { order_number?: string; store_id?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<unknown>>(`/v1/admin/activity${query(params)}`),
});

/** In-app notifications (M12). Reads and read-state only;
 * generation is server-side once the approved delivery
 * RPC exists and is not part of this client. */
export const notificationsService = (client: ApiClient) => ({
  list: (params: { unread_only?: boolean; notification_type?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<NotificationItem>>(`/v1/notifications${query(params)}`),
  unreadCount: () =>
    client.get<{ unread_count: number }>("/v1/notifications/unread-count"),
  get: (id: string) => client.get<NotificationItem>(`/v1/notifications/${id}`),
  markRead: (id: string) =>
    client.post<{ id: string; read_at: string; already_read: boolean }>(
      `/v1/notifications/${id}/read`,
      {},
    ),
  markAllRead: () =>
    client.post<{ updated_count: number }>("/v1/notifications/read-all", {}),
  getPreferences: () =>
    client.get<NotificationPreferences>("/v1/notifications/preferences"),
});

export function createServices(client: ApiClient) {
  return {
    auth: authService(client),
    marketplace: marketplaceService(client),
    orders: ordersService(client),
    payments: paymentsService(client),
    pickup: pickupService(client),
    reviews: reviewsService(client),
    merchants: merchantsService(client),
    listings: listingsService(client),
    merchantDashboard: merchantDashboardService(client),
    admin: adminService(client),
    notifications: notificationsService(client),
  };
}

export type SaveBiteServices = ReturnType<typeof createServices>;
