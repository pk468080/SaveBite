/**
 * Idempotency-key lifecycle (W3, financially important).
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
