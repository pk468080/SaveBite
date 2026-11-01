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

/** W7: preferences save through the API and persist across a reload. */
test("notification preferences persist after reload", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email").fill("buyer@example.com");
  await page.locator("#password").fill("password123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My account" })).toBeVisible();

  await page.goto("/customer/notifications");
  await expect(
    page.getByRole("heading", { name: "Notification preferences" }),
  ).toBeVisible();
  const reminder = page.getByRole("checkbox", { name: "Pickup reminders" });
  await expect(reminder).toBeChecked();
  await reminder.click();
  await page.getByRole("button", { name: "Save preferences" }).click();
  await expect(page.getByText("Preferences saved.")).toBeVisible();

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Notification preferences" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: "Pickup reminders" }),
  ).not.toBeChecked();
  // Mandatory categories stay locked on.
  await expect(
    page.getByRole("checkbox", { name: "Payment updates" }),
  ).toBeDisabled();
});
