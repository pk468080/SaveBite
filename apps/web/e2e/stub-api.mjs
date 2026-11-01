/**
 * Minimal stub FastAPI + stub Supabase Auth for
 * Playwright e2e (W2, extended in W3).
 *
 * Serves the same response shapes as the real backend
 * for the public marketplace endpoints, plus the W3
 * customer journey: mocked Supabase Auth (password
 * grant + user + refresh), reservations, Razorpay
 * checkout initiation, payment verification, orders,
 * and notifications — all in-memory. It is NOT a
 * backend replacement: it exists only so e2e can run
 * without a live Supabase project or real Razorpay
 * keys. Run: `node e2e/stub-api.mjs` (port 8000).
 */
import { createServer } from "node:http";

const LISTING_ID = "11111111-1111-4111-8111-111111111111";
const STORE_ID = "22222222-2222-4222-8222-222222222222";

const listing = {
  id: LISTING_ID,
  store: {
    id: STORE_ID,
    name: "Sharma Foods",
    locality: "Dwarka Sector 7",
    city: "New Delhi",
    state: "Delhi",
    pincode: "110075",
    timezone: "Asia/Kolkata",
  },
  listing_type: "surprise_bag",
  category_id: "33333333-3333-4333-8333-333333333333",
  category_name: "Bakery",
  title: "Evening Bakery Bag",
  description: "Fresh breads and pastries.",
  contents_description: "A mix of breads and pastries.",
  reference_value: "300.00",
  selling_price: "195.00",
  currency: "INR",
  available_quantity: 5,
  dietary_classification: "vegetarian",
  allergen_codes: ["gluten"],
  storage_instructions: "Keep refrigerated.",
  sale_starts_at: "2026-10-31T10:00:00+00:00",
  sale_ends_at: "2026-10-31T17:00:00+00:00",
  pickup_starts_at: "2026-10-31T18:00:00+00:00",
  pickup_ends_at: "2026-10-31T21:00:00+00:00",
  prepared_at: null,
  best_before_at: null,
  images: [
    {
      storage_path: `${LISTING_ID}/photo.jpg`,
      alt_text: "Bakery bag",
      display_order: 0,
    },
  ],
};

const categories = [
  {
    id: "33333333-3333-4333-8333-333333333333",
    parent_id: null,
    name: "Bakery",
    slug: "bakery",
    display_order: 1,
    is_active: true,
  },
];

const rating = {
  store_id: STORE_ID,
  store_name: "Sharma Foods",
  average_rating: 4.5,
  total_reviews: 2,
  five_star: 1,
  four_star: 1,
  three_star: 0,
  two_star: 0,
  one_star: 0,
};

