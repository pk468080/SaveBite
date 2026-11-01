"use client";

import { ApiError, createServices, type AdminOrderDetail } from "@savebite/api-client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

/**
 * Platform order detail (W6, M11). Read-only:
 * items, pickup window, collected time, customer
 * note (when the backend returns one), and the
 * recorded status timeline. No customer personal
 * data is returned by this endpoint, so none is
 * shown. There is no order-edit endpoint.
 */
export default function AdminOrderDetailPage({
  params,
}: {
  params: Promise<{ orderId: string }>;
}) {
  const { orderId } = use(params);
  const [order, setOrder] = useState<AdminOrderDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    createServices(createBrowserApiClient())
      .admin.getOrderDetail(orderId)
      .then((data) => {
        if (!cancelled) setOrder(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
          setDenied(true);
        } else if (err instanceof ApiError && err.status === 404) {
          setOrder(null);
        } else {
          setError(err instanceof Error ? err.message : "Could not load this order.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [orderId]);

  if (loading) return <LoadingState label="Loading order" />;
  if (denied) return <AccessDenied />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!order) {
    return (
      <EmptyState title="Order not found" description="This order does not exist.">
        <Button asChild>
          <Link href="/admin/orders">Back to orders</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Order {order.order_number}</h1>
        <p className="text-sm text-muted-foreground">
          {order.store_name} · {order.merchant_name} · {orderStatusLabel(order.status)} ·{" "}
          {paymentStatusLabel(order.payment_status)}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Order summary</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p>
            <span className="text-muted-foreground">Total: </span>
            {formatINR(order.total_amount, order.currency)}
          </p>
          <p>
            <span className="text-muted-foreground">Pickup window: </span>
            {formatDateTime(order.pickup_starts_at)} – {formatDateTime(order.pickup_ends_at)}
          </p>
          {order.collected_at ? (
            <p>
              <span className="text-muted-foreground">Collected: </span>
              {formatDateTime(order.collected_at)}
            </p>
          ) : null}
          <p>
            <span className="text-muted-foreground">Created: </span>
            {formatDateTime(order.created_at)}
          </p>
          {order.customer_note ? (
            <p>
              <span className="text-muted-foreground">Customer note: </span>
              {order.customer_note}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Items</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col divide-y p-0">
          {order.items.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No items recorded.</p>
          ) : (
            order.items.map((item, index) => (
              <div key={`${item.title}-${index}`} className="flex flex-wrap justify-between gap-2 p-4 text-sm">
                <p>
                  {item.title} × {item.quantity}
                </p>
                <p>
                  {formatINR(item.unit_price, order.currency)} each ·{" "}
                  {formatINR(item.line_total, order.currency)}
                </p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Status timeline</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {order.events.length === 0 ? (
            <p className="text-muted-foreground">No recorded status events yet.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {order.events.map((event, index) => (
                <li key={`${event.to_status}-${index}`}>
                  {event.from_status ? `${event.from_status} → ` : ""}
                  {event.to_status} · {event.actor_type} · {formatDateTime(event.created_at)}
                  {event.reason ? ` · ${event.reason}` : ""}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div>
        <Button asChild variant="outline">
          <Link href="/admin/orders">Back to orders</Link>
        </Button>
      </div>
    </div>
  );
}
