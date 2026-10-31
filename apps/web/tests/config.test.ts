import { afterEach, describe, expect, it, vi } from "vitest";
import { configProblems } from "@/lib/config";

const CLIENT_VARS = [
  "NEXT_PUBLIC_SUPABASE_URL",
  "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
  "NEXT_PUBLIC_API_BASE_URL",
] as const;

describe("environment validation", () => {
  // Config values are captured at module load (Next.js
  // only inlines static process.env access into the
  // browser bundle), so the missing case needs a fresh
  // module import after clearing the environment.
  const saved: Record<string, string | undefined> = {};
  afterEach(() => {
    vi.resetModules();
    for (const name of CLIENT_VARS) {
      if (saved[name] === undefined) {
        delete process.env[name];
      } else {
        process.env[name] = saved[name];
      }
    }
  });

  it("reports every missing client-safe variable", async () => {
    for (const name of CLIENT_VARS) {
      saved[name] = process.env[name];
      delete process.env[name];
    }
    vi.resetModules();
    const fresh = await import("@/lib/config");
    // With no NEXT_PUBLIC_* values set, all three must
    // be reported — never silently treated as configured.
    expect(fresh.configProblems()).toEqual(expect.arrayContaining([...CLIENT_VARS]));
  });

  it("reports nothing when all client-safe variables are present", () => {
    // tests/setup.ts provides placeholders.
    expect(configProblems()).toEqual([]);
  });

  it("never lists a secret variable as required client config", () => {
    const missing = configProblems();
    for (const secret of [
      "SUPABASE_SERVICE_ROLE_KEY",
      "RAZORPAY_KEY_SECRET",
      "RAZORPAY_WEBHOOK_SECRET",
    ]) {
      expect(missing).not.toContain(secret);
    }
  });
});
