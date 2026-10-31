import { describe, expect, it } from "vitest";
import { configProblems } from "@/lib/config";

describe("environment validation", () => {
  it("reports every missing client-safe variable", () => {
    const missing = configProblems();
    // In the test environment no NEXT_PUBLIC_* values are
    // set, so all three must be reported — never silently
    // treated as configured.
    expect(missing).toEqual(
      expect.arrayContaining([
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
        "NEXT_PUBLIC_API_BASE_URL",
      ]),
    );
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
