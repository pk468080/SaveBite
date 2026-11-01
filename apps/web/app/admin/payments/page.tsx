"use client";

import { ApiError, createServices, type AdminPaymentException } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { AdminPager } from "@/components/admin/pager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
 * Payments and refunds (W6, M11). Both lists
 * are READ-ONLY and order-level only: the
 * backend deliberately exposes no gateway ids,
 * signatures, or provider payloads, and no
 * refund execution endpoint exists, so no
 * refund button is shown. Refund-pending is
 * NOT refunded — only status refunded counts
 * as completed — and no refund amount is
 * estimated beyond the order total.
 */
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

export default function AdminPaymentsPage() {
  const [tab, setTab] = useState<"payments" | "refunds">("payments");
  const [items, setItems] = useState<AdminPaymentException[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [paymentStatus, setPaymentStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDenied(false);
    const call =
      tab === "payments"
        ? createServices(createBrowserApiClient()).admin.listPayments({
            payment_status: paymentStatus === "all" ? undefined : paymentStatus,
            page,
            page_size: ADMIN_PAGE_SIZE,
          })
        : createServices(createBrowserApiClient()).admin.listRefunds({
            page,
            page_size: ADMIN_PAGE_SIZE,
          });
    call
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
          setError(err instanceof Error ? err.message : "Could not load payment data.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tab, paymentStatus, page]);

  if (denied) return <AccessDenied />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Payments and refunds</h1>
        <p className="text-sm text-muted-foreground">
          Order-level payment visibility only. No refund can be executed from this portal — that
          capability does not exist in the backend.
        </p>
      </div>

      <div className="flex gap-2">
        <Button
          variant={tab === "payments" ? "default" : "outline"}
          onClick={() => { setTab("payments"); setPage(1); }}
        >
          Payment exceptions
        </Button>
        <Button
          variant={tab === "refunds" ? "default" : "outline"}
          onClick={() => { setTab("refunds"); setPage(1); }}
        >
          Refunds
        </Button>
      </div>

      {tab === "payments" ? (
        <Card>
          <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
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
          </CardContent>
        </Card>
      ) : (
        <Alert variant="info">
          An order appears here when its order status or payment status is refund-related.
          Refund-pending is not refunded — only status refunded counts as completed.
        </Alert>
      )}

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading payment data" />
      ) : items.length === 0 ? (
        <EmptyState
          title={tab === "payments" ? "No payment records found" : "No refund-related orders"}
          description="Try a different filter."
        />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y p-0">
            {items.map((row) => (
              <div key={row.order_id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
                <div>
                  <p className="font-medium">Order {row.order_number}</p>
                  <p className="text-muted-foreground">
                    {row.store_name} · {row.merchant_name} · {formatDateTime(row.created_at)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-medium">{formatINR(row.amount, row.currency)}</p>
                  <p className="text-muted-foreground">
                    {paymentStatusLabel(row.payment_status)} · {orderStatusLabel(row.order_status)}
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
