import { expect, test } from "@playwright/test";

test("marketplace renders real listings and search updates the URL", async ({ page }) => {
  await page.goto("/marketplace");
  await expect(page.getByText("Evening Bakery Bag")).toBeVisible();
  await expect(page.getByText(/2 listings/)).toBeVisible();

  // Search is debounced (400 ms) and lands in the URL.
  await page.getByLabel("Search listings").fill("bakery");
  await expect(page).toHaveURL(/search=bakery/);
  await expect(page.getByText("Evening Bakery Bag")).toBeVisible();

  // A search with no match shows the designed empty state.
  await page.getByLabel("Search listings").fill("zzz-no-match");
  await expect(page).toHaveURL(/search=zzz-no-match/);
  await expect(page.getByText("No listings match your search")).toBeVisible();
});

test("mobile filter drawer opens", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/marketplace");
  await page.getByRole("button", { name: "Filters" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // Scoped to the dialog: the desktop sidebar holds a
  // second, hidden City input at mobile widths.
  await expect(dialog.getByLabel("City")).toBeVisible();
});
