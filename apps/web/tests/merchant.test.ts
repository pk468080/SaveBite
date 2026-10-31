import { describe, expect, it } from "vitest";
import {
  allowedListingActions,
  isValidPickupToken,
  listingStatusLabel,
  normalisePickupToken,
  PINCODE_PATTERN,
  SLUG_PATTERN,
  validateIndianMobile,
  validateListingForm,
  type ListingFormValues,
} from "@/lib/merchant";
import { EMPTY_LISTING_FORM } from "@/components/merchant/listing-form";

function validForm(): ListingFormValues {
  return {
    ...EMPTY_LISTING_FORM,
    title: "Evening Bakery Bag",
    reference_value: "300",
    selling_price: "195",
    total_quantity: "10",
    sale_ends_at: "2026-11-01T18:00",
    pickup_starts_at: "2026-11-01T18:00",
    pickup_ends_at: "2026-11-01T21:00",
  };
}

/**
 * W4 merchant helpers. Validation mirrors the
 * backend rules (M3/M4) so forms fail fast; the
 * backend remains the authority.
 */
describe("merchant listing validation", () => {
  it("accepts a consistent form", () => {
    expect(validateListingForm(validForm())).toBeNull();
  });

  it("rejects a zero selling price and a bad quantity", () => {
    expect(validateListingForm({ ...validForm(), selling_price: "0" })).toMatch(/more than 0/);
    expect(validateListingForm({ ...validForm(), total_quantity: "0" })).toMatch(/above 0/);
    expect(validateListingForm({ ...validForm(), total_quantity: "1.5" })).toMatch(/whole number/);
  });

  it("rejects pickup end before sale end and before pickup start", () => {
    expect(
      validateListingForm({
        ...validForm(),
        pickup_starts_at: "2026-11-01T16:00",
        pickup_ends_at: "2026-11-01T17:00",
      }),
    ).toMatch(/not be before sale end/);
    expect(
      validateListingForm({
        ...validForm(),
        pickup_starts_at: "2026-11-01T20:00",
        pickup_ends_at: "2026-11-01T19:00",
      }),
    ).toMatch(/after pickup start/);
  });

  it("rejects bad allergen codes", () => {
    expect(validateListingForm({ ...validForm(), allergen_codes: "milk, bad code!" })).toMatch(
      /Allergen code/,
    );
    expect(validateListingForm({ ...validForm(), allergen_codes: "milk, nuts" })).toBeNull();
  });

  it("rejects best-before before prepared time", () => {
    expect(
      validateListingForm({
        ...validForm(),
        prepared_at: "2026-11-01T10:00",
        best_before_at: "2026-11-01T09:00",
      }),
    ).toMatch(/Best-before/);
  });
});

describe("merchant transitions", () => {
  it("allows only the backend transition set", () => {
    expect(allowedListingActions("draft")).toEqual(["publish", "cancel"]);
    expect(allowedListingActions("active")).toEqual(["pause", "cancel"]);
    expect(allowedListingActions("paused")).toEqual(["resume", "cancel"]);
    expect(allowedListingActions("cancelled")).toEqual([]);
    expect(allowedListingActions("sold_out")).toEqual(["cancel"]);
  });

  it("labels statuses without inventing new ones", () => {
    expect(listingStatusLabel("sold_out")).toBe("Sold out");
    expect(listingStatusLabel("paused")).toBe("Paused");
  });
});

describe("merchant field patterns", () => {
  it("validates pincode, slug and Indian mobile like the backend", () => {
    expect(PINCODE_PATTERN.test("110075")).toBe(true);
    expect(PINCODE_PATTERN.test("010075")).toBe(false);
    expect(SLUG_PATTERN.test("my-store-1")).toBe(true);
    expect(SLUG_PATTERN.test("My Store")).toBe(false);
    expect(validateIndianMobile("9876543210")).toBeNull();
    expect(validateIndianMobile("+91 9876543210")).toBeNull();
    expect(validateIndianMobile("1234567890")).not.toBeNull();
  });
});

describe("pickup token handling", () => {
  it("strips the SB1: prefix and validates tokens", () => {
    expect(normalisePickupToken("SB1:abcdef123456")).toBe("abcdef123456");
    expect(normalisePickupToken("  abcdef123456  ")).toBe("abcdef123456");
    expect(normalisePickupToken("SB1:ABCDEF")).toBe("abcdef");
    // W5: issued tokens are exactly 64 hex chars
    // (M8); anything shorter or non-hex is refused
    // locally, matching the backend route check.
    expect(isValidPickupToken("b".repeat(64))).toBe(true);
    expect(isValidPickupToken("abcdef123456")).toBe(false);
    expect(isValidPickupToken("short")).toBe(false);
    expect(isValidPickupToken("bad token!")).toBe(false);
  });
});
