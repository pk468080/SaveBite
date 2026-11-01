import { beforeEach, describe, expect, it } from "vitest";
import {
  clearReservationKey,
  isTerminalOrderStatus,
  reservationKeyFor,
} from "@/lib/idempotency";

/**
 * W9.1 reservation-key lifecycle: a fingerprint-scoped
 * key must survive retries of the same attempt but must
 * never survive the attempt itself. The backend replays
 * the SAME order for the same key + contents — even a
 * terminal one — so a key left behind after completion
 * or expiry would poison every later same-contents
 * checkout in the tab. Clearing is safe only after a
 * definite terminal backend status; these tests prove
 * the storage mechanics the checkout page relies on.
 */
describe("reservation key lifecycle (W9.1)", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("same fingerprint reuses the key while the attempt is active", () => {
    const first = reservationKeyFor("listing-1:2");
    expect(reservationKeyFor("listing-1:2")).toBe(first);
  });

  it("clearing a fingerprint's key makes the next attempt get a fresh key", () => {
    const first = reservationKeyFor("listing-1:2");
    clearReservationKey("listing-1:2");
    const second = reservationKeyFor("listing-1:2");
    expect(second).not.toBe(first);
    expect(second).toMatch(/^[A-Za-z0-9_-]{8,128}$/);
  });

  it("clearing one fingerprint leaves other fingerprints' keys alone", () => {
    const other = reservationKeyFor("listing-2:1");
    clearReservationKey("listing-1:2");
    expect(reservationKeyFor("listing-2:1")).toBe(other);
  });

  it("clearing a never-stored fingerprint is a no-op", () => {
    expect(() => clearReservationKey("listing-9:9")).not.toThrow();
    expect(reservationKeyFor("listing-9:9")).toMatch(
      /^[A-Za-z0-9_-]{8,128}$/,
    );
  });

  it("pending_payment is the only non-terminal status", () => {
    expect(isTerminalOrderStatus("pending_payment")).toBe(false);
  });

  it("paid and dead statuses are terminal", () => {
    for (const status of [
      "confirmed",
      "ready_for_pickup",
      "collected",
      "expired",
      "cancelled",
      "refund_pending",
      "refunded",
    ]) {
      expect(isTerminalOrderStatus(status)).toBe(true);
    }
  });

  it("unknown statuses are treated as terminal, never replayed", () => {
    // The page already shows unknown non-pending statuses
    // as not-payable; keeping the key would replay a dead
    // order forever. Only a fresh backend read may feed
    // this decision — never a timeout or failed request.
    expect(isTerminalOrderStatus("mystery_status")).toBe(true);
  });

  it("full lifecycle: stable, then fresh after terminal clear", () => {
    const attempt = reservationKeyFor("listing-1:2");
    expect(reservationKeyFor("listing-1:2")).toBe(attempt);
    // Simulate the checkout page learning the order is
    // terminal from a fresh backend read, then the
    // customer buying the same items again in this tab.
    expect(isTerminalOrderStatus("expired")).toBe(true);
    clearReservationKey("listing-1:2");
    const nextAttempt = reservationKeyFor("listing-1:2");
    expect(nextAttempt).not.toBe(attempt);
    expect(reservationKeyFor("listing-1:2")).toBe(nextAttempt);
  });
});
