import { expect, test } from "@playwright/test";

/**
 * W4 mocked merchant journey (NOT a production
 * merchant test): stub Supabase Auth + stub
 * FastAPI. Covers sign-in → dashboard → create
 * a Surprise Bag draft → publish → inventory →
 * orders → pickup verification (invalid + valid
 * tokens) → analytics → reviews, plus an
 * unauthorized store and a rejected transition.
 * Image upload through Supabase Storage is NOT
 * covered here — the stub serves no storage — so
 * the upload flow is covered by unit tests and
 * manual checks, not claimed as e2e-tested.
 */

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("buyer@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
}

test("mocked merchant journey: dashboard, draft, publish, inventory, orders, pickup", async ({
  page,
}) => {
  test.setTimeout(120000);
  await signIn(page);

  await page.goto("/merchant");
  await expect(page.getByRole("heading", { name: "Merchant dashboard" })).toBeVisible();
  await expect(page.getByText("Captured order value")).toBeVisible();
  await expect(page.getByText("390").first()).toBeVisible();

  // Create a Surprise Bag draft.
  await page.goto("/merchant/listings/new");
  await expect(page.getByLabel(/Title/)).toBeVisible({ timeout: 60000 });
  await page.getByLabel(/Title/).fill("Merchant E2E Bag");
  await page.getByLabel(/Reference/).fill("300");
  await page.getByLabel(/Selling price/).fill("195");
  await page.getByLabel(/Total quantity/).fill("10");
  await page.getByLabel(/Sale ends/).fill("2026-11-02T18:00");
  await page.getByLabel(/Pickup starts/).fill("2026-11-02T18:00");
  await page.getByLabel(/Pickup ends/).fill("2026-11-02T21:00");
  await page.getByRole("button", { name: "Create draft listing" }).click();
  await expect(page.getByRole("heading", { name: "Merchant E2E Bag" })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByText("Draft").first()).toBeVisible();

  // Publish, then check inventory shows the draft counts.
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByText("Active").first()).toBeVisible();
  await page.goto("/merchant/inventory");
  await expect(page.getByText("Merchant E2E Bag")).toBeVisible({ timeout: 60000 });

  // Seed one confirmed order through the stub
  // reservation + verify endpoints, then check
  // the merchant queue and detail show it.
  await page.evaluate(async () => {
    const reservation = await fetch("http://localhost:8000/v1/orders/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": "merchant-e2e-key-1" },
      body: JSON.stringify({
        store_id: "22222222-2222-4222-8222-222222222222",
        items: [{ listing_id: "11111111-1111-4111-8111-111111111111", quantity: 1 }],
      }),
    });
    const created = await reservation.json();
    await fetch("http://localhost:8000/v1/payments/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        razorpay_order_id: "order_mock_1",
        razorpay_payment_id: "pay_mock_1",
        razorpay_signature: "sig_mock_1",
      }),
    });
    return created.order_id;
  });
  await page.goto("/merchant/orders");
  await expect(page.getByText(/SB-E2E-/).first()).toBeVisible({ timeout: 60000 });
  await page.getByRole("link", { name: /SB-E2E-/ }).first().click();
  // Under full-suite parallel load the dynamic
  // route compile can stall client navigation, so
  // wait for the URL itself before asserting content.
  await page.waitForURL(/\/merchant\/orders\/[0-9a-f-]+/, { timeout: 120000 });
  await expect(page.getByText("Evening Bakery Bag")).toBeVisible({ timeout: 60000 });

  // Pickup: invalid token first, then a valid one.
  await page.goto("/merchant/pickups");
  await expect(page.getByRole("heading", { name: "Verify a pickup" })).toBeVisible({
    timeout: 60000,
  });
  await page.getByPlaceholder(/SB1:/).fill("SB1:badtoken123456");
  await page.getByRole("button", { name: "Verify pickup" }).click();
  await expect(page.getByText(/invalid, expired, or already used/)).toBeVisible();
  await page.getByPlaceholder(/SB1:/).fill("SB1:validtoken123456");
  await page.getByRole("button", { name: "Verify pickup" }).click();
  await expect(page.getByText("Pickup confirmed")).toBeVisible();

  // Analytics and reviews render real stub data.
  await page.goto("/merchant/analytics");
  await expect(page.getByText("Sales by day")).toBeVisible({ timeout: 60000 });
  await page.goto("/merchant/reviews");
  await expect(page.getByText("Great value, fresh food.")).toBeVisible({ timeout: 60000 });
});

test("unauthorized store shows not-found, rejected transition is refused", async ({ page }) => {
  test.setTimeout(120000);
  await signIn(page);

  await page.goto("/merchant/stores/00000000-0000-4000-8000-000000000000");
  await expect(page.getByText("Store not found")).toBeVisible({ timeout: 60000 });

  // Create a draft, cancel it, then confirm the
  // backend refuses publish afterwards (422) and
  // the portal no longer offers Publish.
  await page.goto("/merchant/listings/new");
  await expect(page.getByLabel(/Title/)).toBeVisible({ timeout: 60000 });
  await page.getByLabel(/Title/).fill("Cancel Test Bag");
  await page.getByLabel(/Reference/).fill("200");
  await page.getByLabel(/Selling price/).fill("130");
  await page.getByLabel(/Total quantity/).fill("5");
  await page.getByLabel(/Sale ends/).fill("2026-11-02T18:00");
  await page.getByLabel(/Pickup starts/).fill("2026-11-02T18:00");
  await page.getByLabel(/Pickup ends/).fill("2026-11-02T21:00");
  await page.getByRole("button", { name: "Create draft listing" }).click();
  await expect(page.getByRole("heading", { name: "Cancel Test Bag" })).toBeVisible({
    timeout: 60000,
  });
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await page.getByRole("button", { name: "Confirm cancel" }).click();
  await expect(page.getByText("Cancelled").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Publish" })).toHaveCount(0);
  const status = await page.evaluate(async () => {
    const response = await fetch(
      "http://localhost:8000/v1/listings/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/publish",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    );
    return response.status;
  });
  expect(status).toBe(422);
});
