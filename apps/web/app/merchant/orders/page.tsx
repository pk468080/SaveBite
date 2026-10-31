"use client";

import { createServices, type MerchantOrderSummary } from "@savebite/api-client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { StatusBadge } from "@/components/merchant/status-badge";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";
import { formatINR } from "@/lib/marketplace";

const ORDER_STATUSES = [
  "pending_payment",
  "confirmed",
  "ready_for_pickup",
  "collected",
  "expired",
  "cancelled",
  "refund_pending",
  "refunded",
];

const PAYMENT_STATUSES = [
  "created",
  "authorized",
  "captured",
  "failed",
  "refund_pending",
  "partially_refunded",
  "refunded",
  "reconciliation_required",
];

/**
 * Merchant order queue (W4, M7). The merchant
 * list view deliberately carries no customer
 * personal data — no customer id, email, phone
 * or address — so none is shown here. Payment
 * status and fulfilment status stay distinct:
 * captured is not collected, confirmed is not
 * ready for pickup. Merchants cannot change
 * order or payment status from this portal.
 */
function OrdersList() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { selectedStoreId } = useMerchantStores();
  const status = searchParams.get("status") ?? "";
  const paymentStatus = searchParams.get("payment_status") ?? "";
  const search = searchParams.get("search") ?? "";
  const storeParam = searchParams.get("store_id") ?? "";
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1);
  const effectiveStoreId = storeParam || selectedStoreId || undefined;

  const [orders, setOrders] = useState<MerchantOrderSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState(search);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    createServices(createBrowserApiClient())
      .orders.listMerchantOrders({
        store_id: effectiveStoreId,
        status: status || undefined,
        payment_status: paymentStatus || undefined,
        search: search || undefined,
        page,
        page_size: 20,
      })
      .then((data) => {
        if (!cancelled) {
          setOrders(data.items);
          setTotal(data.total);
        }
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
  }, [effectiveStoreId, status, paymentStatus, search, page]);

  function updateParams(patch: Record<string, string | null>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value === null || value === "") {
        next.delete(key);
      } else {
        next.set(key, value);
      }
    }
    next.delete("page");
    router.push(`/merchant/orders?${next.toString()}`);
  }

  const pageCount = Math.max(1, Math.ceil(total / 20));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Orders</h1>
        <StoreSelector allowAll />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Order status</span>
            <select
              className="h-10 rounded-md border border-input bg-background px-3"
              value={status}
              onChange={(event) => updateParams({ status: event.target.value || null })}
            >
              <option value="">All</option>
              {ORDER_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {orderStatusLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Payment status</span>
            <select
              className="h-10 rounded-md border border-input bg-background px-3"
              value={paymentStatus}
              onChange={(event) => updateParams({ payment_status: event.target.value || null })}
            >
              <option value="">All</option>
              {PAYMENT_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {paymentStatusLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              updateParams({ search: searchInput || null });
            }}
          >
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Order number</span>
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="SB-…"
              />
            </label>
            <Button type="submit">Search</Button>
          </form>
        </CardContent>
      </Card>
      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading orders" />
      ) : !orders || orders.length === 0 ? (
        <EmptyState
          title="No orders match"
          description="Orders for your authorized stores appear here once customers reserve and pay."
        />
      ) : (
        <>
          <div className="grid gap-4">
            {orders.map((order) => (
              <Card key={order.id}>
                <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-6 text-sm">
                  <div>
                    <Link className="font-semibold underline" href={`/merchant/orders/${order.id}`}>
                      {order.order_number}
                    </Link>
                    <p className="text-muted-foreground">
                      {order.store.name} · {order.item_count} item(s) ·{" "}
                      {order.items_preview.map((item) => `${item.title} × ${item.quantity}`).join(", ")}
                    </p>
                    <p className="text-muted-foreground">
                      Pickup {formatDateTime(order.pickup_starts_at)} → {formatDateTime(order.pickup_ends_at)}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <span className="font-semibold">{formatINR(order.total_amount)}</span>
                    <span className="flex gap-2">
                      <StatusBadge status={order.status} label={orderStatusLabel(order.status)} />
                      <StatusBadge status={order.payment_status} label={paymentStatusLabel(order.payment_status)} />
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <div className="flex items-center justify-between text-sm">
            <span>
              Page {page} of {pageCount} · {total} orders
            </span>
            <span className="flex gap-2">
              <Button
                variant="outline"
                disabled={page <= 1}
                onClick={() => {
                  const next = new URLSearchParams(searchParams.toString());
                  next.set("page", String(page - 1));
                  router.push(`/merchant/orders?${next.toString()}`);
                }}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                disabled={page >= pageCount}
                onClick={() => {
                  const next = new URLSearchParams(searchParams.toString());
                  next.set("page", String(page + 1));
                  router.push(`/merchant/orders?${next.toString()}`);
                }}
              >
                Next
              </Button>
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export default function MerchantOrdersPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading orders" />}>
      <OrdersList />
    </Suspense>
  );
}