const reviews = {
  items: [
    {
      id: "44444444-4444-4444-8444-444444444444",
      rating: 5,
      comment: "Great value, fresh food.",
      created_at: "2026-10-30T10:00:00+00:00",
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
  store_name: "Sharma Foods",
};

// Second fixture store, used by the W3 same-store
// cart-guard spec: adding it to a cart that already
// holds Sharma Foods must ask before replacing.
const LISTING_ID_2 = "55555555-5555-4555-8555-555555555555";
const STORE_ID_2 = "66666666-6666-4666-8666-666666666666";

const listing2 = {
  ...listing,
  id: LISTING_ID_2,
  store: {
    id: STORE_ID_2,
    name: "Cafe Two",
    locality: "Dwarka Sector 6",
    city: "New Delhi",
    state: "Delhi",
    pincode: "110075",
    timezone: "Asia/Kolkata",
  },
  title: "Morning Cafe Box",
  selling_price: "120.00",
  reference_value: "200.00",
  images: [{ storage_path: `${LISTING_ID_2}/photo.jpg`, alt_text: "Cafe box", display_order: 0 }],
};

// --- W3 in-memory state (reset on stub restart) ---
const USER = {
  id: "77777777-7777-4777-8777-777777777777",
  email: "buyer@example.com",
  aud: "authenticated",
  role: "authenticated",
};
const SESSION = {
  access_token: "e2e-fake-access-token",
  refresh_token: "e2e-fake-refresh-token",
  expires_in: 3600,
  token_type: "bearer",
  user: USER,
};
const orders = new Map();
const pickupTokens = new Map();
let pickupTokenSeq = 1;
const LEGACY_PICKUP_TOKEN = "d".repeat(64);
const merchantListings = new Map();
const merchantImages = new Map();
let orderSeq = 1;
const notifications = [
  {
    id: "88888888-8888-4888-8888-888888888888",
    notification_type: "payment_captured",
    title: "Payment received",
    body: "Your payment was captured.",
    reference_type: "order",
    reference_id: null,
    read_at: null,
    created_at: "2026-10-31T12:00:00+00:00",
    is_read: false,
  },
];

function orderDetail(order) {
  return {
    id: order.id,
    order_number: order.order_number,
    status: order.status,
    payment: {
      status: order.payment_status,
      gateway_label: "Razorpay",
      amount_paid: order.payment_status === "captured" ? order.total_amount : "0.00",
      paid_at: order.payment_status === "captured" ? "2026-10-31T12:10:00+00:00" : null,
    },
    subtotal_amount: order.total_amount,
    discount_amount: "0.00",
    platform_fee_amount: "0.00",
    tax_amount: "0.00",
    total_amount: order.total_amount,
    currency: "INR",
    created_at: "2026-10-31T12:00:00+00:00",
    updated_at: "2026-10-31T12:00:00+00:00",
    confirmed_at: order.status === "confirmed" ? "2026-10-31T12:10:00+00:00" : null,
    collected_at: null,
    cancelled_at: null,
    customer_note: null,
    cancellation_reason: null,
    store: {
      id: STORE_ID,
      name: "Sharma Foods",
      address_line_1: "Shop 1, Dwarka Sector 7",
      address_line_2: null,
      locality: "Dwarka Sector 7",
      city: "New Delhi",
      state: "Delhi",
      pincode: "110075",
      contact_phone: null,
      pickup_instructions: "Ask at the counter.",
    },
    pickup_starts_at: "2026-10-31T18:00:00+00:00",
    pickup_ends_at: "2026-10-31T21:00:00+00:00",
    reservation_expires_at: order.reservation_expires_at,
    pickup_available: order.status === "confirmed",
    items: [
      {
        listing_id: LISTING_ID,
        listing_type: "surprise_bag",
        title: "Evening Bakery Bag",
        description: "Fresh breads and pastries.",
        quantity: order.quantity,
        unit_price: "195.00",
        line_total: order.total_amount,
        reference_value: "300.00",
        dietary_classification: "vegetarian",
        allergen_codes: ["gluten"],
        image_path: `${LISTING_ID}/photo.jpg`,
      },
    ],
    timeline:
      order.status === "confirmed"
        ? [
            { status: "pending_payment", label: "Order placed", occurred_at: "2026-10-31T12:00:00+00:00", actor_type: "customer" },
            { status: "confirmed", label: "Payment captured", occurred_at: "2026-10-31T12:10:00+00:00", actor_type: "system" },
          ]
        : [{ status: "pending_payment", label: "Order placed", occurred_at: "2026-10-31T12:00:00+00:00", actor_type: "customer" }],
  };
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch {
        resolve({});
      }
    });
  });
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost:8000");
  // The real FastAPI allows the website origin; the stub
  // mirrors that so browser fetches are not CORS-blocked.
  res.setHeader("Access-Control-Allow-Origin", "*");
  // Wildcard: the stub serves no credentials, so any
  // header (including supabase-js x-supabase-api-version
  // and the Idempotency-Key) is fine here.
  res.setHeader("Access-Control-Allow-Headers", "*");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }
  res.setHeader("Content-Type", "application/json");
  // --- Stub Supabase Auth (W3): any password signs
  // the fixture user in; the token is never real. ---
  if (url.pathname === "/auth/v1/token") {
    res.end(JSON.stringify(SESSION));
    return;
  }
  if (url.pathname === "/auth/v1/user") {
    if (!req.headers.authorization) {
      res.writeHead(401);
      res.end(JSON.stringify({ msg: "missing authorization" }));
      return;
    }
    res.end(JSON.stringify(USER));
    return;
  }
  if (url.pathname === "/v1/me") {
    res.end(JSON.stringify({ id: USER.id, email: USER.email, platform_roles: [] }));
    return;
  }
  if (req.method === "POST" && url.pathname === "/v1/orders/reservations") {
    const body = await readBody(req);
    if (!req.headers["idempotency-key"]) {
      res.writeHead(422);
      res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: "Idempotency-Key header is required", request_id: "e2e" } }));
      return;
    }
    const quantity = body.items?.[0]?.quantity ?? 1;
    const total = (195 * quantity).toFixed(2);
    const expires = new Date(Date.now() + 5 * 60 * 1000).toISOString();
    const order = {
      id: `99999999-9999-4999-8999-99999999999${orderSeq}`,
      order_number: `SB-E2E-${orderSeq}`,
      status: "pending_payment",
      payment_status: "created",
      total_amount: total,
      quantity,
      reservation_expires_at: expires,
    };
    orderSeq += 1;
    orders.set(order.id, order);
    res.writeHead(201);
    res.end(
      JSON.stringify({
        order_id: order.id,
        order_number: order.order_number,
        status: order.status,
        total_amount: total,
        currency: "INR",
        reservation_expires_at: expires,
        pickup_starts_at: "2026-10-31T18:00:00+00:00",
        pickup_ends_at: "2026-10-31T21:00:00+00:00",
        idempotent_replay: false,
      }),
    );
    return;
  }
  if (req.method === "POST" && /^\/v1\/orders\/[^/]+\/checkout$/.test(url.pathname)) {
    const orderId = url.pathname.split("/")[3];
    const order = orders.get(orderId);
    if (!order) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Order not found", request_id: "e2e" } }));
      return;
    }
    if (!req.headers["idempotency-key"]) {
      res.writeHead(422);
      res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: "Idempotency-Key header is required", request_id: "e2e" } }));
      return;
    }
    res.writeHead(201);
    res.end(
      JSON.stringify({
        order_id: order.id,
        payment_transaction_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        key_id: "rzp_test_mock",
        razorpay_order_id: "order_mock_1",
        amount_paise: Math.round(Number(order.total_amount) * 100),
        currency: "INR",
        prefill_email: USER.email,
      }),
    );
    return;
  }
  if (req.method === "POST" && url.pathname === "/v1/payments/verify") {
    const body = await readBody(req);
    const order = [...orders.values()].find((o) => o.status === "pending_payment") ?? [...orders.values()].at(-1);
    if (order) {
      order.status = "confirmed";
      order.payment_status = "captured";
    }
    res.end(
      JSON.stringify({
        order_id: order?.id ?? "",
        payment_transaction_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        razorpay_payment_id: body.razorpay_payment_id ?? "pay_mock_1",
        verified: true,
        amount_paise: order ? Math.round(Number(order.total_amount) * 100) : 0,
        currency: "INR",
      }),
    );
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/orders") {
    const items = [...orders.values()].map((order) => ({
      id: order.id,
      order_number: order.order_number,
      status: order.status,
      payment_status: order.payment_status,
      total_amount: order.total_amount,
      currency: "INR",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:00+00:00",
      store: { id: STORE_ID, name: "Sharma Foods", locality: "Dwarka Sector 7", city: "New Delhi", state: "Delhi", pincode: "110075" },
      pickup_starts_at: "2026-10-31T18:00:00+00:00",
      pickup_ends_at: "2026-10-31T21:00:00+00:00",
      item_count: 1,
      items_preview: [{ title: "Evening Bakery Bag", quantity: order.quantity }],
    }));
    res.end(JSON.stringify({ items, total: items.length, page: 1, page_size: 20 }));
    return;
  }
  if (req.method === "GET" && /^\/v1\/orders\/[^/]+$/.test(url.pathname)) {
    const order = orders.get(url.pathname.split("/")[3]);
    if (!order) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Order not found", request_id: "e2e" } }));
      return;
    }
    res.end(JSON.stringify(orderDetail(order)));
    return;
  }
  if (url.pathname === "/v1/notifications") {
    const unreadOnly = url.searchParams.get("unread_only") === "true";
    const items = unreadOnly ? notifications.filter((n) => !n.is_read) : notifications;
    res.end(JSON.stringify({ items, total: items.length, page: 1, page_size: 50 }));
    return;
  }
  if (url.pathname === "/v1/notifications/unread-count") {
    res.end(JSON.stringify({ unread_count: notifications.filter((n) => !n.is_read).length }));
    return;
  }
  if (req.method === "POST" && /^\/v1\/notifications\/[^/]+\/read$/.test(url.pathname)) {
    const note = notifications.find((n) => n.id === url.pathname.split("/")[3]);
    if (note) note.is_read = true;
    res.end(JSON.stringify({ id: note?.id ?? "", read_at: "2026-10-31T12:20:00+00:00", already_read: false }));
    return;
  }
  if (req.method === "POST" && url.pathname === "/v1/notifications/read-all") {
    const count = notifications.filter((n) => !n.is_read).length;
    notifications.forEach((n) => {
      n.is_read = true;
    });
    res.end(JSON.stringify({ updated_count: count }));
    return;
  }
  if (url.pathname === "/v1/marketplace/categories") {
    res.end(JSON.stringify(categories));
    return;
  }
  if (url.pathname === "/v1/marketplace/listings") {
    const search = url.searchParams.get("search");
    const all = [listing, listing2];
    const items = search
      ? all.filter((item) => item.title.toLowerCase().includes(search.toLowerCase()))
      : all;
    res.end(JSON.stringify({ items, total: items.length, page: 1, page_size: 20 }));
    return;
  }
  if (url.pathname === `/v1/marketplace/listings/${LISTING_ID}`) {
    res.end(JSON.stringify(listing));
    return;
  }
  if (url.pathname === `/v1/marketplace/listings/${LISTING_ID_2}`) {
    res.end(JSON.stringify(listing2));
    return;
  }
  if (url.pathname.startsWith("/v1/marketplace/listings/")) {
    res.writeHead(404);
    res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Listing not found", request_id: "e2e" } }));
    return;
  }

  // --- W4 merchant fixtures (reset on stub restart) ---
  if (url.pathname === "/v1/merchants") {
    res.end(JSON.stringify([{
      id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      legal_name: "Sharma Foods Pvt Ltd",
      display_name: "Sharma Foods",
      business_type: "bakery",
      business_email: null,
      business_phone: null,
      status: "approved",
      verification_status: "verified",
      created_at: "2026-10-31T10:00:00+00:00",
      updated_at: "2026-10-31T10:00:00+00:00",
    }]));
    return;
  }
  if (url.pathname === "/v1/merchants/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/stores") {
    res.end(JSON.stringify([{
      id: STORE_ID,
      merchant_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
      name: "Sharma Foods",
      slug: "sharma-foods",
      address_line_1: "Shop 1, Dwarka Sector 7",
      address_line_2: null,
      locality: "Dwarka Sector 7",
      city: "New Delhi",
      state: "Delhi",
      pincode: "110075",
      country_code: "IN",
      contact_phone: null,
      pickup_instructions: "Ask at the counter.",
      timezone: "Asia/Kolkata",
      status: "active",
      created_at: "2026-10-31T10:00:00+00:00",
      updated_at: "2026-10-31T10:00:00+00:00",
    }]));
    return;
  }
  if (req.method === "GET" && url.pathname === `/v1/stores/${STORE_ID}/hours`) {
    res.end(JSON.stringify({ store_id: STORE_ID, hours: [
      { weekday: 0, is_closed: false, opens_at: "09:00:00", closes_at: "21:00:00" },
      { weekday: 6, is_closed: true, opens_at: null, closes_at: null },
    ] }));
    return;
  }
  if (req.method === "PUT" && url.pathname === `/v1/stores/${STORE_ID}/hours`) {
    const body = await readBody(req);
    res.end(JSON.stringify({ store_id: STORE_ID, processed: body.hours?.length ?? 0, hours: body.hours ?? [] }));
    return;
  }
  if (url.pathname === "/v1/categories") {
    res.end(JSON.stringify(categories));
    return;
  }
  if (req.method === "POST" && url.pathname === `/v1/stores/${STORE_ID}/listings`) {
    const body = await readBody(req);
    const listing = {
      id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
      store_id: STORE_ID,
      template_id: null,
      listing_type: body.listing_type,
      category_id: body.category_id ?? null,
      title: body.title,
      description: body.description ?? null,
      contents_description: body.contents_description ?? null,
      reference_value: String(body.reference_value),
      selling_price: String(body.selling_price),
      currency: "INR",
      total_quantity: body.total_quantity,
      reserved_quantity: 0,
      sold_quantity: 0,
      available_quantity: body.total_quantity,
      sale_starts_at: body.sale_starts_at ?? "2026-10-31T12:00:00+00:00",
      sale_ends_at: body.sale_ends_at,
      pickup_starts_at: body.pickup_starts_at,
      pickup_ends_at: body.pickup_ends_at,
      prepared_at: body.prepared_at ?? null,
      best_before_at: body.best_before_at ?? null,
      allergen_codes: body.allergen_codes ?? [],
      dietary_classification: body.dietary_classification ?? "unknown",
      storage_instructions: body.storage_instructions ?? null,
      food_safety_notes: body.food_safety_notes ?? null,
      status: "draft",
      published_at: null,
      created_by: USER.id,
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:00+00:00",
    };
    merchantListings.set(listing.id, listing);
    merchantImages.set(listing.id, []);
    res.writeHead(201);
    res.end(JSON.stringify(listing));
    return;
  }
  if (req.method === "GET" && url.pathname === `/v1/stores/${STORE_ID}/listings`) {
    res.end(JSON.stringify([...merchantListings.values()]));
    return;
  }
  if (req.method === "GET" && /^\/v1\/listings\/[^/]+$/.test(url.pathname)) {
    const listing = merchantListings.get(url.pathname.split("/")[3]);
    if (!listing) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Listing not found", request_id: "e2e" } }));
      return;
    }
    res.end(JSON.stringify(listing));
    return;
  }
  if (req.method === "PATCH" && /^\/v1\/listings\/[^/]+$/.test(url.pathname)) {
    const listing = merchantListings.get(url.pathname.split("/")[3]);
    if (!listing) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Listing not found", request_id: "e2e" } }));
      return;
    }
    if (listing.status === "cancelled" || listing.status === "expired") {
      res.writeHead(422);
      res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: "Listing cannot be edited", request_id: "e2e" } }));
      return;
    }
    const body = await readBody(req);
    Object.assign(listing, body);
    listing.available_quantity = listing.total_quantity - listing.reserved_quantity - listing.sold_quantity;
    res.end(JSON.stringify(listing));
    return;
  }
  const transitionMatch = url.pathname.match(/^\/v1\/listings\/([^/]+)\/(publish|pause|resume|cancel)$/);
  if (req.method === "POST" && transitionMatch) {
    const listing = merchantListings.get(transitionMatch[1]);
    if (!listing) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Listing not found", request_id: "e2e" } }));
      return;
    }
    const action = transitionMatch[2];
    const target = action === "publish" || action === "resume" ? "active" : action === "pause" ? "paused" : action === "cancel" ? "cancelled" : action;
    const allowed = {
      draft: ["active", "cancelled"],
      scheduled: ["active", "cancelled"],
      active: ["paused", "cancelled"],
      paused: ["active", "cancelled"],
      sold_out: ["cancelled"],
      expired: ["cancelled"],
      cancelled: [],
    }[listing.status] ?? [];
    if (!allowed.includes(target)) {
      res.writeHead(422);
      res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: `Cannot move listing from ${listing.status} to ${target}`, request_id: "e2e" } }));
      return;
    }
    listing.status = target;
    res.end(JSON.stringify(listing));
    return;
  }
  if (req.method === "GET" && /^\/v1\/listings\/[^/]+\/inventory$/.test(url.pathname)) {
    const listing = merchantListings.get(url.pathname.split("/")[3]);
    if (!listing) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Listing not found", request_id: "e2e" } }));
      return;
    }
    res.end(JSON.stringify({
      listing_id: listing.id,
      store_id: listing.store_id,
      status: listing.status,
      total_quantity: listing.total_quantity,
      reserved_quantity: listing.reserved_quantity,
      sold_quantity: listing.sold_quantity,
      available_quantity: listing.available_quantity,
      sale_ends_at: listing.sale_ends_at,
      pickup_ends_at: listing.pickup_ends_at,
    }));
    return;
  }
  if (req.method === "GET" && /^\/v1\/listings\/[^/]+\/images$/.test(url.pathname)) {
    const images = merchantImages.get(url.pathname.split("/")[3]) ?? [];
    res.end(JSON.stringify(images));
    return;
  }
  if (req.method === "POST" && /^\/v1\/listings\/[^/]+\/images$/.test(url.pathname)) {
    const listingId = url.pathname.split("/")[3];
    const body = await readBody(req);
    if (!body.storage_path?.startsWith(`${listingId}/`)) {
      res.writeHead(422);
      res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: "storage_path must start with this listing id", request_id: "e2e" } }));
      return;
    }
    const image = { id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc", listing_id: listingId, storage_path: body.storage_path, alt_text: body.alt_text ?? null, display_order: body.display_order ?? 0, created_at: "2026-10-31T12:00:00+00:00" };
    merchantImages.get(listingId)?.push(image);
    res.writeHead(201);
    res.end(JSON.stringify(image));
    return;
  }
  if (url.pathname === "/v1/merchant/dashboard") {
    res.end(JSON.stringify({
      period: { from: null, to: null },
      store: { store_id: STORE_ID, store_name: "Sharma Foods", store_status: "active", timezone: "Asia/Kolkata", open_now: null, store_count: 1 },
      orders: { total_orders: 3, paid_orders: 2, awaiting_payment_orders: 1, collected_orders: 1, cancelled_orders: 0, expired_orders: 0, refund_orders: 0, captured_order_value: "390.00", currency: "INR" },
      inventory: { total_listings: 2, published_listings: 1, draft_listings: 1, paused_listings: 0, sold_out_listings: 0, total_available_units: 15, total_reserved_units: 2, total_sold_units: 3 },
      pickups: { upcoming_pickups: 1, in_window_pickups: 1, completed_collections: 1, window_expired_pickups: 0 },
      ratings: { average_rating: 4.5, total_visible_reviews: 2, five_star: 1, four_star: 1, three_star: 0, two_star: 0, one_star: 0 },
    }));
    return;
  }
  if (url.pathname === "/v1/merchant/dashboard/sales") {
    const bucket = { period_start: "2026-10-31", total_orders: 3, captured_orders: 2, pending_payment_orders: 1, failed_payment_orders: 0, collected_orders: 1, cancelled_or_expired_orders: 0, captured_order_value: "390.00", currency: "INR" };
    res.end(JSON.stringify({
      period: { from: null, to: null },
      store: { store_id: STORE_ID, store_name: "Sharma Foods", store_status: "active", timezone: "Asia/Kolkata", open_now: null, store_count: 1 },
      group_by: url.searchParams.get("group_by") ?? "day",
      reporting_timezone: "Asia/Kolkata",
      buckets: [bucket],
      totals: { ...bucket, period_start: "total" },
    }));
    return;
  }
  if (url.pathname === "/v1/merchant/dashboard/inventory") {
    res.end(JSON.stringify({
      period: { from: null, to: null },
      store: { store_id: STORE_ID, store_name: "Sharma Foods", store_status: "active", timezone: "Asia/Kolkata", open_now: null, store_count: 1 },
      summary: { total_listings: 2, published_listings: 1, draft_listings: 1, paused_listings: 0, sold_out_listings: 0, total_available_units: 15, total_reserved_units: 2, total_sold_units: 3 },
      low_stock_listings: [],
    }));
    return;
  }
  if (url.pathname === "/v1/merchant/dashboard/pickups") {
    res.end(JSON.stringify({
      period: { from: null, to: null },
      store: { store_id: STORE_ID, store_name: "Sharma Foods", store_status: "active", timezone: "Asia/Kolkata", open_now: null, store_count: 1 },
      counts: { upcoming_pickups: 1, in_window_pickups: 1, completed_collections: 1, window_expired_pickups: 0 },
      orders: [{ order_number: "SB-E2E-1", status: "confirmed", pickup_starts_at: "2026-10-31T18:00:00+00:00", pickup_ends_at: "2026-10-31T21:00:00+00:00", category: "upcoming", total_quantity: 1 }],
    }));
    return;
  }
  if (url.pathname === "/v1/merchant/dashboard/stores") {
    res.end(JSON.stringify({
      period: { from: null, to: null },
      stores: [{ store_id: STORE_ID, store_name: "Sharma Foods", store_status: "active", total_orders: 3, captured_order_value: "390.00", collected_orders: 1, active_listings: 1, available_units: 15, average_rating: 4.5, review_count: 2 }],
    }));
    return;
  }
  if (url.pathname === "/v1/merchant/orders/summary") {
    res.end(JSON.stringify({ total: 1, awaiting_payment: 0, paid: 1, upcoming_pickups: 1, completed: 0, cancelled_or_expired: 0 }));
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/merchant/orders") {
    const items = [...orders.values()].map((order) => ({
      id: order.id,
      order_number: order.order_number,
      status: order.status,
      payment_status: order.payment_status,
      total_amount: order.total_amount,
      currency: "INR",
      created_at: "2026-10-31T12:00:00+00:00",
      store: { id: STORE_ID, name: "Sharma Foods", locality: "Dwarka Sector 7", city: "New Delhi", state: "Delhi", pincode: "110075" },
      pickup_starts_at: "2026-10-31T18:00:00+00:00",
      pickup_ends_at: "2026-10-31T21:00:00+00:00",
      item_count: 1,
      items_preview: [{ title: "Evening Bakery Bag", quantity: order.quantity }],
    }));
    res.end(JSON.stringify({ items, total: items.length, page: 1, page_size: 20 }));
    return;
  }
  if (req.method === "GET" && /^\/v1\/merchant\/orders\/[^/]+$/.test(url.pathname)) {
    const order = orders.get(url.pathname.split("/")[4]);
    if (!order) {
      res.writeHead(404);
      res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Order not found", request_id: "e2e" } }));
      return;
    }
    res.end(JSON.stringify(orderDetail(order)));
    return;
  }
  const pickupTokenMatch = url.pathname.match(/^\/v1\/orders\/([^/]+)\/pickup-token$/);
  if (req.method === "POST" && pickupTokenMatch) {
    const order = orders.get(pickupTokenMatch[1]);
    const eligible =
      order &&
      (order.status === "confirmed" || order.status === "ready_for_pickup") &&
      order.payment_status === "captured";
    if (!eligible) {
      res.writeHead(422);
      res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: "Order is not eligible for pickup", request_id: "e2e" } }));
      return;
    }
    // Deterministic per-issuance token (unique across
    // parallel workers): the real backend mints 32
    // random bytes; the stub mints a counter-based
    // 64-hex value so verify can resolve the exact
    // order. A fresh issuance invalidates the old one.
    for (const [oldToken, entry] of pickupTokens.entries()) {
      if (entry.orderId === order.id) pickupTokens.delete(oldToken);
    }
    const token = pickupTokenSeq.toString(16).padStart(64, "0");
    pickupTokenSeq += 1;
    pickupTokens.set(token, { orderId: order.id, used: false });
    res.end(JSON.stringify({
      order_id: order.id,
      order_number: order.order_number,
      pickup_token: token,
      qr_payload: `SB1:${token}`,
      expires_at: "2026-10-31T21:30:00+00:00",
      pickup_starts_at: "2026-10-31T18:00:00+00:00",
      pickup_ends_at: "2026-10-31T21:00:00+00:00",
      store_name: "Sharma Foods",
      pickup_instructions: "Ask at the counter.",
    }));
    return;
  }
  if (req.method === "POST" && url.pathname === "/v1/merchant/pickups/verify") {
    const body = await readBody(req);
    const token = String(body.pickup_token ?? "");
    const issued = pickupTokens.get(token);
    if (issued && !issued.used && body.store_id === STORE_ID) {
      issued.used = true;
      const order = orders.get(issued.orderId);
      if (order) order.status = "collected";
      res.end(JSON.stringify({
        order_id: order?.id ?? "99999999-9999-4999-8999-999999999991",
        order_number: order?.order_number ?? "SB-E2E-1",
        store_name: "Sharma Foods",
        status: "collected",
        collected_at: "2026-10-31T18:30:00+00:00",
        items: [{ title: "Evening Bakery Bag", quantity: 1 }],
      }));
      return;
    }
    if (body.store_id === STORE_ID && token === LEGACY_PICKUP_TOKEN) {
      const order = [...orders.values()].find((o) => o.status === "confirmed") ?? [...orders.values()].at(-1);
      if (order) order.status = "collected";
      res.end(JSON.stringify({
        order_id: order?.id ?? "99999999-9999-4999-8999-999999999991",
        order_number: order?.order_number ?? "SB-E2E-1",
        store_name: "Sharma Foods",
        status: "collected",
        collected_at: "2026-10-31T18:30:00+00:00",
        items: [{ title: "Evening Bakery Bag", quantity: 1 }],
      }));
      return;
    }
    res.writeHead(422);
    res.end(JSON.stringify({ error: { code: "VALIDATION_ERROR", message: "Pickup token is invalid, expired, or already used", request_id: "e2e" } }));
    return;
  }
  if (url.pathname === `/v1/stores/${STORE_ID}/rating-summary`) {
    res.end(JSON.stringify(rating));
    return;
  }
  if (url.pathname === `/v1/stores/${STORE_ID}/reviews`) {
    res.end(JSON.stringify(reviews));
    return;
  }
  // ---- W6 admin fixtures (M11 shapes) ----
  // Fixed fixtures, independent of the dynamic
  // customer orders map, so the admin spec is
  // deterministic. Review actions mutate the
  // fixture state, so a detail refetch after a
  // decision shows the backend's new status —
  // the portal never updates status locally.
  const ADMIN_MERCHANT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
  const ADMIN_ORDER_ID = "99999999-9999-4999-8999-999999999999";
  const ADMIN_REFUND_ORDER_ID = "88888888-8888-4888-8888-888888888888";
  if (typeof globalThis.__adminMerchant === "undefined") {
    globalThis.__adminMerchant = {
      id: ADMIN_MERCHANT_ID,
      legal_name: "Sharma Foods Pvt Ltd",
      display_name: "Sharma Foods",
      business_type: "bakery",
      business_email: "hello@sharma.example",
      business_phone: null,
      status: "pending_review",
      verification_status: "pending",
      onboarding_notes: null,
      created_at: "2026-10-31T10:00:00+00:00",
      approved_at: null,
    };
    globalThis.__adminStoreStatus = "draft";
  }
  const adminMerchant = globalThis.__adminMerchant;
  const adminStore = {
    id: STORE_ID,
    merchant_id: ADMIN_MERCHANT_ID,
    merchant_name: "Sharma Foods",
    name: "Sharma Foods",
    status: globalThis.__adminStoreStatus,
    city: "New Delhi",
    state: "Delhi",
    pincode: "110075",
    address_line_1: "Shop 1",
    locality: "Dwarka Sector 7",
    timezone: "Asia/Kolkata",
    hours: [{ weekday: 1, opens_at: "09:00", closes_at: "21:00" }],
    listing_count: 1,
    order_count: 1,
    created_at: "2026-10-31T10:00:00+00:00",
  };
  const adminOrder = {
    id: ADMIN_ORDER_ID,
    order_number: "SB-ADMIN-1",
    store_id: STORE_ID,
    store_name: "Sharma Foods",
    merchant_name: "Sharma Foods",
    status: "confirmed",
    payment_status: "captured",
    total_amount: "195.00",
    currency: "INR",
    pickup_starts_at: "2026-10-31T18:00:00+00:00",
    pickup_ends_at: "2026-10-31T21:00:00+00:00",
    collected_at: null,
    customer_note: null,
    created_at: "2026-10-31T12:00:00+00:00",
    updated_at: "2026-10-31T12:00:00+00:00",
  };
  const adminRefundRow = {
    order_id: ADMIN_REFUND_ORDER_ID,
    order_number: "SB-ADMIN-2",
    store_name: "Sharma Foods",
    merchant_name: "Sharma Foods",
    amount: "195.00",
    currency: "INR",
    payment_status: "refund_pending",
    order_status: "refund_pending",
    created_at: "2026-10-31T11:00:00+00:00",
    updated_at: "2026-10-31T11:00:00+00:00",
  };
  const pageSlice = (rows) => {
    const page = Number(url.searchParams.get("page") ?? 1);
    const pageSize = Number(url.searchParams.get("page_size") ?? 20);
    return {
      items: rows.slice((page - 1) * pageSize, page * pageSize),
      total: rows.length,
      page,
      page_size: pageSize,
    };
  };
  if (req.method === "GET" && url.pathname === "/v1/admin/dashboard") {
    res.end(JSON.stringify({
      merchants_total: 1,
      merchants_approved: adminMerchant.status === "approved" ? 1 : 0,
      merchants_pending_review: adminMerchant.status === "pending_review" ? 1 : 0,
      stores_total: 1,
      stores_active: globalThis.__adminStoreStatus === "active" ? 1 : 0,
      stores_draft: globalThis.__adminStoreStatus === "draft" ? 1 : 0,
      stores_inactive: 0,
      stores_suspended: 0,
      listings_total: 1,
      listings_published: 0,
      listings_draft: 1,
      listings_paused: 0,
      listings_sold_out: 0,
      listings_expired: 0,
      orders_total: 1,
      orders_pending_payment: 0,
      orders_confirmed: 1,
      orders_ready_for_pickup: 0,
      orders_collected: 0,
      orders_cancelled_or_expired: 0,
      captured_payment_count: 1,
      captured_order_value: "195.00",
      failed_payment_count: 0,
      pending_payment_count: 0,
      reconciliation_required_count: 0,
      refund_pending_count: 1,
      visible_reviews_total: 1,
      average_visible_rating: 5,
      recent_orders: [adminOrder],
    }));
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/merchants") {
    let rows = [{ ...adminMerchant, store_count: 1 }];
    const status = url.searchParams.get("status");
    const verification = url.searchParams.get("verification_status");
    const search = url.searchParams.get("search");
    if (status) rows = rows.filter((r) => r.status === status);
    if (verification) rows = rows.filter((r) => r.verification_status === verification);
    if (search) rows = rows.filter((r) => r.display_name.toLowerCase().includes(search.toLowerCase()));
    res.end(JSON.stringify(pageSlice(rows)));
    return;
  }
  const adminMerchantMatch = url.pathname.match(/^\/v1\/admin\/merchants\/([^/]+)(\/review)?$/);
  if (adminMerchantMatch) {
    if (req.method === "GET" && !adminMerchantMatch[2]) {
      res.end(JSON.stringify({ ...adminMerchant, stores: [adminStore] }));
      return;
    }
    if (req.method === "POST" && adminMerchantMatch[2]) {
      const body = await readBody(req);
      const approved = body.action === "approve";
      adminMerchant.status = approved ? "approved" : "rejected";
      adminMerchant.verification_status = approved ? "verified" : "rejected";
      if (approved) adminMerchant.approved_at = "2026-10-31T13:00:00+00:00";
      res.end(JSON.stringify({
        merchant_id: adminMerchant.id,
        status: adminMerchant.status,
        verification_status: adminMerchant.verification_status,
      }));
      return;
    }
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/stores") {
    let rows = [adminStore];
    const status = url.searchParams.get("status");
    const city = url.searchParams.get("city");
    const search = url.searchParams.get("search");
    if (status) rows = rows.filter((r) => r.status === status);
    if (city) rows = rows.filter((r) => r.city.toLowerCase().includes(city.toLowerCase()));
    if (search) rows = rows.filter((r) => r.name.toLowerCase().includes(search.toLowerCase()));
    res.end(JSON.stringify(pageSlice(rows)));
    return;
  }
  const adminStoreMatch = url.pathname.match(/^\/v1\/admin\/stores\/([^/]+)(\/review)?$/);
  if (adminStoreMatch) {
    if (req.method === "GET" && !adminStoreMatch[2]) {
      res.end(JSON.stringify(adminStore));
      return;
    }
    if (req.method === "POST" && adminStoreMatch[2]) {
      const body = await readBody(req);
      globalThis.__adminStoreStatus = body.activate ? "active" : "inactive";
      res.end(JSON.stringify({ store_id: STORE_ID, activated: body.activate }));
      return;
    }
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/orders") {
    let rows = [adminOrder];
    const search = url.searchParams.get("order_number");
    const status = url.searchParams.get("status");
    const paymentStatus = url.searchParams.get("payment_status");
    if (search) rows = rows.filter((r) => r.order_number.includes(search));
    if (status) rows = rows.filter((r) => r.status === status);
    if (paymentStatus) rows = rows.filter((r) => r.payment_status === paymentStatus);
    res.end(JSON.stringify(pageSlice(rows)));
    return;
  }
  const adminOrderMatch = url.pathname.match(/^\/v1\/admin\/orders\/([^/]+)$/);
  if (req.method === "GET" && adminOrderMatch) {
    res.end(JSON.stringify({
      ...adminOrder,
      items: [{ title: "Evening Bakery Bag", quantity: 1, unit_price: "195.00", line_total: "195.00" }],
      events: [{ from_status: "pending_payment", to_status: "confirmed", actor_type: "system", reason: null, created_at: "2026-10-31T12:00:00+00:00" }],
    }));
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/payments") {
    let rows = [{
      order_id: adminOrder.id,
      order_number: adminOrder.order_number,
      store_name: adminOrder.store_name,
      merchant_name: adminOrder.merchant_name,
      amount: adminOrder.total_amount,
      currency: adminOrder.currency,
      payment_status: adminOrder.payment_status,
      order_status: adminOrder.status,
      created_at: adminOrder.created_at,
      updated_at: adminOrder.updated_at,
    }];
    const paymentStatus = url.searchParams.get("payment_status");
    if (paymentStatus) rows = rows.filter((r) => r.payment_status === paymentStatus);
    res.end(JSON.stringify(pageSlice(rows)));
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/refunds") {
    res.end(JSON.stringify(pageSlice([adminRefundRow])));
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/reviews") {
    let rows = [{
      id: "r-admin-1",
      store_id: STORE_ID,
      store_name: "Sharma Foods",
      rating: 5,
      comment: "Great thali.",
      moderation_status: "visible",
      created_at: "2026-10-31T19:00:00+00:00",
    }];
    const rating = url.searchParams.get("rating");
    const moderation = url.searchParams.get("moderation_status");
    if (rating) rows = rows.filter((r) => r.rating === Number(rating));
    if (moderation) rows = rows.filter((r) => r.moderation_status === moderation);
    res.end(JSON.stringify(pageSlice(rows)));
    return;
  }
  if (req.method === "GET" && url.pathname === "/v1/admin/activity") {
    let rows = [{
      order_number: "SB-ADMIN-1",
      from_status: "pending_payment",
      to_status: "confirmed",
      actor_type: "system",
      reason: null,
      created_at: "2026-10-31T12:00:00+00:00",
    }];
    const search = url.searchParams.get("order_number");
    if (search) rows = rows.filter((r) => r.order_number.includes(search));
    res.end(JSON.stringify(pageSlice(rows)));
    return;
  }
  res.writeHead(404);
  res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found", request_id: "e2e" } }));
});

server.listen(8000, () => {
  console.log("SaveBite e2e stub API listening on http://localhost:8000");
});
