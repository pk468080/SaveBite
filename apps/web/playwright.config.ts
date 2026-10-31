import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:3000" },
  // Browsers are NOT installed by `npm install`. Run
  // `npx playwright install chromium` once before
  // running these specs. CI must do the same.
  // The specs run against the e2e stub API (fixed
  // fixture responses, same shapes as FastAPI) on
  // port 8000, plus the Next dev server on port 3000.
  // A real backend is NOT required for e2e; a live
  // backend test is a separate, explicitly reported
  // check, never implied by these specs.
  webServer: [
    {
      command: "node e2e/stub-api.mjs",
      url: "http://localhost:8000/v1/marketplace/categories",
      reuseExistingServer: !process.env.CI,
      timeout: 30000,
    },
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
  ],
});
