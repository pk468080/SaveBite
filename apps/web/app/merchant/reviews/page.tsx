"use client";

import { createServices, type PublicReview, type StoreRatingSummary } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Reviews (W4, M9). Only PUBLIC (visible)
 * reviews are shown — the list and the summary
 * are computed over the same visible set, so they
 * always agree. No reviewer names exist in the
 * public contract, so none are shown or invented.
 * Merchants cannot edit, delete, hide or reply
 * to reviews from this portal: no such endpoint
 * exists, and this page offers no such action.
 */
export default function MerchantReviewsPage() {
  const { stores, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [summary, setSummary] = useState<StoreRatingSummary | null>(null);
  const [reviews, setReviews] = useState<PublicReview[]>([]);
  const [total, setTotal] = useState(0);
  const [ratingFilter, setRatingFilter] = useState("");
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
    Promise.all([
      services.reviews.getStoreRatingSummary(selectedStoreId),
      services.reviews.listStoreReviews(selectedStoreId, {
        rating: ratingFilter ? Number(ratingFilter) : undefined,
        page_size: 20,
      }),
    ])
      .then(([summaryData, reviewData]) => {
        if (!cancelled) {
          setSummary(summaryData);
          setReviews(reviewData.items);
          setTotal(reviewData.total);
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
  }, [storesLoading, selectedStoreId, ratingFilter]);

  if (storesLoading) return <LoadingState label="Loading stores" />;
  if (stores.length === 0) {
    return <EmptyState title="No stores yet" description="Reviews appear once your stores receive them." />;
  }
  if (!selectedStoreId) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold">Reviews</h1>
        <p className="text-sm text-muted-foreground">Pick a store to see its visible reviews.</p>
        <StoreSelector />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Reviews</h1>
        <div className="flex items-center gap-3">
          <StoreSelector />
          <label className="flex items-center gap-2 text-sm">
            <span className="text-muted-foreground">Stars</span>
            <select
              className="h-10 rounded-md border border-input bg-background px-3"
              value={ratingFilter}
              onChange={(event) => setRatingFilter(event.target.value)}
            >
              <option value="">All</option>
              {[5, 4, 3, 2, 1].map((stars) => (
                <option key={stars} value={stars}>
                  {stars}★
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading reviews" />
      ) : (
        <>
          {summary ? (
            <Card>
              <CardHeader>
                <CardTitle>{summary.store_name}</CardTitle>
              </CardHeader>
              <CardContent>
                {summary.average_rating === null ? (
                  <p className="text-sm text-muted-foreground">
                    No visible reviews yet — no average is shown rather than inventing one.
                  </p>
                ) : (
                  <p className="text-sm">
                    Average {summary.average_rating.toFixed(2)} from {summary.total_reviews} visible
                    reviews · 5★ {summary.five_star} · 4★ {summary.four_star} · 3★{" "}
                    {summary.three_star} · 2★ {summary.two_star} · 1★ {summary.one_star}
                  </p>
                )}
              </CardContent>
            </Card>
          ) : null}
          {reviews.length === 0 ? (
            <EmptyState title="No visible reviews" description="Hidden or under-review feedback is never shown as public content." />
          ) : (
            <div className="grid gap-4">
              <p className="text-sm text-muted-foreground">{total} visible review(s) in total.</p>
              {reviews.map((review) => (
                <Card key={review.id}>
                  <CardContent className="flex flex-col gap-1 pt-6 text-sm">
                    <p className="font-semibold">{"★".repeat(review.rating)}{"☆".repeat(5 - review.rating)}</p>
                    {review.comment ? <p>{review.comment}</p> : <p className="text-muted-foreground">No written feedback.</p>}
                    <p className="text-muted-foreground">{formatDateTime(review.created_at)}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
