"use client";

import { ApiError, createServices } from "@savebite/api-client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState, Skeleton } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";
import type { OrderSummary } from "@savebite/api-client";

/**
 * Customer order history (W3). Newest first, from the
 * backend only — no order is ever invented here.
 * Status honesty (M7): pending payment is not paid,
 * captured is not collected, confirmed is not ready
 * for pickup, and reconciliation_required is never a
 * successful purchase.
 */
const ORDER_STATUS_OPTIONS = [
  "pending_payment",
  "confirmed",
  "ready_for_pickup",
  "collected",
  "expired",
  "cancelled",
  "refund_pending",
  "refunded",
] as const;

const PAYMENT_STATUS_OPTIONS = [
  "created",
  "authorized",
  "captured",
  "failed",
  "refund_pending",
  "partially_refunded",
  "refunded",
  "reconciliation_required",
] as const;

function OrdersList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const status = searchParams.get("status") ?? "";
  const paymentStatus = searchParams.get("payment_status") ?? "";
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);

  const [orders, setOrders] = useState<OrderSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const services = createServices(createBrowserApiClient());
        const result = await services.orders.listOrders({
          status: status || undefined,
          payment_status: paymentStatus || undefined,
          page,
          page_size: 20,
        });
        if (!cancelled) {
          setOrders(result.items);
          setTotal(result.total);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.message : "Could not load your orders.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, paymentStatus, page]);

  function setParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    params.delete("page");
    router.replace(`/customer/orders?${params.toString()}`);
  }

  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">My orders</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Your reservations and purchases, newest first.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Order status</span>
          <select
            value={status}
            onChange={(event) => setParam("status", event.target.value)}
            className="h-10 rounded-md border bg-background px-3"
          >
            <option value="">All</option>
            {ORDER_STATUS_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {orderStatusLabel(value)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Payment status</span>
          <select
            value={paymentStatus}
            onChange={(event) => setParam("payment_status", event.target.value)}
            className="h-10 rounded-md border bg-background px-3"
          >
            <option value="">All</option>
            {PAYMENT_STATUS_OPTIONS.map((value) => (
              <option key={value} value={value}>
                {paymentStatusLabel(value)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <div className="flex flex-col gap-3" aria-label="Loading orders">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
      ) : orders && orders.length === 0 ? (
        <EmptyState
          title="No orders yet"
          description="Once you reserve and pay for surplus food, your orders will appear here."
          >
        <Button asChild><Link href="/marketplace">Explore food</Link></Button>
      </EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          {orders?.map((order) => (
            <Card key={order.id}>
              <CardContent className="flex flex-col gap-2 p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <Link href={`/customer/orders/${order.id}`} className="font-semibold hover:underline">
                    {order.order_number}
                  </Link>
                  <span className="font-semibold">{formatINR(order.total_amount, order.currency)}</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  {order.store.name} · {order.store.city} ·{" "}
                  {order.items_preview.map((item) => `${item.title} × ${item.quantity}`).join(", ")}
                  {order.item_count > order.items_preview.length
                    ? ` + ${order.item_count - order.items_preview.length} more`
                    : ""}
                </p>
                <p className="text-sm">
                  <span className="font-medium">{orderStatusLabel(order.status)}</span>
                  {" · "}
                  <span className="text-muted-foreground">
                    Payment: {paymentStatusLabel(order.payment_status)}
                  </span>
                </p>
                <p className="text-xs text-muted-foreground">
                  Ordered {formatDateTime(order.created_at)}
                </p>
                <div>
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/customer/orders/${order.id}`}>View details</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => {
                const params = new URLSearchParams(searchParams.toString());
                params.set("page", String(page - 1));
                router.replace(`/customer/orders?${params.toString()}`);
              }}
            >
              Previous
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} of {pageCount} · {total} order{total === 1 ? "" : "s"}
            </span>
            <Button
              variant="outline"
              disabled={page >= pageCount}
              onClick={() => {
                const params = new URLSearchParams(searchParams.toString());
                params.set("page", String(page + 1));
                router.replace(`/customer/orders?${params.toString()}`);
              }}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function OrdersPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading orders…" />}>
      <OrdersList />
    </Suspense>
  );
}
