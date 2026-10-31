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
  if (url.pathname === `/v1/stores/${STORE_ID}/rating-summary`) {
    res.end(JSON.stringify(rating));
    return;
  }
  if (url.pathname === `/v1/stores/${STORE_ID}/reviews`) {
    res.end(JSON.stringify(reviews));
    return;
  }
  res.writeHead(404);
  res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found", request_id: "e2e" } }));
});

server.listen(8000, () => {
  console.log("SaveBite e2e stub API listening on http://localhost:8000");
});
