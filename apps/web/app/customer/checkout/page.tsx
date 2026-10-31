"use client";

import { ApiError, createServices } from "@savebite/api-client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useCart } from "@/components/cart/cart-context";
import { ReservationCountdown } from "@/components/checkout/reservation-countdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { cartFingerprint } from "@/lib/cart";
import { checkoutKeyFor, reservationKeyFor } from "@/lib/idempotency";
import { formatINR, formatPickupWindow } from "@/lib/marketplace";
import { orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";
import { loadRazorpayScript, openRazorpayCheckout } from "@/lib/razorpay";
import type { OrderDetail, ReservationResponse } from "@savebite/api-client";

const ACTIVE_RESERVATION_KEY = "savebite_active_reservation";

/**
 * Checkout (W3). Two entry modes:
 *  1. From the cart: one reservation is created for the
 *     cart's single-store items, then Razorpay Checkout
 *     is opened with the BACKEND's order, amount, and
 *     public key. The cart is cleared once the backend
 *     confirms the reservation, so a second reservation
 *     cannot be created from the same cart by accident;
 *     the reservation reference lives in sessionStorage
 *     so a refresh recovers it.
 *  2. ?orderId=: pay an existing pending_payment order
 *     (retry after a dismissed or failed attempt). No
 *     second order is ever created for a retry.
 *
 * Payment is NEVER shown as successful from the
 * Razorpay callback alone: the callback fields go to
 * POST /v1/payments/verify, then the order detail is
 * re-read, and only the backend's stored state decides
 * what the customer sees.
 */
type Phase =
  | "loading"
  | "no-cart"
  | "reserving"
  | "reserved"
  | "paying"
  | "verifying"
  | "error"
  | "expired"
  | "not-payable";

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong. Please try again.";
}

