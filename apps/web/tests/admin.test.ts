import { describe, expect, it } from "vitest";
import {
  merchantStatusLabel,
  merchantVerificationLabel,
  moderationStatusLabel,
  storeStatusLabel,
} from "@/lib/admin";

/**
 * W6 admin labels: display text only, never
 * an access decision and never a status the
 * backend does not define.
 */
describe("admin labels", () => {
  it("labels merchant application and verification states", () => {
    expect(merchantStatusLabel("pending_review")).toBe("Pending review");
    expect(merchantStatusLabel("additional_information_required")).toBe(
      "Needs more information",
    );
    expect(merchantStatusLabel("approved")).toBe("Approved");
    expect(merchantVerificationLabel("under_review")).toBe("Verification under review");
    expect(merchantVerificationLabel("verified")).toBe("Verified");
  });

  it("labels store and moderation states", () => {
    expect(storeStatusLabel("active")).toBe("Active");
    expect(storeStatusLabel("suspended")).toBe("Suspended");
    expect(moderationStatusLabel("under_review")).toBe("Under review");
    expect(moderationStatusLabel("visible")).toBe("Visible");
  });

  it("passes unknown statuses through unchanged instead of inventing a label", () => {
    expect(merchantStatusLabel("something_new")).toBe("something_new");
    expect(storeStatusLabel("something_new")).toBe("something_new");
  });
});
