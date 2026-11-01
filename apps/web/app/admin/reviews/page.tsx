"use client";

import { ApiError, createServices, type AdminReviewRow } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { AdminPager } from "@/components/admin/pager";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { ADMIN_PAGE_SIZE, moderationStatusLabel } from "@/lib/admin";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Review visibility (W6, M11). READ-ONLY, by
 * backend design: there is NO review moderation
 * endpoint and NO moderation RPC, reviews are
 * immutable through the API, and the reviews
 * SELECT policy hides hidden and under_review
 * rows from platform admins. So this page shows
 * what the backend returns (visible reviews in
 * practice), offers the backend-supported
 * filters, and shows NO moderation action
 * buttons — inventing one would be a fake.
 * Moderation is recorded here as a future
 * backend requirement, not simulated.
 */
export default function AdminReviewsPage() {
  const [items, setItems] = useState<AdminReviewRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [rating, setRating] = useState("all");
  const [moderation, setModeration] = useState("all");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDenied(false);
    createServices(createBrowserApiClient())
      .admin.listReviews({
        rating: rating === "all" ? undefined : Number(rating),
        moderation_status: moderation === "all" ? undefined : moderation,
        page,
        page_size: ADMIN_PAGE_SIZE,
      })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
          setDenied(true);
        } else {
          setError(err instanceof Error ? err.message : "Could not load reviews.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [rating, moderation, page]);

  if (denied) return <AccessDenied />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Reviews</h1>
        <p className="text-sm text-muted-foreground">
          Customer reviews visible to platform administrators.
        </p>
      </div>

      <Alert variant="info">
        This list is read-only. The backend has no review moderation endpoint: reviews cannot be
        hidden, restored, edited, or deleted from this portal, and hidden or under-review rows are
        not visible through the API. Moderation needs a separate backend change (a moderation RPC
        plus a policy that lets administrators see non-visible rows).
      </Alert>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Rating</span>
            <Select value={rating} onValueChange={(value) => { setRating(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All ratings</SelectItem>
                {[1, 2, 3, 4, 5].map((value) => (
                  <SelectItem key={value} value={String(value)}>
                    {value} star{value === 1 ? "" : "s"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Moderation status</span>
            <Select value={moderation} onValueChange={(value) => { setModeration(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {["visible", "hidden", "under_review"].map((value) => (
                  <SelectItem key={value} value={value}>
                    {moderationStatusLabel(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        </CardContent>
      </Card>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading reviews" />
      ) : items.length === 0 ? (
        <EmptyState
          title="No reviews found"
          description="Visible reviews appear here. Hidden and under-review rows are not visible through the API."
        />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y p-0">
            {items.map((review) => (
              <div key={review.id} className="flex flex-col gap-1 p-4 text-sm">
                <div className="flex flex-wrap justify-between gap-2">
                  <p className="font-medium">
                    {review.rating} star{review.rating === 1 ? "" : "s"} · {review.store_name}
                  </p>
                  <p className="text-muted-foreground">
                    {moderationStatusLabel(review.moderation_status)} ·{" "}
                    {formatDateTime(review.created_at)}
                  </p>
                </div>
                {review.comment ? <p>{review.comment}</p> : null}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      <AdminPager page={page} pageSize={ADMIN_PAGE_SIZE} total={total} onPage={setPage} />
    </div>
  );
}
