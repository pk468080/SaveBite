import { expect, test } from "@playwright/test";

test("homepage loads with SaveBite branding", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Good food, rescued/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Marketplace" }).first()).toBeVisible();
});
