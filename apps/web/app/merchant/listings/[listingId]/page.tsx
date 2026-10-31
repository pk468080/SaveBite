"use client";

import {
  createServices,
  type ListingDetail,
  type ListingImage,
} from "@savebite/api-client";
import Link from "next/link";
import { use, useEffect, useState } from "react";
import { StatusBadge } from "@/components/merchant/status-badge";
import { allowedListingActions, listingStatusLabel, listingTypeLabel } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatDateTime } from "@/lib/order-labels";
import { formatINR } from "@/lib/marketplace";
import { createClient as createBrowserSupabase } from "@/lib/supabase/client";

const ACTION_LABELS: Record<string, string> = {
  publish: "Publish",
  pause: "Pause",
  resume: "Resume",
  cancel: "Cancel",
};

/**
 * Listing detail (W4, M4). Transitions go only
 * through the dedicated endpoints, and the page
 * shows the backend refusal when a transition is
 * not allowed. Images: the file is uploaded by
 * the caller to the listing-media bucket at
 * <listing_id>/<file> (the bucket policy allows
 * store operators only), then registered through
 * POST /v1/listings/{id}/images. Images have no
 * UPDATE or DELETE policy, so once registered
 * they cannot be edited or removed from here —
 * the page says so instead of pretending.
 */
export default function ListingDetailPage({ params }: { params: Promise<{ listingId: string }> }) {
  const { listingId } = use(params);
  const [listing, setListing] = useState<ListingDetail | null>(null);
  const [images, setImages] = useState<ListingImage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [altText, setAltText] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);

  async function load() {
    const services = createServices(createBrowserApiClient());
    const [detail, imageList] = await Promise.all([
      services.listings.getListing(listingId),
      services.listings.listImages(listingId),
    ]);
    setListing(detail);
    setImages(imageList);
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    load()
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingId]);

  async function runAction(action: string) {
    if (action === "cancel" && !confirmCancel) {
      setConfirmCancel(true);
      return;
    }
    setConfirmCancel(false);
    setActionError(null);
    setActing(true);
    try {
      const services = createServices(createBrowserApiClient());
      const updated =
        action === "publish"
          ? await services.listings.publish(listingId)
          : action === "pause"
            ? await services.listings.pause(listingId)
            : action === "resume"
              ? await services.listings.resume(listingId)
              : await services.listings.cancel(listingId);
      setListing(updated);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "That change was refused.");
    } finally {
      setActing(false);
    }
  }

  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploadError(null);
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
      setUploadError("Only JPG, PNG and WebP images are allowed by the listing-media bucket.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setUploadError("Images must be 5 MB or smaller.");
      return;
    }
    setUploading(true);
    try {
      const safeName = file.name.replace(/[^A-Za-z0-9._-]/g, "_");
      const path = `${listingId}/${Date.now()}-${safeName}`;
      const supabase = createBrowserSupabase();
      const { error: uploadErr } = await supabase.storage
        .from("listing-media")
        .upload(path, file, { contentType: file.type, upsert: false });
      if (uploadErr) throw new Error(uploadErr.message);
      const registered = await createServices(createBrowserApiClient()).listings.addImage(listingId, {
        storage_path: path,
        alt_text: altText.trim() || null,
        display_order: images.length,
      });
      setImages((current) => [...current, registered]);
      setAltText("");
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Image could not be uploaded.");
    } finally {
      setUploading(false);
    }
  }

  if (loading) return <LoadingState label="Loading listing" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!listing) {
    return (
      <EmptyState
        title="Listing not found"
        description="This listing is not among your authorized stores, or it does not exist."
      >
        <Button asChild>
          <Link href="/merchant/listings">Back to listings</Link>
        </Button>
      </EmptyState>
    );
  }

  const actions = allowedListingActions(listing.status);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">{listing.title}</h1>
          <p className="text-sm text-muted-foreground">{listingTypeLabel(listing.listing_type)}</p>
        </div>
        <StatusBadge status={listing.status} label={listingStatusLabel(listing.status)} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Details and inventory</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {listing.description ? <p>{listing.description}</p> : null}
          {listing.contents_description ? <p>Contents: {listing.contents_description}</p> : null}
          <p>
            Price {formatINR(listing.selling_price)} · Reference {formatINR(listing.reference_value)} ·
            Total {listing.total_quantity} · Reserved {listing.reserved_quantity} · Sold{" "}
            {listing.sold_quantity} · Available {listing.available_quantity}
          </p>
          <p className="text-muted-foreground">
            Available quantity is the database generated value (total − reserved − sold), shown as
            returned. It is read-only here.
          </p>
          <p>Sale: {formatDateTime(listing.sale_starts_at ?? listing.created_at ?? "")} → {formatDateTime(listing.sale_ends_at)}</p>
          <p>
            Pickup: {formatDateTime(listing.pickup_starts_at)} → {formatDateTime(listing.pickup_ends_at)}
          </p>
          <p>Dietary: {listing.dietary_classification.replace("_", " ")}</p>
          {listing.allergen_codes.length > 0 ? <p>Allergens: {listing.allergen_codes.join(", ")}</p> : null}
          {listing.storage_instructions ? <p>Storage: {listing.storage_instructions}</p> : null}
          {listing.food_safety_notes ? <p>Food safety: {listing.food_safety_notes}</p> : null}
          {listing.published_at ? <p>Published: {formatDateTime(listing.published_at)}</p> : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link href={`/merchant/listings/${listing.id}/edit`}>Edit details</Link>
            </Button>
            {actions.map((action) => (
              <Button
                key={action}
                variant={action === "cancel" ? "destructive" : "outline"}
                disabled={acting}
                onClick={() => void runAction(action)}
              >
                {action === "cancel" && confirmCancel ? "Confirm cancel" : ACTION_LABELS[action]}
              </Button>
            ))}
          </div>
          {actionError ? <Alert variant="error">{actionError}</Alert> : null}
          {confirmCancel ? (
            <p className="text-sm text-muted-foreground">
              Cancelling is final for this listing — tap Confirm cancel to proceed, or choose
              another action to dismiss.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Images</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-sm text-muted-foreground">
            Images are uploaded to the listing-media bucket and then registered. Once registered,
            an image cannot be edited or removed through this portal — the backend has no update
            or delete for listing images.
          </p>
          {images.length === 0 ? (
            <p className="text-sm text-muted-foreground">No images registered yet.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {images.map((image) => (
                <li key={image.id} className="flex flex-wrap justify-between gap-2 border-b pb-2 last:border-0">
                  <span>{image.storage_path}</span>
                  {image.alt_text ? <span className="text-muted-foreground">{image.alt_text}</span> : null}
                </li>
              ))}
            </ul>
          )}
          <label className="flex flex-col gap-1 text-sm">
            <span>Alt text for the next image (optional)</span>
            <input
              className="h-10 rounded-md border border-input bg-background px-3"
              value={altText}
              onChange={(event) => setAltText(event.target.value)}
              maxLength={200}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span>Upload image (JPG, PNG or WebP, max 5 MB)</span>
            <input type="file" accept="image/jpeg,image/png,image/webp" onChange={handleUpload} disabled={uploading} />
          </label>
          {uploading ? <p className="text-sm text-muted-foreground">Uploading…</p> : null}
          {uploadError ? <Alert variant="error">{uploadError}</Alert> : null}
        </CardContent>
      </Card>
    </div>
  );
}
