import { expect, test } from "@playwright/test";

const LISTING_ID = "11111111-1111-4111-8111-111111111111";

test("listing detail shows real price, store, rating, and reviews", async ({ page }) => {
  await page.goto(`/marketplace/${LISTING_ID}`);
  await expect(page.getByRole("heading", { name: "Evening Bakery Bag" })).toBeVisible();
  await expect(page.getByText("Sharma Foods", { exact: true })).toBeVisible();
  await expect(page.getByText(/195/)).toBeVisible();
  await expect(page.getByText(/4.50/)).toBeVisible();
  await expect(page.getByText("Great value, fresh food.")).toBeVisible();
  // Pickup-only messaging, no purchase action in W2.
  await expect(page.getByText("Pickup only — no delivery")).toBeVisible();
  await expect(page.getByRole("link", { name: "Continue to Sign In" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /buy|checkout|reserve|pay now/i }),
  ).toHaveCount(0);
});

test("missing listing shows the unavailable state, not a crash", async ({ page }) => {
  await page.goto("/marketplace/99999999-9999-4999-8999-999999999999");
  await expect(page.getByText("This listing is no longer available")).toBeVisible();
  await expect(page.getByRole("link", { name: "Browse the marketplace" })).toBeVisible();
});
