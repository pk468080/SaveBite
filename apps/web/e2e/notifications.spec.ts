import { expect, test } from "@playwright/test";

/** W3 notifications (M12 read APIs) against the stub. */

test("notifications list and mark-as-read", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("buyer@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();

  await page.goto("/customer/notifications");
  await expect(page.getByText("Payment received")).toBeVisible();
  await page.getByRole("button", { name: "Mark as read" }).click();
  await expect(page.getByRole("button", { name: "Mark as read" })).toHaveCount(0);
});
