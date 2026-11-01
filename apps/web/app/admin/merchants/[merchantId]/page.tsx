"use client";

import { ApiError, createServices, type AdminMerchantDetail } from "@savebite/api-client";
import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { MerchantReviewPanel } from "@/components/admin/merchant-review-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { merchantStatusLabel, merchantVerificationLabel, storeStatusLabel } from "@/lib/admin";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Merchant application detail + decision (W6,
 * M11). All fields come from GET
 * /v1/admin/merchants/{id}. The decision panel
 * calls the review API and this page re-reads
 * the merchant afterwards, so the shown status
 * is always the backend's answer, never an
 * optimistic local edit.
 */
export default function AdminMerchantDetailPage({
  params,
}: {
  params: Promise<{ merchantId: string }>;
}) {
  const { merchantId } = use(params);
  const [merchant, setMerchant] = useState<AdminMerchantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setDenied(false);
    try {
      const data = await createServices(createBrowserApiClient()).admin.getMerchantDetail(merchantId);
      setMerchant(data);
    } catch (err) {
      if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
        setDenied(true);
      } else if (err instanceof ApiError && err.status === 404) {
        setMerchant(null);
      } else {
        setError(err instanceof Error ? err.message : "Could not load this merchant.");
      }
    } finally {
      setLoading(false);
    }
  }, [merchantId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingState label="Loading merchant" />;
  if (denied) return <AccessDenied />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (!merchant) {
    return (
      <EmptyState title="Merchant not found" description="This merchant does not exist.">
        <Button asChild>
          <Link href="/admin/merchants">Back to merchants</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">{merchant.display_name}</h1>
        <p className="text-sm text-muted-foreground">
          {merchantStatusLabel(merchant.status)} ·{" "}
          {merchantVerificationLabel(merchant.verification_status)}
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Application details</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p>
            <span className="text-muted-foreground">Legal name: </span>
            {merchant.legal_name}
          </p>
          <p>
            <span className="text-muted-foreground">Business type: </span>
            {merchant.business_type}
          </p>
          {merchant.business_email ? (
            <p>
              <span className="text-muted-foreground">Business email: </span>
              {merchant.business_email}
            </p>
          ) : null}
          {merchant.business_phone ? (
            <p>
              <span className="text-muted-foreground">Business phone: </span>
              {merchant.business_phone}
            </p>
          ) : null}
          {merchant.onboarding_notes ? (
            <p>
              <span className="text-muted-foreground">Onboarding notes: </span>
              {merchant.onboarding_notes}
            </p>
          ) : null}
          <p>
            <span className="text-muted-foreground">Applied: </span>
            {formatDateTime(merchant.created_at)}
          </p>
          {merchant.approved_at ? (
            <p>
              <span className="text-muted-foreground">Approved: </span>
              {formatDateTime(merchant.approved_at)}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Stores ({merchant.stores.length})</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col divide-y p-0">
          {merchant.stores.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">No stores yet.</p>
          ) : (
            merchant.stores.map((store) => (
              <div key={store.id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
                <div>
                  <Link href={`/admin/stores/${store.id}`} className="font-medium underline underline-offset-4">
                    {store.name}
                  </Link>
                  <p className="text-muted-foreground">
                    {store.city} {store.pincode} · {store.listing_count} listing(s) ·{" "}
                    {store.order_count} order(s)
                  </p>
                </div>
                <p className="font-medium">{storeStatusLabel(store.status)}</p>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <MerchantReviewPanel merchantId={merchant.id} onReviewed={() => void load()} />

      <div>
        <Button asChild variant="outline">
          <Link href="/admin/merchants">Back to merchants</Link>
        </Button>
      </div>
    </div>
  );
}
