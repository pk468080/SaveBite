/**
 * Pickup QR helpers (W5, M8). These mirror the
 * backend contract; they never decide anything
 * the backend does not decide. Token issuance
 * and verification stay server-side: the only
 * thing built here is the QR payload string from
 * a token the backend already issued, plus the
 * eligibility gate that decides whether the
 * "Show Pickup QR" button appears at all. A
 * hidden button is not security — an ineligible
 * order still gets a backend refusal if issuance
 * is attempted.
 */

/** QR payload prefix from the M8 contract. */
export const QR_PAYLOAD_PREFIX = "SB1:";

/** Issued tokens are 32 random bytes, hex-encoded. */
export const QR_TOKEN_PATTERN = /^[0-9a-f]{64}$/;

/**
 * Build the exact QR payload string for a token
 * the backend issued. Accepts a bare token or an
 * already-prefixed payload; the result is always
 * "SB1:<64-hex-token>".
 */
export function buildQrPayload(token: string): string {
  const cleaned = token.trim().toLowerCase();
  const prefix = QR_PAYLOAD_PREFIX.toLowerCase();
  const bare = cleaned.startsWith(prefix) ? cleaned.slice(prefix.length) : cleaned;
  return `${QR_PAYLOAD_PREFIX}${bare}`;
}

/**
 * Parse a scanned QR value. Returns the bare
 * token only when the value is exactly a SaveBite
 * pickup payload ("SB1:" + 64 hex chars);
 * anything else returns null so it is rejected
 * before any backend call. Raw tokens without
 * the prefix are NOT accepted from a scan — a
 * scanned value must be a real QR payload.
 */
export function parseQrPayload(value: string): string | null {
  const cleaned = value.trim().toLowerCase();
  const prefix = QR_PAYLOAD_PREFIX.toLowerCase();
  if (!cleaned.startsWith(prefix)) return null;
  const bare = cleaned.slice(prefix.length);
  return QR_TOKEN_PATTERN.test(bare) ? bare : null;
}

/**
 * Frontend eligibility mirror of the M8 issue
 * rule: the order must be confirmed or ready for
 * pickup AND its payment must be captured. The
 * backend re-checks everything, including the
 * pickup window (issuance is refused after
 * pickup end + 30 minutes), which the frontend
 * deliberately does not gate on — client clocks
 * cannot be trusted for that check.
 */
export function isPickupQrEligible(orderStatus: string, paymentStatus: string): boolean {
  return (
    (orderStatus === "confirmed" || orderStatus === "ready_for_pickup") &&
    paymentStatus === "captured"
  );
}

/**
 * Plain-language reason an order cannot show a
 * pickup QR yet. Never claims a backend reason
 * it has not confirmed; window problems surface
 * as the backend's own message on issuance.
 */
export function pickupIneligibilityReason(orderStatus: string, paymentStatus: string): string {
  if (orderStatus === "collected") {
    return "This order has already been collected, so there is no pickup code for it.";
  }
  if (orderStatus === "cancelled" || orderStatus === "expired") {
    return "This order is no longer eligible for pickup.";
  }
  if (orderStatus === "pending_payment" || paymentStatus !== "captured") {
    return "Pay for this order first. The pickup QR appears once payment is confirmed.";
  }
  return "This order is not ready for pickup yet. The pickup QR appears once it is confirmed.";
}
