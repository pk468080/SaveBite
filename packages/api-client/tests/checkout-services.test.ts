import { describe, expect, it, vi } from "vitest";
import { ApiClient, createServices } from "../src";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * W3 service contract checks: reservation body shape
 * (M5), checkout idempotency header (M6), and the
 * verify request shape. The backend is authoritative;
 * these tests pin the frontend to its real contract.
 */
describe("W3 checkout services", () => {
  it("sends store_id + items and the idempotency key for reservations", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(201, {
        order_id: "order-1",
        order_number: "SB-1",
        status: "pending_payment",
        total_amount: "198.00",
        currency: "INR",
        reservation_expires_at: "2026-10-31T12:05:00Z",
        pickup_starts_at: "2026-10-31T18:00:00Z",
        pickup_ends_at: "2026-10-31T21:00:00Z",
        idempotent_replay: false,
      }),
    );
    const services = createServices(
      new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchImpl as unknown as typeof fetch }),
    );
    await services.orders.createReservation(
      { store_id: "store-1", items: [{ listing_id: "listing-1", quantity: 2 }] },
      "reservation-key-123",
    );
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      store_id: "store-1",
      items: [{ listing_id: "listing-1", quantity: 2 }],
    });
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("reservation-key-123");
  });

  it("sends the idempotency key for checkout and the callback fields for verify", async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.includes("/checkout")) {
        return jsonResponse(201, {
          order_id: "order-1",
          payment_transaction_id: "txn-1",
          key_id: "rzp_test_public",
          razorpay_order_id: "order_rzp_1",
          amount_paise: 19800,
          currency: "INR",
          prefill_email: "buyer@example.com",
        });
      }
      return jsonResponse(200, {
        order_id: "order-1",
        payment_transaction_id: "txn-1",
        razorpay_payment_id: "pay_1",
        verified: true,
        amount_paise: 19800,
        currency: "INR",
      });
    });
    const services = createServices(
      new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchImpl as unknown as typeof fetch }),
    );
    const checkout = await services.payments.checkout("order-1", "checkout-key-456");
    expect(checkout.key_id).toBe("rzp_test_public");
    expect(checkout.amount_paise).toBe(19800);
    const [, checkoutInit] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect((checkoutInit.headers as Record<string, string>)["Idempotency-Key"]).toBe("checkout-key-456");
    const verified = await services.payments.verifyPayment({
      razorpay_order_id: "order_rzp_1",
      razorpay_payment_id: "pay_1",
      razorpay_signature: "sig_1",
    });
    expect(verified.verified).toBe(true);
    const [, verifyInit] = fetchImpl.mock.calls[1] as unknown as [string, RequestInit];
    expect(JSON.parse(String(verifyInit.body))).toEqual({
      razorpay_order_id: "order_rzp_1",
      razorpay_payment_id: "pay_1",
      razorpay_signature: "sig_1",
    });
  });

  it("lists orders with status and payment filters", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { items: [], total: 0, page: 1, page_size: 20 }),
    );
    const services = createServices(
      new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchImpl as unknown as typeof fetch }),
    );
    await services.orders.listOrders({ status: "confirmed", payment_status: "captured", page: 2 });
    const [url] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("status=confirmed");
    expect(url).toContain("payment_status=captured");
    expect(url).toContain("page=2");
  });
});

/**
 * B1 retry contract: a retry re-sends the SAME idempotency
 * key, the backend re-issues the original gateway order,
 * and verification still requires the backend call — the
 * callback alone never confirms payment.
 */
describe("B1 checkout retry", () => {
  it("retry sends the same idempotency key and reuses the returned order id", async () => {
    const fetchImpl = vi.fn(async (url: string) => {
      if (url.includes("/checkout")) {
        return jsonResponse(201, {
          order_id: "order-1",
          payment_transaction_id: "txn-1",
          key_id: "rzp_test_public",
          razorpay_order_id: "order_rzp_reused",
          amount_paise: 19800,
          currency: "INR",
          prefill_email: "buyer@example.com",
        });
      }
      return jsonResponse(200, {
        order_id: "order-1",
        payment_transaction_id: "txn-1",
        razorpay_payment_id: "pay_1",
        verified: true,
        amount_paise: 19800,
        currency: "INR",
      });
    });
    const services = createServices(
      new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchImpl as unknown as typeof fetch }),
    );
    const first = await services.payments.checkout("order-1", "checkout-key-789");
    const second = await services.payments.checkout("order-1", "checkout-key-789");
    expect(first.razorpay_order_id).toBe("order_rzp_reused");
    expect(second.razorpay_order_id).toBe("order_rzp_reused");
    const keys = fetchImpl.mock.calls
      .slice(0, 2)
      .map(
        ([, init]) =>
          (init.headers as Record<string, string>)["Idempotency-Key"],
      );
    expect(keys).toEqual(["checkout-key-789", "checkout-key-789"]);
    // Verification still goes through the backend and sends
    // no idempotency key of its own.
    await services.payments.verifyPayment({
      razorpay_order_id: "order_rzp_reused",
      razorpay_payment_id: "pay_1",
      razorpay_signature: "sig_1",
    });
    const [, verifyInit] = fetchImpl.mock.calls[2] as unknown as [string, RequestInit];
    expect(
      (verifyInit.headers as Record<string, string>)["Idempotency-Key"],
    ).toBeUndefined();
  });
});
