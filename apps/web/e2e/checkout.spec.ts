import { expect, test } from "@playwright/test";

/**
 * W3 mocked end-to-end customer journey (NOT a
 * production payment test): stub Supabase Auth,
 * stub FastAPI, and a mocked Razorpay Checkout SDK
 * injected before page scripts run. Steps:
 * sign in → browse → add to cart → reserve →
 * mock checkout → backend verification → confirmed
 * order → history → detail.
 */

const LISTING_ID = "11111111-1111-4111-8111-111111111111";

test.beforeEach(async ({ page }) => {
  // Mock Razorpay Checkout: the app's loader sees
  // window.Razorpay and never loads the real script.
  // open() invokes the success handler asynchronously,
  // exactly like a completed mock checkout.
  await page.addInitScript(() => {
    class MockRazorpay {
      private options: Record<string, unknown>;
      constructor(options: Record<string, unknown>) {
        this.options = options;
      }
      open() {
        const handler = this.options.handler as (response: {
          razorpay_order_id: string;
          razorpay_payment_id: string;
          razorpay_signature: string;
        }) => void;
        setTimeout(() => {
          handler({
            razorpay_order_id: "order_mock_1",
            razorpay_payment_id: "pay_mock_1",
            razorpay_signature: "sig_mock_1",
          });
        }, 0);
      }
      close() {}
    }
    (window as unknown as { Razorpay: typeof MockRazorpay }).Razorpay = MockRazorpay;
  });
});

async function signIn(page: import("@playwright/test").Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("buyer@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
}

test("mocked customer journey: reserve, pay, confirm, view order", async ({ page }) => {
  // Dev-server cold compiles can be slow under
  // parallel workers; the journey itself is fast.
  test.setTimeout(90000);
  await signIn(page);

  await page.goto(`/marketplace/${LISTING_ID}`);
  await expect(page.getByText("Evening Bakery Bag").first()).toBeVisible();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added.")).toBeVisible();

  await page.goto("/cart");
  await expect(page.getByText("Evening Bakery Bag")).toBeVisible();
  await page.getByRole("button", { name: "Continue to checkout" }).click();

  // Reservation summary from the stub backend, with a
  // live countdown driven by the returned expiry.
  await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();
  await expect(page.getByText(/Order SB-E2E-/)).toBeVisible();
  await expect(page.getByRole("timer")).toBeVisible();

  await page.getByRole("button", { name: "Pay with Razorpay" }).click();
  // Verification + order re-read decide the result;
  // the callback alone never shows success.
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();
  await expect(page.getByText(/payment of .* was captured/i)).toBeVisible();

  await page.goto("/customer/orders");
  await expect(page.getByText(/SB-E2E-/).first()).toBeVisible();
  await expect(page.getByText("Payment: Payment captured").first()).toBeVisible();

  await page.getByRole("link", { name: /SB-E2E-/ }).first().click();
  // Detail is a server-rendered route: first visit
  // compiles it in dev, so allow longer than default.
  await expect(page.getByText("Evening Bakery Bag")).toBeVisible({ timeout: 60000 });
  await expect(page.getByText("Payment captured").first()).toBeVisible();
});

test("sign-in validation and password visibility", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();

  await page.locator("#password").fill("secret123");
  await expect(page.locator("#password")).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.locator("#password")).toHaveAttribute("type", "text");
});

test("same-store guard asks before replacing the cart", async ({ page }) => {
  await page.goto(`/marketplace/${LISTING_ID}`);
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added.")).toBeVisible();

  await page.goto("/marketplace/55555555-5555-4555-8555-555555555555");
  await expect(page.getByText("Morning Cafe Box").first()).toBeVisible();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByRole("dialog")).toContainText("Replace your cart?");
  await page.getByRole("button", { name: "Replace cart" }).click();

  await page.goto("/cart");
  await expect(page.getByText("Morning Cafe Box")).toBeVisible();
  await expect(page.getByText("Evening Bakery Bag")).toHaveCount(0);
});

/**
 * B1 mocked end-to-end checkout retry (NOT a production
 * payment test). This test MUST live in this file, after
 * the journey test: Playwright runs one spec file's tests
 * sequentially in a single worker, but all files share one
 * stub server, so a retry test in its own file would
 * create a second order that breaks the journey test's
 * orders-list assertions. Steps: sign in → reserve →
 * first modal DISMISSED (not a success) → notice + Pay
 * button again → retry reuses the same gateway order id
 * → mock checkout → backend verification → confirmed.
 *
 * The stub mirrors the fixed backend contract: a repeated
 * checkout with the same idempotency key re-issues the
 * same gateway order id. Dismissal itself is frontend
 * behaviour: it must never declare success, create a new
 * reservation, or mint a new idempotency key.
 */
