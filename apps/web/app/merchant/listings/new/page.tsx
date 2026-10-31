"use client";

import { createServices, type MarketplaceCategory } from "@savebite/api-client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { EMPTY_LISTING_FORM, ListingForm, listingFormToBody } from "@/components/merchant/listing-form";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import type { ListingFormValues } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Create listing (W4, M4). The backend always
 * creates a draft — publishing is a separate
 * step on the listing page, after images and
 * details are ready. Listing writes need owner,
 * admin, store_manager or inventory_manager on
 * the backend; other members get its refusal.
 */
export default function NewListingPage() {
  const router = useRouter();
  const { stores, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [categories, setCategories] = useState<MarketplaceCategory[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    createServices(createBrowserApiClient())
      .merchants.listCategories()
      .then(setCategories)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (storesLoading) return <LoadingState label="Loading stores" />;
  if (stores.length === 0) {
    return (
      <EmptyState title="No stores yet" description="Create a store first, then add listings to it.">
        <Button asChild>
          <Link href="/merchant/stores/new">Create a store</Link>
        </Button>
      </EmptyState>
    );
  }
  if (!selectedStoreId) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Create a listing</h1>
        <p className="text-sm text-muted-foreground">Pick the store this listing belongs to.</p>
        <StoreSelector />
      </div>
    );
  }

  async function handleCreate(values: ListingFormValues) {
    const created = await createServices(createBrowserApiClient()).listings.createListing(
      selectedStoreId as string,
      listingFormToBody(values),
    );
    router.push(`/merchant/listings/${created.id}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Create a listing</h1>
          <p className="text-sm text-muted-foreground">
            The listing is created as a draft. Publish it from its page when it is ready.
          </p>
        </div>
        <StoreSelector />
      </div>
      {error ? <Alert variant="error">{error}</Alert> : null}
      <Card>
        <CardHeader>
          <CardTitle>Listing details</CardTitle>
        </CardHeader>
        <CardContent>
          <ListingForm
            initial={EMPTY_LISTING_FORM}
            categories={categories}
            submitLabel="Create draft listing"
            onSubmit={handleCreate}
          />
        </CardContent>
      </Card>
    </div>
  );
}
