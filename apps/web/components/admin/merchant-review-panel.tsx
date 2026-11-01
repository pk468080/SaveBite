"use client";

import { createServices } from "@savebite/api-client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Merchant application decision panel (W6, M11).
 * Only the two actions the backend supports are
 * offered: approve and reject. Nothing is updated
 * locally: the panel calls the review API, shows
 * the backend result, and asks the parent to
 * re-read the merchant. Duplicate submissions
 * are blocked while a request is in flight, and
 * the action requires a deliberate confirmation.
 * Approval preconditions (verified status plus a
 * verified, current FSSAI document) are enforced
 * by the backend RPC, not here — a failed
 * approval shows the backend's reason.
 */
export function MerchantReviewPanel({
  merchantId,
  onReviewed,
}: {
  merchantId: string;
  onReviewed: () => void;
}) {
  const [action, setAction] = useState<"approve" | "reject" | null>(null);
  const [notes, setNotes] = useState("");
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit() {
    if (!action || acting) return;
    setActing(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await createServices(createBrowserApiClient()).admin.reviewMerchant(
        merchantId,
        { action, review_notes: notes.trim() || undefined },
      );
      setSuccess(
        `Application ${result.status} (verification: ${result.verification_status}). The details above have been refreshed from the backend.`,
      );
      setAction(null);
      setNotes("");
      onReviewed();
    } catch (err) {
      // A failed action never changes the shown
      // status: the parent data is untouched.
      setError(err instanceof Error ? err.message : "The review could not be saved.");
    } finally {
      setActing(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review application</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p className="text-muted-foreground">
          Approval requires verification status verified and a verified, current FSSAI document.
          Both are enforced by the backend — if either is missing, approval fails with the
          backend&apos;s reason, and nothing changes here.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={acting} onClick={() => setAction("approve")}>
            Approve
          </Button>
          <Button variant="outline" disabled={acting} onClick={() => setAction("reject")}>
            Reject
          </Button>
        </div>
        {action ? (
          <div className="flex flex-col gap-2 rounded-md border p-3">
            <p>
              You are about to <strong>{action}</strong> this application.
            </p>
            <label className="flex flex-col gap-1">
              <span>Review notes (optional, max 1000 characters)</span>
              <textarea
                className="min-h-20 rounded-md border border-input bg-background px-3 py-2"
                value={notes}
                maxLength={1000}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Why this decision, if needed"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button disabled={acting} onClick={() => void submit()}>
                {acting ? "Saving…" : `Confirm ${action}`}
              </Button>
              <Button variant="outline" disabled={acting} onClick={() => setAction(null)}>
                Cancel
              </Button>
            </div>
          </div>
        ) : null}
        {error ? <Alert variant="error">{error}</Alert> : null}
        {success ? <Alert variant="success">{success}</Alert> : null}
      </CardContent>
    </Card>
  );
}
