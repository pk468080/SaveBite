"use client";

import {
  createServices,
  type PickupDashboard,
  type SalesAnalytics,
  type StoreComparison,
} from "@savebite/api-client";
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
 * Analytics (W4, M10). All figures are the
 * server-provided amounts and counts. Captured
 * order value is never labelled earnings, and
 * no commission, settlement, payout or net
 * revenue is computed from it — the order row
 * carries no refund amounts to net against.
 * Charts here are tables of the returned
 * buckets only; no trend is drawn from data the
 * backend did not return.
 */
export default function MerchantAnalyticsPage() {
  const { merchants, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [sales, setSales] = useState<SalesAnalytics | null>(null);
  const [comparison, setComparison] = useState<StoreComparison | null>(null);
  const [pickups, setPickups] = useState<PickupDashboard | null>(null);
  const [groupBy, setGroupBy] = useState<"day" | "week" | "month">("day");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (storesLoading) return;
    if (merchants.length === 0) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const services = createServices(createBrowserApiClient());
    const params = {
      store_id: selectedStoreId ?? undefined,
      from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
      to: to ? new Date(`${to}T00:00:00`).toISOString() : undefined,
    };
    Promise.all([
      services.merchantDashboard.getSales({ ...params, group_by: groupBy }),
      services.merchantDashboard.getStoreComparison({ from: params.from, to: params.to }),
      services.merchantDashboard.getPickups(params),
    ])
      .then(([salesData, comparisonData, pickupData]) => {
        if (!cancelled) {
          setSales(salesData);
          setComparison(comparisonData);
          setPickups(pickupData);
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
  }, [storesLoading, merchants.length, selectedStoreId, groupBy, from, to]);

  if (storesLoading) return <LoadingState label="Loading stores" />;
  if (merchants.length === 0) {
    return <EmptyState title="No merchant application yet" description="Analytics appear once your stores have orders." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="text-2xl font-bold">Analytics</h1>
        <div className="flex flex-wrap items-end gap-3">
          <StoreSelector allowAll />
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Group by</span>
            <select
              className="h-10 rounded-md border border-input bg-background px-3"
              value={groupBy}
              onChange={(event) => setGroupBy(event.target.value as "day" | "week" | "month")}
            >
              <option value="day">Day</option>
              <option value="week">Week</option>
              <option value="month">Month</option>
            </select>
          </label>
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
        <LoadingState label="Loading analytics" />
      ) : (
        <>
          {sales ? (
            <Card>
              <CardHeader>
                <CardTitle>
                  Sales by {groupBy} — totals: {sales.totals.total_orders} orders,{" "}
                  {sales.totals.captured_orders} captured, {sales.totals.collected_orders} collected,{" "}
                  {formatINR(sales.totals.captured_order_value)} captured order value
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="mb-3 text-sm text-muted-foreground">
                  Captured order value is the sum of captured payments only — not earnings, not
                  payouts. Reporting timezone: {sales.reporting_timezone}.
                </p>
                {sales.buckets.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No orders in this period.</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-muted-foreground">
                        <th className="py-2 pr-2">Period</th>
                        <th className="py-2 pr-2">Orders</th>
                        <th className="py-2 pr-2">Captured</th>
                        <th className="py-2 pr-2">Pending payment</th>
                        <th className="py-2 pr-2">Failed</th>
                        <th className="py-2 pr-2">Collected</th>
                        <th className="py-2">Captured value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sales.buckets.map((bucket) => (
                        <tr key={bucket.period_start} className="border-t">
                          <td className="py-2 pr-2">{bucket.period_start}</td>
                          <td className="py-2 pr-2">{bucket.total_orders}</td>
                          <td className="py-2 pr-2">{bucket.captured_orders}</td>
                          <td className="py-2 pr-2">{bucket.pending_payment_orders}</td>
                          <td className="py-2 pr-2">{bucket.failed_payment_orders}</td>
                          <td className="py-2 pr-2">{bucket.collected_orders}</td>
                          <td className="py-2">{formatINR(bucket.captured_order_value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          ) : null}
          {comparison && comparison.stores.length > 1 ? (
            <Card>
              <CardHeader>
                <CardTitle>Store comparison</CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="py-2 pr-2">Store</th>
                      <th className="py-2 pr-2">Orders</th>
                      <th className="py-2 pr-2">Captured value</th>
                      <th className="py-2 pr-2">Collected</th>
                      <th className="py-2 pr-2">Active listings</th>
                      <th className="py-2 pr-2">Available units</th>
                      <th className="py-2">Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.stores.map((row) => (
                      <tr key={row.store_id} className="border-t">
                        <td className="py-2 pr-2">{row.store_name}</td>
                        <td className="py-2 pr-2">{row.total_orders}</td>
                        <td className="py-2 pr-2">{formatINR(row.captured_order_value)}</td>
                        <td className="py-2 pr-2">{row.collected_orders}</td>
                        <td className="py-2 pr-2">{row.active_listings}</td>
                        <td className="py-2 pr-2">{row.available_units}</td>
                        <td className="py-2">
                          {row.average_rating === null
                            ? "No visible reviews"
                            : `${row.average_rating.toFixed(2)} (${row.review_count})`}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          ) : null}
          {pickups ? (
            <Card>
              <CardHeader>
                <CardTitle>Pickups in this period</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <p>
                  Upcoming {pickups.counts.upcoming_pickups} · In window {pickups.counts.in_window_pickups} ·
                  Completed {pickups.counts.completed_collections} · Window expired{" "}
                  {pickups.counts.window_expired_pickups}
                </p>
                {pickups.orders.length === 0 ? (
                  <p className="text-muted-foreground">No pickup orders in this period.</p>
                ) : (
                  pickups.orders.map((order) => (
                    <p key={order.order_number}>
                      {order.order_number} — {order.category.replace("_", " ")} — {order.total_quantity}{" "}
                      item(s)
                    </p>
                  ))
                )}
              </CardContent>
            </Card>
          ) : null}
          <div>
            <Button asChild variant="outline">
              <Link href="/merchant">Back to dashboard</Link>
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
