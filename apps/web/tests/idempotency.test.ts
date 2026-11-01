import { beforeEach, describe, expect, it } from "vitest";
import {
  checkoutKeyFor,
  newIdempotencyKey,
  reservationKeyFor,
} from "@/lib/idempotency";

/**
 * B1 retry contract: the checkout idempotency key must be
 * stable for one order in one tab, so a retry after a
 * dismissed modal re-sends the SAME key and the backend
 * can re-issue the original Razorpay order instead of
 * creating a second one. A new tab (cleared session) is a
 * new logical attempt and gets a fresh key.
 */
describe("idempotency keys", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("checkoutKeyFor is stable for the same order across calls", () => {
    const first = checkoutKeyFor("order-1");
    const second = checkoutKeyFor("order-1");
    expect(first).toBe(second);
    expect(first.length).toBeGreaterThanOrEqual(8);
  });

  it("checkoutKeyFor differs per order", () => {
    expect(checkoutKeyFor("order-1")).not.toBe(checkoutKeyFor("order-2"));
  });

  it("reservationKeyFor is stable for the same cart fingerprint", () => {
    expect(reservationKeyFor("listing-1:2")).toBe(
      reservationKeyFor("listing-1:2"),
    );
  });

  it("a cleared session (new tab) gets a fresh checkout key", () => {
    const first = checkoutKeyFor("order-1");
    sessionStorage.clear();
    const second = checkoutKeyFor("order-1");
    expect(second).not.toBe(first);
  });

  it("newIdempotencyKey matches the backend alphabet and length", () => {
    for (let i = 0; i < 20; i++) {
      expect(newIdempotencyKey()).toMatch(/^[A-Za-z0-9_-]{8,128}$/);
    }
  });
});
