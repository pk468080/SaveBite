/**
 * Minimal stub FastAPI for Playwright e2e (W2).
 *
 * Serves the same response shapes as the real backend
 * for the public marketplace endpoints, with fixed
 * fixture data. It is NOT a backend replacement: it
 * exists only so e2e can run without a live Supabase
 * project. Run: `node e2e/stub-api.mjs` (port 8000).
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

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", "http://localhost:8000");
  // The real FastAPI allows the website origin; the stub
  // mirrors that so browser fetches are not CORS-blocked.
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Authorization, Content-Type");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }
  res.setHeader("Content-Type", "application/json");
  if (url.pathname === "/v1/marketplace/categories") {
    res.end(JSON.stringify(categories));
    return;
  }
  if (url.pathname === "/v1/marketplace/listings") {
    const search = url.searchParams.get("search");
    const items = search && !listing.title.toLowerCase().includes(search.toLowerCase()) ? [] : [listing];
    res.end(JSON.stringify({ items, total: items.length, page: 1, page_size: 20 }));
    return;
  }
  if (url.pathname === `/v1/marketplace/listings/${LISTING_ID}`) {
    res.end(JSON.stringify(listing));
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
