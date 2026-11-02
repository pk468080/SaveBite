import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrderDetail } from "@savebite/api-client";
import CheckoutPage from "@/app/customer/checkout/page";
import {
  clearReservationKey,
  isKnownTerminalOrderStatus,
  isTerminalOrderStatus,
  reservationKeyFor,
} from "@/lib/idempotency";

/**
 * W9.1.1 countdown-expiry contract: a local countdown
 * reaching zero is NOT proof the reservation expired.
 * Only a fresh backend re-read decides, and only a
 * KNOWN terminal status may clear the stored reference
 * and key. A still-payable read, a failed read, and an
 * unrecognized status must all preserve both, so the
 * customer keeps a payment retry and no second
 * reservation is ever created for the attempt.
 */

const ACTIVE_RESERVATION_KEY = "savebite_active_reservation";
const RESERVATION_KEY_PREFIX = "savebite_reservation_key:";
const FINGERPRINT = "listing-1:2";
const ORDER_ID = "order-1";

const { mockGetOrder, mockCreateReservation, mockPush, mockClear } = vi.hoisted(() => ({
  mockGetOrder: vi.fn(),
  mockCreateReservation: vi.fn(),
  mockPush: vi.fn(),
  mockClear: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
  useSearchParams: () => ({
    get: (key: string) => (key === "orderId" ? ORDER_ID : null),
  }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/cart/cart-context", () => ({
  // Stable identity: the page's entry effect depends on
  // `clear`, so a fresh function per render would
  // re-run the effect and exhaust the mocked reads.
  useCart: () => ({ cart: null, clear: mockClear }),
}));

vi.mock("@/lib/api/browser", () => ({
  createBrowserApiClient: () => ({}),
}));

vi.mock("@savebite/api-client", () => ({
  ApiError: class ApiError extends Error {},
  createServices: () => ({
    orders: {
      getOrder: mockGetOrder,
      createReservation: mockCreateReservation,
    },
    payments: { checkout: vi.fn(), verifyPayment: vi.fn() },
  }),
}));

function orderDetail(status: string): OrderDetail {
  return {
    id: ORDER_ID,
    order_number: "SB-TEST-1",
    status: status as OrderDetail["status"],
    payment: { status: "created", amount_paid: "0" },
    subtotal_amount: "195.00",
    discount_amount: "0.00",
    platform_fee_amount: "0.00",
    tax_amount: "0.00",
    total_amount: "195.00",
    currency: "INR",
    created_at: "2026-11-01T10:00:00+00:00",
    updated_at: "2026-11-01T10:00:00+00:00",
    store: {
      id: "22222222-2222-4222-8222-222222222222",
      name: "Sharma Foods",
      city: "New Delhi",
      state: "Delhi",
      pincode: "110075",
      address_line_1: "Shop 1",
    },
    pickup_starts_at: "2026-11-01T18:00:00+00:00",
    pickup_ends_at: "2026-11-01T21:00:00+00:00",
    // Already past: the countdown fires on mount.
    reservation_expires_at: "2020-01-01T00:00:00+00:00",
    pickup_available: false,
    items: [
      {
        listing_id: "11111111-1111-4111-8111-111111111111",
        listing_type: "surprise_bag",
        title: "Evening Bakery Bag",
        quantity: 1,
        unit_price: "195.00",
        line_total: "195.00",
        reference_value: "300.00",
        dietary_classification: "vegetarian",
        allergen_codes: [],
      },
    ],
    timeline: [],
  };
}

function seedAttempt() {
  sessionStorage.setItem(
    ACTIVE_RESERVATION_KEY,
    JSON.stringify({ orderId: ORDER_ID, fingerprint: FINGERPRINT }),
  );
  sessionStorage.setItem(`${RESERVATION_KEY_PREFIX}${FINGERPRINT}`, "key-abc-12345");
}

describe("isKnownTerminalOrderStatus (W9.1.1)", () => {
  it("is true only for the seven known terminal statuses", () => {
    for (const status of [
      "confirmed",
      "ready_for_pickup",
      "collected",
      "expired",
      "cancelled",
      "refund_pending",
      "refunded",
    ]) {
      expect(isKnownTerminalOrderStatus(status)).toBe(true);
    }
  });

  it("is false for pending_payment and for unrecognized statuses", () => {
    expect(isKnownTerminalOrderStatus("pending_payment")).toBe(false);
    expect(isKnownTerminalOrderStatus("mystery_status")).toBe(false);
    expect(isKnownTerminalOrderStatus("")).toBe(false);
  });

  it("differs from isTerminalOrderStatus exactly on unknown statuses", () => {
    // Display rule (unchanged from W9.1): unknown shows
    // as not-payable. Clearing rule (W9.1.1): unknown
    // must NOT clear. The two helpers encode the split.
    expect(isTerminalOrderStatus("mystery_status")).toBe(true);
    expect(isKnownTerminalOrderStatus("mystery_status")).toBe(false);
  });
});

describe("checkout countdown expiry (W9.1.1)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
    seedAttempt();
  });

  afterEach(() => cleanup());

  it("early client countdown with a still-payable backend order preserves reference and key", async () => {
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    render(<CheckoutPage />);

    // Payment stays retryable; the timer ran early.
    await screen.findByRole("button", { name: "Pay with Razorpay" });
    expect(await screen.findByText(/timer ran out early/i)).toBeVisible();
    expect(sessionStorage.getItem(ACTIVE_RESERVATION_KEY)).not.toBeNull();
    expect(sessionStorage.getItem(`${RESERVATION_KEY_PREFIX}${FINGERPRINT}`)).toBe(
      "key-abc-12345",
    );
    expect(reservationKeyFor(FINGERPRINT)).toBe("key-abc-12345");
    expect(mockCreateReservation).not.toHaveBeenCalled();
  });

  it("backend read failure at countdown expiry preserves reference and key and offers a retry", async () => {
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    mockGetOrder.mockRejectedValueOnce(new Error("Network down"));
    render(<CheckoutPage />);

    await screen.findByText(/could not confirm your reservation status/i);
    expect(sessionStorage.getItem(ACTIVE_RESERVATION_KEY)).not.toBeNull();
    expect(sessionStorage.getItem(`${RESERVATION_KEY_PREFIX}${FINGERPRINT}`)).toBe(
      "key-abc-12345",
    );

    // Retry the state refresh: the order is still
    // payable, the same key is reused, and no second
    // reservation is created.
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    fireEvent.click(await screen.findByRole("button", { name: "Retry status check" }));
    await screen.findByRole("button", { name: "Pay with Razorpay" });
    expect(sessionStorage.getItem(ACTIVE_RESERVATION_KEY)).not.toBeNull();
    expect(reservationKeyFor(FINGERPRINT)).toBe("key-abc-12345");
    expect(mockCreateReservation).not.toHaveBeenCalled();
  });

  it("confirmed terminal order (expired) clears reference and key", async () => {
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    mockGetOrder.mockResolvedValueOnce(orderDetail("expired"));
    render(<CheckoutPage />);

    await screen.findByText(/this reservation has expired/i);
    expect(sessionStorage.getItem(ACTIVE_RESERVATION_KEY)).toBeNull();
    expect(sessionStorage.getItem(`${RESERVATION_KEY_PREFIX}${FINGERPRINT}`)).toBeNull();
    expect(mockCreateReservation).not.toHaveBeenCalled();
  });

  it("confirmed terminal order (confirmed) shows not-payable and clears reference and key", async () => {
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    mockGetOrder.mockResolvedValueOnce(orderDetail("confirmed"));
    render(<CheckoutPage />);

    await screen.findByText(/can no longer be paid here/i);
    expect(sessionStorage.getItem(ACTIVE_RESERVATION_KEY)).toBeNull();
    expect(sessionStorage.getItem(`${RESERVATION_KEY_PREFIX}${FINGERPRINT}`)).toBeNull();
    expect(screen.queryByRole("button", { name: "Pay with Razorpay" })).toBeNull();
  });

  it("unrecognized backend status fails closed: not-payable, but reference and key preserved", async () => {
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    mockGetOrder.mockResolvedValueOnce(orderDetail("mystery_status"));
    render(<CheckoutPage />);

    await screen.findByText(/can no longer be paid here/i);
    expect(screen.queryByRole("button", { name: "Pay with Razorpay" })).toBeNull();
    // Fail closed means no silent clear on a status
    // this client does not recognize.
    expect(sessionStorage.getItem(ACTIVE_RESERVATION_KEY)).not.toBeNull();
    expect(sessionStorage.getItem(`${RESERVATION_KEY_PREFIX}${FINGERPRINT}`)).toBe(
      "key-abc-12345",
    );
    expect(mockCreateReservation).not.toHaveBeenCalled();
  });

  it("same reservation key survives repeated still-payable re-reads", async () => {
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    mockGetOrder.mockResolvedValueOnce(orderDetail("pending_payment"));
    render(<CheckoutPage />);
    await screen.findByRole("button", { name: "Pay with Razorpay" });
    const first = reservationKeyFor(FINGERPRINT);
    expect(first).toBe("key-abc-12345");
    // A later refresh replays the same attempt: the
    // key object is identical, and clearing one
    // fingerprint never touches another.
    clearReservationKey("other-fingerprint");
    expect(reservationKeyFor(FINGERPRINT)).toBe(first);
  });
});
