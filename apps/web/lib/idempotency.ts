/**
 * Idempotency-key lifecycle (W3, financially important;
 * terminal clearing added in W9.1).
 *
 * Backend rule (M5/M6, verified): the Idempotency-Key
 * header must be 8–128 chars of [A-Za-z0-9_-].
 *
 * - One LOGICAL attempt gets one key, generated once
 *   and stored in sessionStorage for the life of that
 *   attempt. Retries, re-renders, StrictMode double
 *   effects, and network retries all reuse it, so a
 *   retry can never create a second reservation or a
 *   second Razorpay order.
 * - A DELIBERATE new attempt (new cart contents, or a
 *   fresh checkout after the previous attempt was
 *   abandoned) gets a fresh key, because it is a new
 *   logical request.
 * - Keys are never generated on every render and never
 *   stored in localStorage: sessionStorage scopes them
 *   to the tab that started the attempt.
 *
 * W9.1 terminal rule (the bug this fixes): a key scoped
 * to a cart fingerprint used to survive after its order
 * became terminal (completed, expired, cancelled, or
 * refunded). The backend replays the SAME order for the
 * same key + contents — even a terminal one — so the
 * customer could never buy the same items again in the
 * same tab: every fresh checkout replayed the dead
 * order. The fix: when a fresh backend order read
 * proves the attempt is terminal (see
 * isTerminalOrderStatus), the checkout page clears
 * that fingerprint's key, so the next attempt gets a
 * fresh key and a fresh order. A key is NEVER cleared
 * on a failed request, a dismissed payment window, or
 * any other ambiguous state — only on a definite
 * backend status — because clearing mid-attempt would
 * let a retry create a duplicate reservation.
 */
const RESERVATION_PREFIX = "savebite_reservation_key:";
const CHECKOUT_PREFIX = "savebite_checkout_key:";

export function newIdempotencyKey(): string {
  // crypto.randomUUID() without dashes: 32 hex chars,
  // inside the backend's allowed alphabet and length.
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return `key-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;
}

function storedKey(prefix: string, scope: string): string {
  if (typeof sessionStorage === "undefined") return newIdempotencyKey();
  const storageKey = `${prefix}${scope}`;
  const existing = sessionStorage.getItem(storageKey);
  if (existing) return existing;
  const fresh = newIdempotencyKey();
  sessionStorage.setItem(storageKey, fresh);
  return fresh;
}

export function reservationKeyFor(cartFingerprint: string): string {
  return storedKey(RESERVATION_PREFIX, cartFingerprint);
}

export function checkoutKeyFor(orderId: string): string {
  return storedKey(CHECKOUT_PREFIX, orderId);
}

export function clearReservationKey(cartFingerprint: string): void {
  if (typeof sessionStorage !== "undefined") {
    sessionStorage.removeItem(`${RESERVATION_PREFIX}${cartFingerprint}`);
  }
}

/**
 * W9.1: is a backend order status terminal for checkout
 * purposes? Only pending_payment can still be paid. Every
 * other known status — paid (confirmed, ready_for_pickup,
 * collected) or dead (expired, cancelled, refund_pending,
 * refunded) — ends the attempt, so its reservation key
 * must be cleared (see the header comment). Unknown
 * statuses are treated as terminal too: the checkout page
 * already shows them as not-payable, and keeping the key
 * would replay a dead order forever. This decision must
 * only ever be fed by a fresh backend order read, never
 * by a timeout, a failed request, or a local timer.
 */
export function isTerminalOrderStatus(status: string): boolean {
  return status !== "pending_payment";
}
