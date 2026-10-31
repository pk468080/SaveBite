"use client";

import { createServices, type MarketplaceCategory } from "@savebite/api-client";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import { EMPTY_LISTING_FORM, ListingForm, listingFormToBody } from "@/components/merchant/listing-form";
import type { ListingFormValues } from "@/lib/merchant";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Edit listing (W4, M4). PATCH sends only the
 * updateable columns; status, store, listing
 * type, currency and inventory counters are
 * immutable through this API and are never sent.
 * Cancelled and expired listings are refused by
 * the backend, and that refusal is shown as-is.
 */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export default function EditListingPage({ params }: { params: Promise<{ listingId: string }> }) {
  const { listingId } = use(params);
  const router = useRouter();
  const [initial, setInitial] = useState<ListingFormValues | null>(null);
  const [categories, setCategories] = useState<MarketplaceCategory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const services = createServices(createBrowserApiClient());
        const [detail, cats] = await Promise.all([
          services.listings.getListing(listingId),
          services.merchants.listCategories(),
        ]);
        if (cancelled) return;
        setCategories(cats);
        setInitial({
          ...EMPTY_LISTING_FORM,
          listing_type: detail.listing_type,
          category_id: detail.category_id ?? "",
          title: detail.title,
          description: detail.description ?? "",
          contents_description: detail.contents_description ?? "",
          reference_value: detail.reference_value,
          selling_price: detail.selling_price,
          total_quantity: String(detail.total_quantity),
          sale_starts_at: toLocalInput(detail.sale_starts_at),
          sale_ends_at: toLocalInput(detail.sale_ends_at),
          pickup_starts_at: toLocalInput(detail.pickup_starts_at),
          pickup_ends_at: toLocalInput(detail.pickup_ends_at),
          prepared_at: toLocalInput(detail.prepared_at),
          best_before_at: toLocalInput(detail.best_before_at),
          allergen_codes: detail.allergen_codes.join(", "),
          dietary_classification: detail.dietary_classification,
          storage_instructions: detail.storage_instructions ?? "",
          food_safety_notes: detail.food_safety_notes ?? "",
        });
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Listing could not be loaded.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [listingId]);

  if (loading) return <LoadingState label="Loading listing" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!initial) return <Alert variant="error">Listing could not be loaded.</Alert>;

  async function handleSave(values: ListingFormValues) {
    const body = listingFormToBody(values);
    // listing_type is immutable on PATCH; the
    // form keeps it for display, but it is not sent.
    delete body.listing_type;
    await createServices(createBrowserApiClient()).listings.updateListing(listingId, body);
    router.push(`/merchant/listings/${listingId}`);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Edit listing</h1>
        <p className="text-sm text-muted-foreground">
          Status, store, listing type and inventory counters cannot be changed here — those are
          backend-controlled. Use the listing page for publish, pause, resume and cancel.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Listing details</CardTitle>
        </CardHeader>
        <CardContent>
          <ListingForm
            initial={initial}
            categories={categories}
            submitLabel="Save changes"
            onSubmit={handleSave}
            lockType
          />
        </CardContent>
      </Card>
    </div>
  );
}
