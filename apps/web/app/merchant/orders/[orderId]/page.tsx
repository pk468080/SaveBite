"use client";

import { createServices, type OrderDetail } from "@savebite/api-client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/merchant/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

/**
 * Merchant order detail (W4, M7). Item prices
 * are the order-time snapshots, never live
 * listing prices. The timeline shows only real
 * recorded events. Customer personal data is
 * absent by design — the merchant order API
 * excludes customer id, email, phone and
 * address — so this page shows none of it, and
 * the customer note only when the backend
 * returns one. No status can be changed here.
 */
export default function MerchantOrderDetailPage({ params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = use(params);
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    createServices(createBrowserApiClient())
      .orders.getMerchantOrder(orderId)
      .then((data) => {
        if (!cancelled) setOrder(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  if (loading) return <LoadingState label="Loading order" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!order) {
    return (
      <EmptyState
        title="Order not found"
        description="This order does not exist or is not for one of your authorized stores."
      >
        <Button asChild>
          <Link href="/merchant/orders">Back to orders</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Order {order.order_number}</h1>
        <p className="text-sm text-muted-foreground">
          Placed {formatDateTime(order.created_at)} · Store {order.store.name}
        </p>
        <div className="mt-2 flex gap-2">
          <StatusBadge status={order.status} label={orderStatusLabel(order.status)} />
          <StatusBadge status={order.payment.status} label={paymentStatusLabel(order.payment.status)} />
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Items (order-time prices)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          {order.items.map((item) => (
            <div key={item.listing_id} className="flex justify-between gap-3 border-b pb-2 last:border-0">
              <span>
                {item.title} × {item.quantity}
              </span>
              <span>{formatINR(item.line_total, order.currency)}</span>
            </div>
          ))}
          <p className="flex justify-between">
            <span className="text-muted-foreground">Subtotal</span>
            <span>{formatINR(order.subtotal_amount, order.currency)}</span>
          </p>
          <p className="flex justify-between">
            <span className="text-muted-foreground">Discount</span>
            <span>{formatINR(order.discount_amount, order.currency)}</span>
          </p>
          <p className="flex justify-between">
            <span className="text-muted-foreground">Platform fee</span>
            <span>{formatINR(order.platform_fee_amount, order.currency)}</span>
          </p>
          <p className="flex justify-between">
            <span className="text-muted-foreground">Tax</span>
            <span>{formatINR(order.tax_amount, order.currency)}</span>
          </p>
          <p className="flex justify-between font-semibold">
            <span>Total</span>
            <span>{formatINR(order.total_amount, order.currency)}</span>
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Pickup</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p>
            Window: {formatDateTime(order.pickup_starts_at)} → {formatDateTime(order.pickup_ends_at)}
          </p>
          {order.store.pickup_instructions ? <p>Instructions: {order.store.pickup_instructions}</p> : null}
          {order.customer_note ? <p>Customer note: {order.customer_note}</p> : null}
          {order.collected_at ? <p>Collected: {formatDateTime(order.collected_at)}</p> : null}
          <div>
            <Button asChild variant="outline">
              <Link href="/merchant/pickups">Verify a pickup</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Status timeline (recorded events only)</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {order.timeline.length === 0 ? (
            <p className="text-muted-foreground">No recorded events yet.</p>
          ) : (
            order.timeline.map((event, index) => (
              <p key={`${event.status}-${index}`}>
                {event.label} — {formatDateTime(event.occurred_at)}
              </p>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
