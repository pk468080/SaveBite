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
