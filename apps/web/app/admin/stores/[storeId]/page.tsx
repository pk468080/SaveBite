"use client";

import { ApiError, createServices, type AdminStoreDetail } from "@savebite/api-client";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { StoreReviewPanel } from "@/components/admin/store-review-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { storeStatusLabel } from "@/lib/admin";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Store detail + activation (W6, M11). Hours
 * come from GET /v1/admin/stores/{id} as weekday
 * numbers with opening and closing times. The
 * backend never confirms whether weekday 0 is
 * Monday or Sunday, so day names are never
 * guessed here either — the same rule as the
 * merchant hours editor in W4.
 */
export default function AdminStoreDetailPage({
  params,
}: {
  params: Promise<{ storeId: string }>;
}) {
  const { storeId } = use(params);
  const [store, setStore] = useState<AdminStoreDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDenied(false);
    try {
      const data = await createServices(createBrowserApiClient()).admin.getStoreDetail(storeId);
      setStore(data);
    } catch (err) {
      if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
        setDenied(true);
      } else if (err instanceof ApiError && err.status === 404) {
        setStore(null);
      } else {
        setError(err instanceof Error ? err.message : "Could not load this store.");
      }
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingState label="Loading store" />;
  if (denied) return <AccessDenied />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!store) {
    return (
      <EmptyState title="Store not found" description="This store does not exist.">
        <Button asChild>
          <Link href="/admin/stores">Back to stores</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">{store.name}</h1>
        <p className="text-sm text-muted-foreground">
          {store.merchant_name} · {storeStatusLabel(store.status)}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Store details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p>
            <span className="text-muted-foreground">Address: </span>
            {store.address_line_1}
            {store.locality ? `, ${store.locality}` : ""}, {store.city}, {store.state}{" "}
            {store.pincode}
          </p>
          <p>
            <span className="text-muted-foreground">Timezone: </span>
            {store.timezone}
          </p>
          <p>
            <span className="text-muted-foreground">Listings: </span>
            {store.listing_count} · <span className="text-muted-foreground">Orders: </span>
            {store.order_count}
          </p>
          {store.created_at ? (
            <p>
              <span className="text-muted-foreground">Created: </span>
              {formatDateTime(store.created_at)}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Operating hours</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p className="text-muted-foreground">
            Weekday numbers as returned by the backend. Whether weekday 0 is Monday or Sunday is
            not confirmed by the backend, so no day names are shown.
          </p>
          {store.hours.length === 0 ? (
            <p className="text-muted-foreground">No hours recorded for this store.</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {store.hours.map((hour, index) => (
                <li key={`${hour.weekday}-${index}`}>
                  Weekday {hour.weekday}: {hour.opens_at ?? "—"} – {hour.closes_at ?? "—"}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <StoreReviewPanel
        storeId={store.id}
        currentActive={store.status === "active"}
        onReviewed={() => void load()}
      />

      <div>
        <Button asChild variant="outline">
          <Link href="/admin/stores">Back to stores</Link>
        </Button>
      </div>
    </div>
  );
}
