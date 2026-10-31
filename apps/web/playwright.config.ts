import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Dev-server cold compiles (first visit to a route)
  // can exceed the 5 s default under parallel workers.
  expect: { timeout: 15000 },
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
      // W3: point Supabase Auth at the stub so the
      // mocked sign-in works end to end. Real env
      // vars win over .env.local in Next.js, so these
      // override the placeholder values for e2e only.
      // Never a real credential.
      env: {
        NEXT_PUBLIC_SUPABASE_URL: "http://localhost:8000",
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "e2e-publishable-key",
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000",
        NEXT_PUBLIC_SITE_URL: "http://localhost:3000",
      },
    },
  ],
});
