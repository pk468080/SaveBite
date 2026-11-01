"use client";

import { ApiError, createServices, type AdminOrderSummary } from "@savebite/api-client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { AdminPager } from "@/components/admin/pager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { ADMIN_PAGE_SIZE } from "@/lib/admin";
import { formatINR } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

/**
 * Platform order list (W6, M11). Read-only:
 * there is no order-status-change endpoint, so
 * no action buttons are shown. Filters and
 * pagination are server-side. Order-number
 * search is a database-side partial match.
 */
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

export default function AdminOrdersPage() {
  const [items, setItems] = useState<AdminOrderSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("all");
  const [paymentStatus, setPaymentStatus] = useState("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDenied(false);
    createServices(createBrowserApiClient())
      .admin.listOrders({
        status: status === "all" ? undefined : status,
        payment_status: paymentStatus === "all" ? undefined : paymentStatus,
        order_number: search || undefined,
        page,
        page_size: ADMIN_PAGE_SIZE,
      })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
          setDenied(true);
        } else {
          setError(err instanceof Error ? err.message : "Could not load orders.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, paymentStatus, search, page]);

  if (denied) return <AccessDenied />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Orders</h1>
        <p className="text-sm text-muted-foreground">
          Platform orders, read-only. Customer personal details are not returned by this API and
          are not shown here.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Order status</span>
            <Select value={status} onValueChange={(value) => { setStatus(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {ORDER_STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {orderStatusLabel(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Payment status</span>
            <Select value={paymentStatus} onValueChange={(value) => { setPaymentStatus(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All payment states</SelectItem>
                {PAYMENT_STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {paymentStatusLabel(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <form
            className="flex flex-1 items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchInput.trim());
              setPage(1);
            }}
          >
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span>Order number</span>
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search order number"
              />
            </label>
            <Button type="submit">Search</Button>
          </form>
        </CardContent>
      </Card>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading orders" />
      ) : items.length === 0 ? (
        <EmptyState title="No orders found" description="Try a different filter or search." />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y p-0">
            {items.map((order) => (
              <div key={order.id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
                <div>
                  <Link href={`/admin/orders/${order.id}`} className="font-medium underline underline-offset-4">
                    Order {order.order_number}
                  </Link>
                  <p className="text-muted-foreground">
                    {order.store_name} · {order.merchant_name} · {formatDateTime(order.created_at)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-medium">{formatINR(order.total_amount, order.currency)}</p>
                  <p className="text-muted-foreground">
                    {orderStatusLabel(order.status)} · {paymentStatusLabel(order.payment_status)}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      <AdminPager page={page} pageSize={ADMIN_PAGE_SIZE} total={total} onPage={setPage} />
    </div>
  );
}
