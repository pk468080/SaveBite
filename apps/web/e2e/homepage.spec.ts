import { expect, test } from "@playwright/test";

test("homepage loads with SaveBite branding and real fixture data", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Rescue Great Food. Save More. Waste Less." }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Explore Food" }).first()).toBeVisible();
  // Real API data (from the e2e stub): category tile and a listing card.
  await expect(page.getByRole("link", { name: "Bakery", exact: true })).toBeVisible();
  // The same listing appears in both "Ending soon" and "Newly listed".
  await expect(page.getByText("Evening Bakery Bag").first()).toBeVisible();
  await expect(page.getByRole("link", { name: "How It Works" }).first()).toBeVisible();
});

test("homepage Explore Food CTA navigates to the marketplace", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Explore Food" }).first().click();
  await expect(page).toHaveURL(/\/marketplace/);
});
