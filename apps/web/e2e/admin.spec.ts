import { expect, test, type Page } from "@playwright/test";

/**
 * W6 mocked admin journey (NOT a production
 * authorization test): stub Supabase Auth + stub
 * FastAPI admin fixtures. Covers: dashboard
 * counts and honest captured-value labelling,
 * merchant list → detail → approve with
 * confirmation and backend refetch, store
 * list → detail → activate, order list →
 * detail, payments + refunds tabs, reviews
 * read-only (no moderation buttons), activity
 * events, and the standalone access-denied
 * page. Real role authorization is enforced
 * by the backend gate, not by these mocks.
 */

async function signIn(page: Page) {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("buyer@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();
}

test("mocked admin journey: dashboard, approve, activate, orders, payments, reviews, activity", async ({
  page,
}) => {
  test.setTimeout(180000);
  await signIn(page);

  // Dashboard (layout gate passes on the stub 200).
  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Platform overview" })).toBeVisible();
  await expect(page.getByText("Captured order value", { exact: true })).toBeVisible();
  await expect(page.getByText(/It is not merchant earnings/)).toBeVisible();
  await expect(page.getByText(/Order SB-ADMIN-1/)).toBeVisible();

  // Merchants: list → detail → approve with confirmation → refetched status.
  await page.goto("/admin/merchants");
  await expect(page.getByRole("heading", { name: "Merchant applications" })).toBeVisible();
  await page.getByRole("link", { name: "Sharma Foods" }).first().click();
  await page.waitForURL(/\/admin\/merchants\/[0-9a-f-]+/, { timeout: 120000 });
  await expect(page.getByText("Pending review")).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  // No API call before confirmation: the confirm control only appears now.
  await expect(page.getByRole("button", { name: "Confirm approve" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm approve" }).click();
  // The panel's success banner is transient: the
  // page refetches and the refetched status is
  // the confirmation, not the banner.
  await expect(page.getByText("Approved").first()).toBeVisible();

  // Stores: list → detail → activate with confirmation → refetched status.
  await page.goto("/admin/stores");
  await expect(page.getByRole("heading", { name: "Stores" })).toBeVisible();
  await page.getByRole("link", { name: "Sharma Foods" }).first().click();
  await page.waitForURL(/\/admin\/stores\/[0-9a-f-]+/, { timeout: 120000 });
  await expect(page.getByText("Draft")).toBeVisible();
  await page.getByRole("button", { name: "Activate", exact: true }).click();
  await expect(page.getByRole("button", { name: "Confirm activation" })).toBeVisible();
  await page.getByRole("button", { name: "Confirm activation" }).click();
  // Same as the merchant decision: the refetched
  // status, not the transient banner, confirms it.
  await expect(page.getByText("Active")).toBeVisible();

  // Orders: list → detail with items.
  await page.goto("/admin/orders");
  await expect(page.getByRole("heading", { name: "Orders" })).toBeVisible();
  await page.getByRole("link", { name: /Order SB-ADMIN-1/ }).click();
  await page.waitForURL(/\/admin\/orders\/[0-9a-f-]+/, { timeout: 120000 });
  await expect(page.getByText("Evening Bakery Bag")).toBeVisible();

  // Payments: exceptions, then the refunds tab.
  await page.goto("/admin/payments");
  await expect(page.getByRole("heading", { name: "Payments and refunds" })).toBeVisible();
  await expect(page.getByText(/Order SB-ADMIN-1/)).toBeVisible();
  await page.getByRole("button", { name: "Refunds" }).click();
  await expect(page.getByText(/Order SB-ADMIN-2/)).toBeVisible();

  // Reviews: visible row, and no moderation actions anywhere.
  await page.goto("/admin/reviews");
  await expect(page.getByRole("heading", { name: "Reviews" })).toBeVisible();
  await expect(page.getByText("Great thali.")).toBeVisible();
  await expect(page.getByText(/The backend has no review moderation endpoint/)).toBeVisible();
  await expect(page.getByRole("button", { name: /hide/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /delete/i })).toHaveCount(0);

  // Activity: recorded order status events.
  await page.goto("/admin/activity");
  await expect(page.getByRole("heading", { name: "Activity" })).toBeVisible();
  await expect(page.getByText(/Order SB-ADMIN-1: pending_payment → confirmed/)).toBeVisible();
});

test("access-denied page renders standalone", async ({ page }) => {
  test.setTimeout(120000);
  await page.goto("/unauthorized");
  await expect(
    page.getByRole("heading", { name: "You do not have access to this area" }),
  ).toBeVisible();
});