function CheckoutFlow() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const orderIdParam = searchParams.get("orderId");
  const { cart, clear } = useCart();
  const [cartReady, setCartReady] = useState(false);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reservation, setReservation] = useState<ReservationResponse | null>(null);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [cartSnapshot, setCartSnapshot] = useState<{ title: string; quantity: number }[]>([]);
  const attemptRef = useRef<string | null>(null);
  const servicesRef = useRef<ReturnType<typeof createServices> | null>(null);

  const services = useCallback(() => {
    servicesRef.current ??= createServices(createBrowserApiClient());
    return servicesRef.current;
  }, []);

  const refreshOrder = useCallback(
    async (orderId: string) => {
      const detail = await services().orders.getOrder(orderId);
      setOrder(detail);
      return detail;
    },
    [services],
  );

  // Cart is hydrated from localStorage by the provider;
  // wait one tick so an empty first render is not
  // mistaken for "no cart".
  useEffect(() => {
    const timer = setTimeout(() => setCartReady(true), 0);
    return () => clearTimeout(timer);
  }, []);

  // Entry: existing order, or create one reservation.
  useEffect(() => {
    if (!cartReady) return;
    if (orderIdParam) {
      (async () => {
        try {
          const detail = await refreshOrder(orderIdParam);
          if (detail.status === "pending_payment") {
            setPhase("reserved");
          } else {
            setPhase("not-payable");
          }
        } catch (caught) {
          setError(errorMessage(caught));
          setPhase("error");
        }
      })();
      return;
    }
    if (!cart || cart.items.length === 0) {
      // A stored reservation survives a refresh even
      // though the cart was cleared at creation time.
      const stored = sessionStorage.getItem(ACTIVE_RESERVATION_KEY);
      if (stored) {
        try {
          const parsed = JSON.parse(stored) as { orderId: string };
          void refreshOrder(parsed.orderId).then((detail) => {
            setPhase(detail.status === "pending_payment" ? "reserved" : "not-payable");
          });
          return;
        } catch {
          sessionStorage.removeItem(ACTIVE_RESERVATION_KEY);
        }
      }
      setPhase("no-cart");
      return;
    }
    const fingerprint = cartFingerprint(cart);
    if (attemptRef.current === fingerprint) return;
    attemptRef.current = fingerprint;
    const stored = sessionStorage.getItem(ACTIVE_RESERVATION_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as { orderId: string; fingerprint: string };
        if (parsed.fingerprint === fingerprint) {
          void refreshOrder(parsed.orderId).then((detail) => {
            setPhase(detail.status === "pending_payment" ? "reserved" : "not-payable");
          });
          return;
        }
      } catch {
        sessionStorage.removeItem(ACTIVE_RESERVATION_KEY);
      }
    }
    setPhase("reserving");
    const snapshot = cart.items.map((item) => ({ title: item.title, quantity: item.quantity }));
    services()
      .orders.createReservation(
        {
          store_id: cart.storeId,
          items: cart.items.map((item) => ({ listing_id: item.listingId, quantity: item.quantity })),
        },
        reservationKeyFor(fingerprint),
      )
      .then((created) => {
        setReservation(created);
        setCartSnapshot(snapshot);
        sessionStorage.setItem(
          ACTIVE_RESERVATION_KEY,
          JSON.stringify({ orderId: created.order_id, fingerprint }),
        );
        clear();
        // A replay carries no expiry: the order detail
        // is authoritative, so always re-read it.
        return refreshOrder(created.order_id).then((detail) => {
          setPhase(detail.status === "pending_payment" ? "reserved" : "not-payable");
        });
      })
      .catch((caught: unknown) => {
        setError(errorMessage(caught));
        setPhase("error");
      });
  }, [cartReady, cart, orderIdParam, refreshOrder, services, clear]);

  const handleExpire = useCallback(() => {
    const id = order?.id ?? reservation?.order_id;
    if (!id) return;
    sessionStorage.removeItem(ACTIVE_RESERVATION_KEY);
    void refreshOrder(id).then(() => setPhase("expired"));
  }, [order, reservation, refreshOrder]);

  async function handlePay() {
    const id = order?.id ?? reservation?.order_id;
    if (!id) return;
    setError(null);
    setNotice(null);
    setPhase("paying");
    try {
      const checkout = await services().payments.checkout(id, checkoutKeyFor(id));
      await loadRazorpayScript();
      openRazorpayCheckout({
        key: checkout.key_id,
        order_id: checkout.razorpay_order_id,
        // Server-provided amount only. The frontend
        // never calculates or chooses the amount.
        amount: checkout.amount_paise,
        currency: checkout.currency,
        name: "SaveBite",
        description: `Order ${order?.order_number ?? reservation?.order_number ?? ""}`,
        prefill: checkout.prefill_email ? { email: checkout.prefill_email } : undefined,
        theme: { color: "#15803d" },
        handler: (response) => {
          setPhase("verifying");
          services()
            .payments.verifyPayment({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            })
            .then(() => refreshOrder(id))
            .then(() => {
              sessionStorage.removeItem(ACTIVE_RESERVATION_KEY);
              router.push(`/customer/orders/${id}/payment`);
            })
            .catch((caught: unknown) => {
              // Verification failed: the order state is
              // still authoritative — never show success.
              setError(
                `${errorMessage(caught)} Your order status has not been changed by this error. Check the order below.`,
              );
              setPhase("reserved");
            });
        },
        modal: {
          ondismiss: () => {
            // A closed window proves nothing: re-read
            // the backend state before saying anything.
            void refreshOrder(id).then((detail) => {
              if (detail.payment.status === "captured") {
                router.push(`/customer/orders/${id}/payment`);
              } else {
                setNotice(
                  "Payment was not completed. Your reservation is still open while its timer runs — you can try again below.",
                );
                setPhase("reserved");
              }
            });
          },
        },
      });
    } catch (caught) {
      setError(errorMessage(caught));
      setPhase("reserved");
    }
  }

  if (phase === "loading" || phase === "reserving") {
    return <LoadingState label={phase === "reserving" ? "Creating your reservation…" : "Loading checkout…"} />;
  }

  if (phase === "no-cart") {
    return (
      <EmptyState
        title="Nothing to check out"
        description="Your cart is empty. Add food from the marketplace first."
        >
        <Button asChild><Link href="/marketplace">Explore food</Link></Button>
      </EmptyState>
    );
  }

  if (phase === "error") {
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="error">{error ?? "Checkout could not be started."}</Alert>
        <p className="text-sm text-muted-foreground">
          No payment was taken by this error. If items became unavailable or the
          reservation expired, review your cart and try again.
        </p>
        <div className="flex gap-2">
          <Button asChild variant="outline"><Link href="/cart">Back to cart</Link></Button>
          <Button asChild variant="outline"><Link href="/customer/orders">My orders</Link></Button>
        </div>
      </div>
    );
  }

  if (phase === "not-payable" && order) {
    return (
      <div className="flex flex-col gap-4">
        <Alert variant="info">
          This order is {orderStatusLabel(order.status)} with payment{" "}
          {paymentStatusLabel(order.payment.status)} — it can no longer be paid here.
        </Alert>
        <Button asChild><Link href={`/customer/orders/${order.id}`}>View order details</Link></Button>
      </div>
    );
  }

  if (!order && !reservation) {
    return <LoadingState label="Loading checkout…" />;
  }

  const orderNumber = order?.order_number ?? reservation?.order_number ?? "";
  const total = order?.total_amount ?? reservation?.total_amount ?? "0";
  const currency = order?.currency ?? reservation?.currency ?? "INR";
  const expiresAt = order?.reservation_expires_at ?? reservation?.reservation_expires_at ?? null;
  const storeName = order?.store.name ?? "";
  const items = order
    ? order.items.map((item) => ({ title: item.title, quantity: item.quantity }))
    : cartSnapshot;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Checkout</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Order {orderNumber} · {storeName ? `${storeName} · ` : ""}Pickup only — no delivery.
        </p>
      </div>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {notice ? <Alert variant="info">{notice}</Alert> : null}

      {phase === "expired" ? (
        <Alert variant="error">
          This reservation has expired. The backend state is shown below — if payment
          was captured before expiry, the order page will say so. Otherwise, add the
          items to your cart again to start a fresh reservation.
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Reservation summary</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ul className="flex flex-col gap-1 text-sm">
            {items.map((item, index) => (
              <li key={`${item.title}-${index}`} className="flex justify-between gap-4">
                <span>{item.title}</span>
                <span className="text-muted-foreground">× {item.quantity}</span>
              </li>
            ))}
          </ul>
          <p className="flex justify-between border-t pt-3 font-semibold">
            <span>Total (from the backend)</span>
            <span>{formatINR(total, currency)}</span>
          </p>
          {order ? (
            <p className="text-sm text-muted-foreground">
              Pickup window: {formatPickupWindow(order.pickup_starts_at, order.pickup_ends_at, "Asia/Kolkata")}
            </p>
          ) : reservation ? (
            <p className="text-sm text-muted-foreground">
              Pickup window: {formatPickupWindow(reservation.pickup_starts_at, reservation.pickup_ends_at, "Asia/Kolkata")}
            </p>
          ) : null}
          {phase === "reserved" && expiresAt ? (
            <ReservationCountdown expiresAt={expiresAt} onExpire={handleExpire} />
          ) : phase === "reserved" && !expiresAt ? (
            <p className="text-sm text-muted-foreground">
              Reservation confirmed. If the timer is not shown, refresh this page —
              the backend holds the authoritative expiry.
            </p>
          ) : null}
        </CardContent>
      </Card>

      {phase === "reserved" ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={handlePay}>Pay with Razorpay</Button>
          <Button asChild variant="outline">
            <Link href={`/customer/orders/${order?.id ?? reservation?.order_id}`}>View order</Link>
          </Button>
        </div>
      ) : phase === "paying" || phase === "verifying" ? (
        <LoadingState label={phase === "verifying" ? "Verifying your payment with the backend…" : "Opening the payment window…"} />
      ) : null}

      <p className="text-xs text-muted-foreground">
        Payments are processed by Razorpay. SaveBite never sees your card details, and
        the backend verifies every payment independently before confirming an order.
      </p>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading checkout…" />}>
      <CheckoutFlow />
    </Suspense>
  );
}
