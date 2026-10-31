import { describe, expect, it } from "vitest";
import {
  buildQrPayload,
  isPickupQrEligible,
  parseQrPayload,
  pickupIneligibilityReason,
} from "@/lib/pickup";

const TOKEN = "b".repeat(64);

describe("pickup QR payload", () => {
  it("builds the documented SB1: payload from a bare token", () => {
    expect(buildQrPayload(TOKEN)).toBe(`SB1:${TOKEN}`);
  });

  it("builds the same payload from an already-prefixed or uppercase value", () => {
    expect(buildQrPayload(`SB1:${TOKEN.toUpperCase()}`)).toBe(`SB1:${TOKEN}`);
  });

  it("parses a valid scanned payload back to the bare token", () => {
    expect(parseQrPayload(`SB1:${TOKEN}`)).toBe(TOKEN);
  });

  it("rejects scanned values that are not SaveBite QR payloads", () => {
    expect(parseQrPayload(TOKEN)).toBeNull();
    expect(parseQrPayload(`SB1:short`)).toBeNull();
    expect(parseQrPayload(`SB1:${"g".repeat(64)}`)).toBeNull();
    expect(parseQrPayload("https://example.com/menu")).toBeNull();
    expect(parseQrPayload("")).toBeNull();
  });
});

describe("pickup QR eligibility", () => {
  it("allows confirmed and ready_for_pickup orders with captured payment", () => {
    expect(isPickupQrEligible("confirmed", "captured")).toBe(true);
    expect(isPickupQrEligible("ready_for_pickup", "captured")).toBe(true);
  });

  it("blocks pending, unpaid, collected, cancelled and expired orders", () => {
    expect(isPickupQrEligible("pending_payment", "created")).toBe(false);
    expect(isPickupQrEligible("confirmed", "created")).toBe(false);
    expect(isPickupQrEligible("confirmed", "failed")).toBe(false);
    expect(isPickupQrEligible("collected", "captured")).toBe(false);
    expect(isPickupQrEligible("cancelled", "captured")).toBe(false);
    expect(isPickupQrEligible("expired", "captured")).toBe(false);
  });

  it("explains each ineligible state in plain language", () => {
    expect(pickupIneligibilityReason("collected", "captured")).toMatch(/already been collected/);
    expect(pickupIneligibilityReason("cancelled", "captured")).toMatch(/no longer eligible/);
    expect(pickupIneligibilityReason("pending_payment", "created")).toMatch(/Pay for this order/);
    expect(pickupIneligibilityReason("confirmed", "created")).toMatch(/Pay for this order/);
  });
});
