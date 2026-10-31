import { expect, test, type Page } from "@playwright/test";

/**
 * W5 mocked customer-to-merchant pickup journey
 * (NOT a production pickup test): stub Supabase
 * Auth + stub FastAPI. No real camera is used —
 * the merchant step submits the token through
 * manual entry, which verifies exactly the same
 * way as a scan. The test observes the mocked
 * issuance response to learn the token, the way
 * a merchant learns it by scanning the QR; the
 * token is never shown as page text, and the
 * spec asserts it is never written to browser
 * storage. Covers: eligible QR request, QR
 * display, hide + fresh request, merchant
 * verification, collected status on refetch,
 * already-used rejection, invalid-token
 * rejection, and ineligible-order gating.
 */

async function signIn(page: Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("buyer@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
}

/** Seed one stub order; confirm it when asked. Returns its id. */
async function seedOrder(page: Page, confirm: boolean): Promise<string> {
  return page.evaluate(async ({ key, confirm: shouldConfirm }) => {
    const reservation = await fetch("http://localhost:8000/v1/orders/reservations", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Idempotency-Key": key },
      body: JSON.stringify({
        store_id: "22222222-2222-4222-8222-222222222222",
        items: [{ listing_id: "11111111-1111-4111-8111-111111111111", quantity: 1 }],
      }),
    });
    const created = await reservation.json();
    if (shouldConfirm) {
      await fetch("http://localhost:8000/v1/payments/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          razorpay_order_id: "order_mock_1",
          razorpay_payment_id: "pay_mock_1",
          razorpay_signature: "sig_mock_1",
        }),
      });
    }
    return created.order_id as string;
  }, { key: `pickup-e2e-${Date.now()}-${Math.random()}`, confirm });
}

test("mocked pickup journey: QR request, merchant verify, collected on refetch", async ({
  page,
}) => {
  test.setTimeout(120000);
  await signIn(page);
  const orderId = await seedOrder(page, true);

  const issuedTokens: string[] = [];
  page.on("response", (response) => {
    if (
      response.url().endsWith("/pickup-token") &&
      response.request().method() === "POST"
    ) {
      void response
        .json()
        .then((body) => {
          if (typeof body.pickup_token === "string") issuedTokens.push(body.pickup_token);
        })
        .catch(() => {});
    }
  });

  await page.goto(`/customer/orders/${orderId}`);
  await expect(page.getByRole("heading", { name: /Order SB-E2E-/ })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole("button", { name: "Show Pickup QR" })).toBeVisible();
  await page.getByRole("button", { name: "Show Pickup QR" }).click();
  await expect(page.getByText(/Show this QR code to the merchant/)).toBeVisible();
  await expect(page.getByRole("img", { name: /Pickup QR code/ }).first()).toBeVisible();
  await expect.poll(() => issuedTokens.length, { timeout: 15000 }).toBeGreaterThan(0);
  const firstToken = issuedTokens.at(-1)!;

  // The token must never reach browser storage.
  const storedHasToken = await page.evaluate((token) => {
    const values = [
      ...Object.values(localStorage),
      ...Object.values(sessionStorage),
    ].join("\n");
    return values.includes("SB1:") || values.includes(token);
  }, firstToken);
  expect(storedHasToken).toBe(false);

  // Hide, then request a fresh code (the old
  // unused code is invalidated by the backend).
  await page.getByRole("button", { name: "Hide QR code" }).click();
  await expect(page.getByRole("img", { name: /Pickup QR code/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Show Pickup QR" }).click();
  await expect(page.getByText(/Show this QR code to the merchant/)).toBeVisible();
  await expect.poll(() => issuedTokens.length, { timeout: 15000 }).toBeGreaterThanOrEqual(2);
  const freshToken = issuedTokens.at(-1)!;
  expect(freshToken).not.toBe(firstToken);

  // Merchant verifies the fresh code by manual
  // entry (same backend verification as a scan).
  await page.goto("/merchant/pickups");
  await expect(page.getByRole("heading", { name: "Verify a pickup" })).toBeVisible({
    timeout: 60000,
  });
  await page.getByPlaceholder(/SB1:/).fill(`SB1:${freshToken}`);
  await page.getByRole("button", { name: "Verify pickup" }).click();
  await expect(page.getByText("Pickup confirmed")).toBeVisible();
  await page.getByRole("link", { name: "View order" }).click();
  await expect(page.getByText("Collected").first()).toBeVisible({ timeout: 60000 });

  // Customer sees the collected status on refetch,
  // and the QR action is gone for a collected order.
  await page.goto(`/customer/orders/${orderId}`);
  await expect(page.getByText(/Collected/).first()).toBeVisible({ timeout: 60000 });
  await expect(page.getByRole("button", { name: "Show Pickup QR" })).toHaveCount(0);

  // The same code cannot collect twice.
  await page.goto("/merchant/pickups");
  await page.getByPlaceholder(/SB1:/).fill(`SB1:${freshToken}`);
  await page.getByRole("button", { name: "Verify pickup" }).click();
  await expect(page.getByText(/invalid, expired, or already used/)).toBeVisible();
});

test("invalid token is refused, ineligible order cannot request a QR", async ({ page }) => {
  test.setTimeout(120000);
  await signIn(page);

  // Well-formed but unissued token: backend refusal.
  await page.goto("/merchant/pickups");
  await expect(page.getByRole("heading", { name: "Verify a pickup" })).toBeVisible({
    timeout: 60000,
  });
  await page.getByPlaceholder(/SB1:/).fill(`SB1:${"c".repeat(64)}`);
  await page.getByRole("button", { name: "Verify pickup" }).click();
  await expect(page.getByText(/invalid, expired, or already used/)).toBeVisible();

  // Pending-payment order: no QR action, pay-first guidance.
  const pendingId = await seedOrder(page, false);
  await page.goto(`/customer/orders/${pendingId}`);
  await expect(page.getByRole("heading", { name: /Order SB-E2E-/ })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.getByRole("button", { name: "Show Pickup QR" })).toHaveCount(0);
  await expect(page.getByText(/Pay for this order first/)).toBeVisible();
});
