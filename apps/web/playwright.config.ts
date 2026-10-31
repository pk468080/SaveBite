import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Browsers are NOT installed by `npm install`. Run
  // `npx playwright install chromium` once before
  // running these specs. CI must do the same.
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
