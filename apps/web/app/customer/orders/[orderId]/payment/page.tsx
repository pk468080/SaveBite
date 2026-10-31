"use client";

import { ApiError, createServices } from "@savebite/api-client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR, formatPickupWindow } from "@/lib/marketplace";
import { formatDateTime } from "@/lib/order-labels";
import type { OrderDetail } from "@savebite/api-client";

/**
 * Payment result (W3). State comes ONLY from the
 * backend order detail, re-read on every visit:
 *  - captured + confirmed/ready_for_pickup → success.
 *  - pending_payment → still open, retry offered.
 *  - failed → failed, retry offered.
 *  - reconciliation_required → NEUTRAL verification
 *    message: never success, never a refund promise.
 *  - expired/cancelled → what happened, no retry.
 * The Razorpay callback alone never decides this page.
 */
export default function PaymentResultPage() {
  const params = useParams();
  const orderId = String(params.orderId);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const services = createServices(createBrowserApiClient());
        const detail = await services.orders.getOrder(orderId);
        if (!cancelled) setOrder(detail);
      } catch (caught) {
        if (!cancelled) {
          setError(
            caught instanceof ApiError
              ? caught.message
              : "Could not load this order. Please try again.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  if (loading) return <LoadingState label="Checking your payment with the backend…" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!order) return <Alert variant="error">Order not found.</Alert>;

  const payment = order.payment.status;
  const success =
    payment === "captured" && (order.status === "confirmed" || order.status === "ready_for_pickup");
  const retryable = order.status === "pending_payment" || payment === "failed";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">
          {success
            ? "Payment confirmed"
            : payment === "reconciliation_required"
              ? "Payment needs verification"
              : order.status === "expired"
                ? "Reservation expired"
                : order.status === "cancelled"
                  ? "Order cancelled"
                  : payment === "failed"
                    ? "Payment failed"
                    : "Payment pending"}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">Order {order.order_number}</p>
      </div>

      {success ? (
        <Alert variant="success">
          Your payment of {formatINR(order.payment.amount_paid, order.currency)} was captured and
          the backend confirmed your order. Collect it at the store during the pickup window below.
        </Alert>
      ) : payment === "reconciliation_required" ? (
        <Alert variant="info">
          Your payment needs verification before this order can be confirmed. Nothing has been
          promised as a purchase yet, and no refund has been promised either. Check your order
          details again shortly — the backend updates the status once verification completes.
        </Alert>
      ) : order.status === "expired" ? (
        <Alert variant="error">
          This reservation expired before payment was confirmed. If money was captured, the order
          status here will reflect it; otherwise, start a fresh reservation from the marketplace.
        </Alert>
      ) : order.status === "cancelled" ? (
        <Alert variant="error">This order was cancelled and cannot be paid.</Alert>
      ) : payment === "failed" ? (
        <Alert variant="error">
          The payment failed and no money was confirmed as captured. You can try again while the
          reservation is still open.
        </Alert>
      ) : (
        <Alert variant="info">
          Payment is still pending for this order. If you just paid, wait a moment and refresh —
          the backend state shown here is authoritative.
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Order summary</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p className="flex justify-between">
            <span className="text-muted-foreground">Store</span>
            <span className="font-medium">{order.store.name}</span>
          </p>
          <p className="flex justify-between">
            <span className="text-muted-foreground">Total</span>
            <span className="font-medium">{formatINR(order.total_amount, order.currency)}</span>
          </p>
          {order.payment.paid_at ? (
            <p className="flex justify-between">
              <span className="text-muted-foreground">Paid at</span>
              <span className="font-medium">{formatDateTime(order.payment.paid_at)}</span>
            </p>
          ) : null}
          <p className="flex justify-between gap-4">
            <span className="text-muted-foreground">Pickup window</span>
            <span className="text-right font-medium">
              {formatPickupWindow(order.pickup_starts_at, order.pickup_ends_at, "Asia/Kolkata")}
            </span>
          </p>
          <p className="text-muted-foreground">
            {order.store.address_line_1}
            {order.store.address_line_2 ? `, ${order.store.address_line_2}` : ""}
            {order.store.locality ? `, ${order.store.locality}` : ""}, {order.store.city},{" "}
            {order.store.state} {order.store.pincode}
          </p>
          {order.store.pickup_instructions ? (
            <p className="text-muted-foreground">Pickup instructions: {order.store.pickup_instructions}</p>
          ) : null}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        {retryable ? (
          <Button asChild>
            <Link href={`/customer/checkout?orderId=${order.id}`}>Try payment again</Link>
          </Button>
        ) : null}
        <Button asChild variant="outline">
          <Link href={`/customer/orders/${order.id}`}>View order details</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/customer/orders">Order history</Link>
        </Button>
      </div>
    </div>
  );
}