test("dismissed modal is not success; retry reopens the same Razorpay order", async ({
  page,
}) => {
  test.setTimeout(90000);
  // Override the file-level always-succeed mock for this
  // test only: the first modal open dismisses, later opens
  // succeed. Every opened order id is recorded so the test
  // can prove the retry reopened Checkout with the SAME
  // order id.
  await page.addInitScript(() => {
    const opened: string[] = [];
    (window as unknown as { __openedRazorpayOrderIds: string[] }).__openedRazorpayOrderIds =
      opened;
    class DismissFirstRazorpay {
      private options: Record<string, unknown>;
      constructor(options: Record<string, unknown>) {
        this.options = options;
        opened.push(String(options.order_id));
      }
      open() {
        if (opened.length === 1) {
          const modal = this.options.modal as
            | { ondismiss?: () => void }
            | undefined;
          setTimeout(() => modal?.ondismiss?.(), 0);
          return;
        }
        const handler = this.options.handler as (response: {
          razorpay_order_id: string;
          razorpay_payment_id: string;
          razorpay_signature: string;
        }) => void;
        setTimeout(() => {
          handler({
            razorpay_order_id: String(this.options.order_id),
            razorpay_payment_id: "pay_mock_1",
            razorpay_signature: "sig_mock_1",
          });
        }, 0);
      }
      close() {}
    }
    (window as unknown as { Razorpay: typeof DismissFirstRazorpay }).Razorpay =
      DismissFirstRazorpay;
  });

  await signIn(page);

  await page.goto(`/marketplace/${LISTING_ID}`);
  await expect(page.getByText("Evening Bakery Bag").first()).toBeVisible();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added.")).toBeVisible();

  await page.goto("/cart");
  await page.getByRole("button", { name: "Continue to checkout" }).click();
  await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();

  // First attempt: modal dismissed. No success, no new
  // reservation — the page reports "not completed" and
  // offers the Pay button again.
  await page.getByRole("button", { name: "Pay with Razorpay" }).click();
  await expect(page.getByText(/Payment was not completed/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Pay with Razorpay" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Payment confirmed" }),
  ).toHaveCount(0);

  // Retry: same tab, same idempotency key, same gateway
  // order id — then a completed mock checkout verifies
  // through the backend and only then shows success.
  await page.getByRole("button", { name: "Pay with Razorpay" }).click();
  await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();

  const opened = await page.evaluate(
    () =>
      (window as unknown as { __openedRazorpayOrderIds: string[] })
        .__openedRazorpayOrderIds,
  );
  expect(opened).toEqual(["order_mock_1", "order_mock_1"]);
});

test("terminal stored order does not poison a fresh same-items checkout", async ({
  page,
}) => {
  test.setTimeout(90000);
  await signIn(page);

  // First attempt: reserve the bag.
  await page.goto(`/marketplace/${LISTING_ID}`);
  await expect(page.getByText("Evening Bakery Bag").first()).toBeVisible();
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added.")).toBeVisible();

  await page.goto("/cart");
  const reservationResponse = page.waitForResponse("**/v1/orders/reservations");
  await page.getByRole("button", { name: "Continue to checkout" }).click();
  const firstOrder = await (await reservationResponse).json();
  const firstOrderNumber = firstOrder.order_number as string;
  await expect(
    page.getByText(new RegExp(`Order ${firstOrderNumber}`)),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Pay with Razorpay" })).toBeVisible();

  // The order becomes terminal WITHOUT the checkout page
  // observing it — the production shape is a webhook
  // confirm or a background expiry while the customer is
  // elsewhere; here the stub's test-only control route
  // does the same to exactly this order.
  const expire = await page.request.post(
    `http://localhost:8000/__e2e__/orders/${firstOrder.order_id}/expire`,
  );
  expect(expire.ok()).toBe(true);

  // Same items, same tab, same quantity: the customer
  // buys again. Before W9.1 the stored terminal attempt
  // (and its fingerprint key, which the backend would
  // replay as the dead order) left this page stuck on
  // "can no longer be paid". Now it must reserve fresh.
  await page.goto(`/marketplace/${LISTING_ID}`);
  await page.getByRole("button", { name: "Add to cart" }).click();
  await expect(page.getByText("Added.")).toBeVisible();
  await page.goto("/cart");
  const secondReservationResponse = page.waitForResponse("**/v1/orders/reservations");
  await page.getByRole("button", { name: "Continue to checkout" }).click();
  const secondOrder = await (await secondReservationResponse).json();
  await expect(page.getByRole("heading", { name: "Checkout" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Pay with Razorpay" })).toBeVisible();
  const orderText = await page.getByText(/Order SB-E2E-/).first().textContent();
  expect(orderText).toContain("Order ");
  expect(orderText).not.toContain(firstOrderNumber);

  // Leave no pending order behind: the stub verify
  // endpoint confirms the FIRST pending order globally,
  // so a leftover pending order would steal another
  // spec's verification (the pickup spec seeds and
  // verifies its own order and asserts on that exact
  // order). Expiring this test's fresh reservation
  // keeps the shared stub clean for other specs.
  const expireSecond = await page.request.post(
    `http://localhost:8000/__e2e__/orders/${secondOrder.order_id}/expire`,
  );
  expect(expireSecond.ok()).toBe(true);
});
