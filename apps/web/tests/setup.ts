import "@testing-library/jest-dom/vitest";

// Test-only placeholder configuration so pure helpers
// (image URLs, config checks) can run without a real
// .env.local. Never a real credential.
process.env.NEXT_PUBLIC_SUPABASE_URL ??= "https://test.supabase.co";
process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??= "test-publishable-key";
process.env.NEXT_PUBLIC_API_BASE_URL ??= "http://localhost:8000";
process.env.NEXT_PUBLIC_SITE_URL ??= "http://localhost:3000";
