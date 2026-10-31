"use client";

import Link from "next/link";
import { StatusBadge } from "@/components/merchant/status-badge";
import { useMerchantStores } from "@/components/merchant/store-context";
import { merchantStatusLabel, verificationLabel } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";

/**
 * Application status (W4, M3 + M11 review rules).
 * Shows the actual merchant status and verification
 * status returned by GET /v1/merchants. Approval
 * needs a verified status plus a verified, current
 * FSSAI document on the admin side — the portal
 * never claims an application is fully verified
 * unless the backend says so, and merchants cannot
 * approve their own application here.
 */
export default function MerchantApplicationPage() {
  const { merchants, loading, error } = useMerchantStores();

  if (loading) return <LoadingState label="Loading applications" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (merchants.length === 0) {
    return (
      <EmptyState
        title="No application submitted yet"
        description="Submit your business details once, then track the real review status here."
      >
        <Button asChild>
          <Link href="/merchant/onboarding">Submit an application</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Application status</h1>
        <p className="text-sm text-muted-foreground">
          The status below is what the backend returns — nothing here is approved by this page.
        </p>
      </div>
      <Alert variant="info">
        Document submission is not yet available through this portal: there is no merchant-facing
        document-upload endpoint in the current backend. Admin review requires a verified, current
        FSSAI document before approval, so if your application asks for more information, the
        SaveBite team will request documents through another channel until that endpoint exists.
        This is a known missing backend capability, not something this portal works around with a
        direct storage upload.
      </Alert>
      <div className="grid gap-4">
        {merchants.map((merchant) => (
          <Card key={merchant.id}>
            <CardHeader>
              <CardTitle>{merchant.display_name}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <p className="text-muted-foreground">Legal name: {merchant.legal_name}</p>
              <div className="flex flex-wrap gap-2">
                <StatusBadge status={merchant.status} label={merchantStatusLabel(merchant.status)} />
                <StatusBadge
                  status={merchant.verification_status}
                  label={verificationLabel(merchant.verification_status)}
                />
              </div>
              {merchant.status === "approved" && merchant.verification_status === "verified" ? (
                <p>
                  Approved and verified — you can create stores and listings.
                  <span className="ml-2">
                    <Link className="underline" href="/merchant/stores/new">
                      Create a store
                    </Link>
                  </span>
                </p>
              ) : merchant.status === "pending_review" ? (
                <p className="text-muted-foreground">
                  Pending review. Nothing else is needed from you here until the status changes.
                </p>
              ) : merchant.status === "additional_information_required" ? (
                <p className="text-muted-foreground">
                  The review team needs more information. No document upload exists in this portal
                  yet — wait for their request through another channel.
                </p>
              ) : merchant.status === "rejected" ? (
                <p className="text-muted-foreground">
                  This application was rejected. Submitting a new application starts a fresh review.
                </p>
              ) : null}
            </CardContent>
          </Card>
        ))}
      </div>
      <div>
        <Button asChild variant="outline">
          <Link href="/merchant/onboarding">Submit another application</Link>
        </Button>
      </div>
    </div>
  );
}
