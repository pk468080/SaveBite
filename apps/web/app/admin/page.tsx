"use client";

import { ApiError, createServices, type AdminDashboard } from "@savebite/api-client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

/**
 * Platform overview (W6, M11). Every number
 * comes from GET /v1/admin/dashboard, displayed
 * exactly as the backend defines it. Captured
 * order value is the sum of order totals where
 * payment is captured — it is NOT earnings,
 * payouts, revenue, or platform profit, and it
 * is never labelled as any of those. There is
 * no customer count: the backend cannot count
 * customers through this API (profiles are
 * readable only by their owner), so none is
 * shown or estimated. Refresh re-reads the
 * backend; there is no polling.
 */
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>
    </section>
  );
}

export default function AdminOverviewPage() {
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDenied(false);
    try {
      const data = await createServices(createBrowserApiClient()).admin.getDashboard();
      setDashboard(data);
    } catch (err) {
      // 401/403 are shown as access denied, once,
      // never retried in a loop. Other failures
      // surface as an error, not an empty page.
      if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
        setDenied(true);
      } else {
        setError(err instanceof Error ? err.message : "Could not load the platform overview.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingState label="Loading platform overview" />;
  if (denied) return <AccessDenied />;
  if (error) {
    return (
      <div className="flex flex-col gap-3">
        <Alert variant="error">{error}</Alert>
        <div>
          <Button variant="outline" onClick={() => void load()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }
  if (!dashboard) {
    return <EmptyState title="No platform data" description="The backend returned no overview." />;
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Platform overview</h1>
          <p className="text-sm text-muted-foreground">
            Live counts from the platform backend. Customer counts are not available through this
            API and are not estimated here.
          </p>
        </div>
        <Button variant="outline" onClick={() => void load()}>
          Refresh
        </Button>
      </div>

      <Section title="Merchants and stores">
        <Metric label="Merchants" value={String(dashboard.merchants_total)} />
        <Metric label="Merchants approved" value={String(dashboard.merchants_approved)} />
        <Metric label="Merchants pending review" value={String(dashboard.merchants_pending_review)} />
        <Metric label="Stores" value={String(dashboard.stores_total)} />
        <Metric label="Stores active" value={String(dashboard.stores_active)} />
        <Metric label="Stores draft" value={String(dashboard.stores_draft)} />
        <Metric label="Stores inactive" value={String(dashboard.stores_inactive)} />
        <Metric label="Stores suspended" value={String(dashboard.stores_suspended)} />
      </Section>

      <Section title="Listings">
        <Metric label="Listings" value={String(dashboard.listings_total)} />
        <Metric label="Listings published" value={String(dashboard.listings_published)} />
        <Metric label="Listings draft" value={String(dashboard.listings_draft)} />
        <Metric label="Listings paused" value={String(dashboard.listings_paused)} />
        <Metric label="Listings sold out" value={String(dashboard.listings_sold_out)} />
        <Metric label="Listings expired" value={String(dashboard.listings_expired)} />
      </Section>

      <Section title="Orders">
        <Metric label="Orders" value={String(dashboard.orders_total)} />
        <Metric label="Orders pending payment" value={String(dashboard.orders_pending_payment)} />
        <Metric label="Orders confirmed" value={String(dashboard.orders_confirmed)} />
        <Metric label="Orders ready for pickup" value={String(dashboard.orders_ready_for_pickup)} />
        <Metric label="Orders collected" value={String(dashboard.orders_collected)} />
        <Metric label="Orders cancelled or expired" value={String(dashboard.orders_cancelled_or_expired)} />
      </Section>

      <Section title="Payments">
        <Metric label="Captured order value" value={formatINR(dashboard.captured_order_value, "INR")} />
        <Metric label="Captured payments" value={String(dashboard.captured_payment_count)} />
        <Metric label="Failed payments" value={String(dashboard.failed_payment_count)} />
        <Metric label="Payments not started" value={String(dashboard.pending_payment_count)} />
        <Metric label="Payments needing verification" value={String(dashboard.reconciliation_required_count)} />
        <Metric label="Refund-pending orders" value={String(dashboard.refund_pending_count)} />
      </Section>
      <p className="-mt-4 text-sm text-muted-foreground">
        Captured order value is the sum of captured payments only. It is not merchant earnings,
        payouts, revenue, or platform profit.
      </p>

      <Section title="Reviews">
        <Metric label="Visible reviews" value={String(dashboard.visible_reviews_total)} />
        <Metric
          label="Average visible rating"
          value={
            dashboard.average_visible_rating === null
              ? "No reviews yet"
              : dashboard.average_visible_rating.toFixed(2)
          }
        />
      </Section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Recent orders</h2>
        {dashboard.recent_orders.length === 0 ? (
          <p className="text-sm text-muted-foreground">No orders yet.</p>
        ) : (
          <Card>
            <CardContent className="flex flex-col divide-y p-0">
              {dashboard.recent_orders.map((order) => (
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
        <div>
          <Button asChild variant="outline">
            <Link href="/admin/merchants">Review merchant applications</Link>
          </Button>
        </div>
      </section>
    </div>
  );
}
