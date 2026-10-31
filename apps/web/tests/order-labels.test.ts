import { describe, expect, it } from "vitest";
import { countdownParts, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

describe("order labels and countdown", () => {
  it("never presents pending payment as paid, or confirmed as ready", () => {
    expect(orderStatusLabel("pending_payment")).toBe("Awaiting payment");
    expect(orderStatusLabel("confirmed")).toBe("Confirmed");
    expect(orderStatusLabel("ready_for_pickup")).toBe("Ready for pickup");
    expect(orderStatusLabel("collected")).toBe("Collected");
    expect(paymentStatusLabel("captured")).toBe("Payment captured");
    expect(paymentStatusLabel("reconciliation_required")).toBe("Needs verification");
  });

  it("counts down from the absolute expiry, not from page load", () => {
    const expiresAt = "2026-10-31T12:05:00.000Z";
    const now = new Date("2026-10-31T12:03:30.000Z").getTime();
    const parts = countdownParts(expiresAt, now);
    expect(parts).toMatchObject({ expired: false, minutes: 1, seconds: 30 });
    const past = countdownParts(expiresAt, new Date("2026-10-31T12:05:00.000Z").getTime());
    expect(past.expired).toBe(true);
    expect(past.totalSeconds).toBe(0);
  });
});
