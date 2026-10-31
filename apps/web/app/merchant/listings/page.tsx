"use client";

import { createServices, type ListingSummary } from "@savebite/api-client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/merchant/status-badge";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import { listingStatusLabel, listingTypeLabel } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatINR } from "@/lib/marketplace";

const STATUS_OPTIONS = ["draft", "scheduled", "active", "paused", "sold_out", "expired", "cancelled"];

/**
 * Listing list (W4, M4). Listings for the
 * selected store only; any merchant member can
 * read them, while writes need a manager role on
 * the backend. Available quantity is the database
 * generated value, shown as returned — never
 * recomputed here for a business decision.
 */
export default function MerchantListingsPage() {
  const { stores, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [listings, setListings] = useState<ListingSummary[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (storesLoading) return;
    if (!selectedStoreId) {
      setListings([]);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    createServices(createBrowserApiClient())
      .merchants.listStoreListings(selectedStoreId)
      .then((data) => {
        if (!cancelled) setListings(data);
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
  }, [storesLoading, selectedStoreId]);

  if (storesLoading) return <LoadingState label="Loading stores" />;
  if (stores.length === 0) {
    return (
      <EmptyState
        title="No stores yet"
        description="Create a store first, then its listings live here."
      >
        <Button asChild>
          <Link href="/merchant/stores/new">Create a store</Link>
        </Button>
      </EmptyState>
    );
  }

  const visible = statusFilter ? listings.filter((item) => item.status === statusFilter) : listings;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Listings</h1>
        <div className="flex flex-wrap items-center gap-3">
          <StoreSelector />
          <Select value={statusFilter || "all"} onValueChange={(value) => setStatusFilter(value === "all" ? "" : value)}>
            <SelectTrigger aria-label="Filter by status" className="w-48">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {STATUS_OPTIONS.map((status) => (
                <SelectItem key={status} value={status}>
                  {listingStatusLabel(status)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button asChild>
            <Link href="/merchant/listings/new">Create listing</Link>
          </Button>
        </div>
      </div>
      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading listings" />
      ) : visible.length === 0 ? (
        <EmptyState
          title="No listings match"
          description="Create a draft listing, then publish it when it is ready."
        >
          <Button asChild>
            <Link href="/merchant/listings/new">Create listing</Link>
          </Button>
        </EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {visible.map((listing) => (
            <Card key={listing.id}>
              <CardHeader>
                <CardTitle>
                  <Link className="underline" href={`/merchant/listings/${listing.id}`}>
                    {listing.title}
                  </Link>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                {listing.listing_type ? (
                  <p className="text-muted-foreground">{listingTypeLabel(listing.listing_type)}</p>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <StatusBadge status={listing.status} label={listingStatusLabel(listing.status)} />
                </div>
                <p>
                  {formatINR(listing.selling_price)} · Total {listing.total_quantity} · Reserved{" "}
                  {listing.reserved_quantity} · Sold {listing.sold_quantity} · Available{" "}
                  {listing.available_quantity}
                </p>
                <div className="flex gap-2">
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/merchant/listings/${listing.id}`}>Manage</Link>
                  </Button>
                  <Button asChild variant="outline" size="sm">
                    <Link href={`/merchant/listings/${listing.id}/edit`}>Edit</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
