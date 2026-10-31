"use client";

import { createServices, type InventoryDashboard, type ListingSummary } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/merchant/status-badge";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import { listingStatusLabel } from "@/lib/merchant";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Inventory (W4, M4 + M10). Read-only visibility:
 * there is no approved inventory-adjustment API,
 * so nothing here changes a quantity. Available
 * is the generated column value as returned.
 * The low-stock filter is a reporting threshold
 * the dashboard endpoint accepts — it changes no
 * listing status and defines no business rule.
 */
export default function MerchantInventoryPage() {
  const { stores, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [dashboard, setDashboard] = useState<InventoryDashboard | null>(null);
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [threshold, setThreshold] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (storesLoading) return;
    if (!selectedStoreId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    const services = createServices(createBrowserApiClient());
    const thresholdValue = threshold.trim() ? Number(threshold) : undefined;
    Promise.all([
      services.merchantDashboard.getInventory({
        store_id: selectedStoreId,
        low_stock_threshold:
          thresholdValue !== undefined && Number.isInteger(thresholdValue) && thresholdValue >= 0
            ? thresholdValue
            : undefined,
      }),
      services.merchants.listStoreListings(selectedStoreId),
    ])
      .then(([inventory, storeListings]) => {
        if (!cancelled) {
          setDashboard(inventory);
          setListings(storeListings);
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
  }, [storesLoading, selectedStoreId, threshold]);

  if (storesLoading) return <LoadingState label="Loading stores" />;
  if (stores.length === 0) {
    return <EmptyState title="No stores yet" description="Create a store first, then its inventory appears here." />;
  }
  if (!selectedStoreId) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Inventory</h1>
        <p className="text-sm text-muted-foreground">Pick a store to see its inventory.</p>
        <StoreSelector />
      </div>
    );
  }

  const visible = statusFilter ? listings.filter((item) => item.status === statusFilter) : listings;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Inventory</h1>
        <div className="flex flex-wrap items-center gap-3">
          <StoreSelector />
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Low-stock at or below</span>
            <Input
              className="w-24"
              inputMode="numeric"
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              placeholder="—"
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Status</span>
            <select
              className="h-10 rounded-md border border-input bg-background px-3"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="">All</option>
              {["draft", "scheduled", "active", "paused", "sold_out", "expired", "cancelled"].map((status) => (
                <option key={status} value={status}>
                  {listingStatusLabel(status)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading inventory" />
      ) : (
        <>
          {dashboard ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-muted-foreground">Available units</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-bold">{dashboard.summary.total_available_units}</CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-muted-foreground">Reserved units</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-bold">{dashboard.summary.total_reserved_units}</CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-muted-foreground">Sold units</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-bold">{dashboard.summary.total_sold_units}</CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm font-medium text-muted-foreground">Listings</CardTitle>
                </CardHeader>
                <CardContent className="text-2xl font-bold">
                  {dashboard.summary.total_listings} total · {dashboard.summary.published_listings} published ·{" "}
                  {dashboard.summary.draft_listings} draft
                </CardContent>
              </Card>
            </div>
          ) : null}
          {dashboard && dashboard.low_stock_listings.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>At or below the threshold ({threshold})</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {dashboard.low_stock_listings.map((item) => (
                  <p key={item.listing_id}>
                    {item.title} — {item.available_quantity} available (reserved {item.reserved_quantity}, sold{" "}
                    {item.sold_quantity})
                  </p>
                ))}
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>All listings ({visible.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {visible.length === 0 ? (
                <p className="text-sm text-muted-foreground">No listings match.</p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground">
                      <th className="py-2 pr-2">Listing</th>
                      <th className="py-2 pr-2">Status</th>
                      <th className="py-2 pr-2">Total</th>
                      <th className="py-2 pr-2">Reserved</th>
                      <th className="py-2 pr-2">Sold</th>
                      <th className="py-2">Available</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((listing) => (
                      <tr key={listing.id} className="border-t">
                        <td className="py-2 pr-2">{listing.title}</td>
                        <td className="py-2 pr-2">
                          <StatusBadge status={listing.status} label={listingStatusLabel(listing.status)} />
                        </td>
                        <td className="py-2 pr-2">{listing.total_quantity}</td>
                        <td className="py-2 pr-2">{listing.reserved_quantity}</td>
                        <td className="py-2 pr-2">{listing.sold_quantity}</td>
                        <td className="py-2">{listing.available_quantity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
