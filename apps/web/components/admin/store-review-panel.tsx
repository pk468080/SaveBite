"use client";

import { createServices } from "@savebite/api-client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";

/**
 * Store activation panel (W6, M11). The backend
 * supports exactly one store decision: activate
 * or deactivate. Activation requires an approved
 * and verified merchant, a store location, and
 * store hours — all enforced by the backend RPC.
 * Nothing is updated locally: the panel calls
 * the review API and asks the parent to re-read
 * the store. Duplicate submissions are blocked
 * while a request is in flight.
 */
export function StoreReviewPanel({
  storeId,
  currentActive,
  onReviewed,
}: {
  storeId: string;
  currentActive: boolean;
  onReviewed: () => void;
}) {
  const [activate, setActivate] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function submit() {
    if (activate === null || acting) return;
    setActing(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await createServices(createBrowserApiClient()).admin.reviewStore(storeId, {
        activate,
        reason: reason.trim() || undefined,
      });
      setSuccess(
        result.activated
          ? "Store activated. The details above have been refreshed from the backend."
          : "Store deactivated. The details above have been refreshed from the backend.",
      );
      setActivate(null);
      setReason("");
      onReviewed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The store decision could not be saved.");
    } finally {
      setActing(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Store activation</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        <p className="text-muted-foreground">
          Activation requires an approved and verified merchant, a store location, and store
          hours. All three are enforced by the backend — if any is missing, activation fails
          with the backend&apos;s reason, and nothing changes here.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={acting || currentActive} onClick={() => setActivate(true)}>
            Activate
          </Button>
          <Button variant="outline" disabled={acting || !currentActive} onClick={() => setActivate(false)}>
            Deactivate
          </Button>
        </div>
        {activate !== null ? (
          <div className="flex flex-col gap-2 rounded-md border p-3">
            <p>
              You are about to <strong>{activate ? "activate" : "deactivate"}</strong> this store.
            </p>
            <label className="flex flex-col gap-1">
              <span>Reason (optional, max 1000 characters)</span>
              <textarea
                className="min-h-20 rounded-md border border-input bg-background px-3 py-2"
                value={reason}
                maxLength={1000}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Why this decision, if needed"
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button disabled={acting} onClick={() => void submit()}>
                {acting ? "Saving…" : `Confirm ${activate ? "activation" : "deactivation"}`}
              </Button>
              <Button variant="outline" disabled={acting} onClick={() => setActivate(null)}>
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
