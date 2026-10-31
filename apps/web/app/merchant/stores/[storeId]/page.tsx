"use client";

import { createServices, type ListingSummary, type StoreDetail } from "@savebite/api-client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/merchant/status-badge";
import { useMerchantStores } from "@/components/merchant/store-context";
import { listingStatusLabel, storeStatusLabel } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";

/**
 * Store detail (W4, M3). There is no dedicated
 * GET /v1/stores/{id} endpoint, so the store is
 * found in the caller's own merchant store lists.
 * A store id outside the caller's memberships is
 * therefore simply not found here — and the
 * backend would refuse its data anyway.
 */
export default function StoreDetailPage({ params }: { params: Promise<{ storeId: string }> }) {
  const { storeId } = use(params);
  const { merchants, selectStore } = useMerchantStores();
  const [store, setStore] = useState<StoreDetail | null>(null);
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setNotFound(false);
    (async () => {
      try {
        const services = createServices(createBrowserApiClient());
        const found = merchants.length > 0 ? merchants : await services.merchants.listMerchants();
        let match: StoreDetail | null = null;
        for (const merchant of found) {
          const merchantStores = await services.merchants.listStores(merchant.id);
          const hit = merchantStores.find((item) => item.id === storeId);
          if (hit) {
            match = hit;
            break;
          }
        }
        if (cancelled) return;
        if (!match) {
          setNotFound(true);
          return;
        }
        setStore(match);
        selectStore(storeId);
        const storeListings = await services.merchants.listStoreListings(storeId);
        if (!cancelled) setListings(storeListings);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Store could not be loaded.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storeId, merchants, selectStore]);

  if (loading) return <LoadingState label="Loading store" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (notFound || !store) {
    return (
      <EmptyState
        title="Store not found"
        description="This store is not among your authorized stores, or it does not exist."
      >
        <Button asChild>
          <Link href="/merchant/stores">Back to stores</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{store.name}</h1>
          <p className="text-sm text-muted-foreground">
            {[store.locality, store.city, store.state, store.pincode].filter(Boolean).join(", ")}
          </p>
        </div>
        <StatusBadge status={store.status} label={storeStatusLabel(store.status)} />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Store details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p>Slug: {store.slug}</p>
          <p>
            Address: {[store.address_line_1, store.address_line_2].filter(Boolean).join(", ")}
          </p>
          <p>Timezone: {store.timezone}</p>
          {store.contact_phone ? <p>Contact phone: {store.contact_phone}</p> : null}
          {store.pickup_instructions ? <p>Pickup instructions: {store.pickup_instructions}</p> : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link href={`/merchant/stores/${store.id}/hours`}>Edit hours</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href="/merchant/listings/new">Create a listing</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={`/merchant/orders?store_id=${store.id}`}>View orders</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Listings ({listings.length})</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {listings.length === 0 ? (
            <p className="text-sm text-muted-foreground">No listings for this store yet.</p>
          ) : (
            listings.map((listing) => (
              <div key={listing.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 text-sm last:border-0">
                <Link className="underline" href={`/merchant/listings/${listing.id}`}>
                  {listing.title}
                </Link>
                <span className="flex items-center gap-3">
                  <StatusBadge status={listing.status} label={listingStatusLabel(listing.status)} />
                  <span>{formatINR(listing.selling_price)}</span>
                  <span className="text-muted-foreground">{listing.available_quantity} available</span>
                </span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
