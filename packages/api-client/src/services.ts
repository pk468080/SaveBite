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
  ListingSummary,
  MarketplaceCategory,
  MarketplaceListing,
  MerchantDashboard,
  MerchantSummary,
  NotificationItem,
  NotificationPreferences,
  OrderDetail,
  OrderSummary,
  Page,
  PublicReview,
  ReservationResponse,
  ReviewResponse,
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
  listMerchantOrders: (params: { store_id?: string; status?: string; page?: number; page_size?: number } = {}) =>
    client.get<Page<OrderSummary>>(`/v1/merchant/orders${query(params)}`),
  getMerchantOrder: (id: string) =>
    client.get<OrderDetail>(`/v1/merchant/orders/${id}`),
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
    client.post("/v1/merchant/pickups/verify", body),
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
export const merchantsService = (client: ApiClient) => ({
  listMerchants: () => client.get<MerchantSummary[]>("/v1/merchants"),
  getMerchant: (id: string) => client.get<MerchantSummary>(`/v1/merchants/${id}`),
  listStores: (merchantId: string) =>
    client.get<StoreSummary[]>(`/v1/merchants/${merchantId}/stores`),
  listStoreListings: (storeId: string) =>
    client.get<ListingSummary[]>(`/v1/stores/${storeId}/listings`),
});

/** Merchant dashboard and analytics (M10). */
export const merchantDashboardService = (client: ApiClient) => ({
  getDashboard: (params: { store_id?: string; from?: string; to?: string } = {}) =>
    client.get<MerchantDashboard>(`/v1/merchant/dashboard${query(params)}`),
});

/** Platform admin operations (M11). */
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
    merchantDashboard: merchantDashboardService(client),
    admin: adminService(client),
    notifications: notificationsService(client),
  };
}

export type SaveBiteServices = ReturnType<typeof createServices>;
