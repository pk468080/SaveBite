"use client";

import { createServices, type MerchantDashboard } from "@savebite/api-client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";

/**
 * Merchant dashboard (W4, M10). Every number
 * comes from GET /v1/merchant/dashboard. Captured
 * order value is labelled exactly that — it is
 * NOT earnings, settlement or payout revenue.
 * open_now is null by design (the weekday
 * convention is unverified), so it is never shown
 * as open or closed.
 */
function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">{value}</p>
        {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

export default function MerchantDashboardPage() {
  const { merchants, stores, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [dashboard, setDashboard] = useState<MerchantDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  useEffect(() => {
    if (storesLoading) return;
    if (merchants.length === 0) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    createServices(createBrowserApiClient())
      .merchantDashboard.getDashboard({
        store_id: selectedStoreId ?? undefined,
        from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
        to: to ? new Date(`${to}T00:00:00`).toISOString() : undefined,
      })
      .then((data) => {
        if (!cancelled) setDashboard(data);
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
  }, [storesLoading, merchants.length, selectedStoreId, from, to]);

  if (storesLoading) return <LoadingState label="Loading your stores" />;
  if (merchants.length === 0) {
    return (
      <EmptyState
        title="No merchant application yet"
        description="Submit a merchant application first. Once it is approved, your stores and dashboard appear here."
      >
        <Button asChild>
          <Link href="/merchant/onboarding">Start onboarding</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Merchant dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Real orders, inventory, pickups and ratings for your authorized stores only.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <StoreSelector allowAll />
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">From</span>
            <input
              type="date"
              className="h-10 rounded-md border border-input bg-background px-3"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">To</span>
            <input
              type="date"
              className="h-10 rounded-md border border-input bg-background px-3"
              value={to}
              onChange={(event) => setTo(event.target.value)}
            />
          </label>
        </div>
      </div>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading dashboard" />
      ) : dashboard ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Total orders" value={String(dashboard.orders.total_orders)} />
            <Metric label="Paid orders (captured)" value={String(dashboard.orders.paid_orders)} />
            <Metric
              label="Captured order value"
              value={formatINR(dashboard.orders.captured_order_value)}
              hint="Captured payments only — not earnings or payouts."
            />
            <Metric label="Awaiting payment" value={String(dashboard.orders.awaiting_payment_orders)} />
            <Metric label="Collected orders" value={String(dashboard.orders.collected_orders)} />
            <Metric label="Active listings" value={String(dashboard.inventory.published_listings)} />
            <Metric label="Available units" value={String(dashboard.inventory.total_available_units)} />
            <Metric label="Reserved units" value={String(dashboard.inventory.total_reserved_units)} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Upcoming pickups" value={String(dashboard.pickups.upcoming_pickups)} />
            <Metric label="Pickups in window" value={String(dashboard.pickups.in_window_pickups)} />
            <Metric label="Completed collections" value={String(dashboard.pickups.completed_collections)} />
            <Metric
              label="Window-expired pickups"
              value={String(dashboard.pickups.window_expired_pickups)}
              hint="Window closed without collection — not recorded as a no-show."
            />
          </div>
          <Card>
            <CardHeader>
              <CardTitle>Customer ratings (visible reviews only)</CardTitle>
            </CardHeader>
            <CardContent>
              {dashboard.ratings.average_rating === null ? (
                <p className="text-sm text-muted-foreground">
                  No visible reviews yet — no average is shown rather than inventing one.
                </p>
              ) : (
                <p className="text-sm">
                  Average {dashboard.ratings.average_rating.toFixed(2)} from{" "}
                  {dashboard.ratings.total_visible_reviews} visible reviews · 5★{" "}
                  {dashboard.ratings.five_star} · 4★ {dashboard.ratings.four_star} · 3★{" "}
                  {dashboard.ratings.three_star} · 2★ {dashboard.ratings.two_star} · 1★{" "}
                  {dashboard.ratings.one_star}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <Link href="/merchant/orders">View orders</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href="/merchant/listings">Manage listings</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href="/merchant/pickups">Verify a pickup</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href="/merchant/analytics">Analytics</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
          {stores.length > 0 && dashboard.store.store_count > 1 ? (
            <p className="text-sm text-muted-foreground">
              Showing {dashboard.store.store_count} authorized stores. Pick one store above to narrow
              every number to that store.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
