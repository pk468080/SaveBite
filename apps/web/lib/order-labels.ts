/**
 * Customer-facing labels for order and payment states
 * (W3). Wording follows the backend's own status
 * honesty (M7): pending payment is not paid, captured
 * is not collected, confirmed is not ready for pickup,
 * and reconciliation_required is never shown as a
 * successful purchase.
 */
import type { OrderStatusValue, PaymentStatusValue } from "@savebite/api-client";

export const ORDER_STATUS_LABELS: Record<OrderStatusValue, string> = {
  pending_payment: "Awaiting payment",
  confirmed: "Confirmed",
  ready_for_pickup: "Ready for pickup",
  collected: "Collected",
  expired: "Expired",
  cancelled: "Cancelled",
  refund_pending: "Refund pending",
  refunded: "Refunded",
};

export const PAYMENT_STATUS_LABELS: Record<PaymentStatusValue, string> = {
  created: "Payment not started",
  authorized: "Payment authorised",
  captured: "Payment captured",
  failed: "Payment failed",
  refund_pending: "Refund pending",
  partially_refunded: "Partially refunded",
  refunded: "Refunded",
  reconciliation_required: "Needs verification",
};

export function orderStatusLabel(status: string): string {
  return ORDER_STATUS_LABELS[status as OrderStatusValue] ?? status.replace(/_/g, " ");
}

export function paymentStatusLabel(status: string): string {
  return PAYMENT_STATUS_LABELS[status as PaymentStatusValue] ?? status.replace(/_/g, " ");
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(date);
}

/** Countdown parts from an absolute expiry timestamp.
 * Recomputed from Date.now() on every tick, so tab
 * suspension or throttling cannot drift the display
 * past the real expiry. */
export function countdownParts(expiresAt: string, nowMs: number): {
  expired: boolean;
  minutes: number;
  seconds: number;
  totalSeconds: number;
} {
  const diff = Math.max(0, Math.floor((new Date(expiresAt).getTime() - nowMs) / 1000));
  return {
    expired: diff <= 0,
    minutes: Math.floor(diff / 60),
    seconds: diff % 60,
    totalSeconds: diff,
  };
}
