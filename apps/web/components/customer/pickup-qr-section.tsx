"use client";

import { createServices, type PickupTokenResponse } from "@savebite/api-client";
import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import { Alert } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatPickupWindow } from "@/lib/marketplace";
import { formatDateTime } from "@/lib/order-labels";
import { isPickupQrEligible, pickupIneligibilityReason } from "@/lib/pickup";

/**
 * Customer pickup QR (W5, M8). The token lives
 * in this component's memory only: it is never
 * written to localStorage, sessionStorage,
 * cookies, or the URL, never logged, and never
 * shown as visible text — only the QR code
 * carries it. Leaving the view, hiding the code,
 * or changing order clears it. The customer must
 * deliberately request a code; loading this
 * section never issues one. Requesting a fresh
 * code invalidates the previous unused code, and
 * the UI says so before the request is made.
 * Eligibility here is only a display gate: the
 * backend re-checks status, payment, window and
 * ownership on every issuance.
 */
export function PickupQrSection({
  orderId,
  orderNumber,
  orderStatus,
  paymentStatus,
  storeName,
  storeAddress,
  pickupStartsAt,
  pickupEndsAt,
  pickupInstructions,
}: {
  orderId: string;
  orderNumber: string;
  orderStatus: string;
  paymentStatus: string;
  storeName: string;
  storeAddress: string;
  pickupStartsAt: string;
  pickupEndsAt: string;
  pickupInstructions?: string | null;
}) {
  const [issued, setIssued] = useState<PickupTokenResponse | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [issueError, setIssueError] = useState<string | null>(null);
  const issuingRef = useRef(false);

  // Leaving the QR view (unmount or a different
  // order) drops the in-memory token immediately.
  useEffect(() => {
    setIssued(null);
    setIssueError(null);
    return () => {
      setIssued(null);
    };
  }, [orderId]);

  const eligible = isPickupQrEligible(orderStatus, paymentStatus);

  async function requestCode() {
    // Duplicate-click guard: the button is also
    // disabled while issuing, but the ref covers
    // rapid double activation before re-render.
    if (issuingRef.current) return;
    issuingRef.current = true;
    setIssuing(true);
    setIssueError(null);
    try {
      const response = await createServices(createBrowserApiClient()).pickup.issuePickupToken(
        orderId,
      );
      setIssued(response);
    } catch (err) {
      if (issued) {
        // A replacement request may have
        // invalidated the old code server-side
        // even though its response was lost, so
        // the old code must not stay on screen
        // as if it still worked.
        setIssued(null);
        setIssueError(
          "Could not get a fresh code, and the previous code may no longer be valid. Please request a new code.",
        );
      } else {
        // The backend message is shown as-is; a
        // failed first request leaves no code to
        // misrepresent, and the customer can try
        // again deliberately.
        setIssueError(
          err instanceof Error ? err.message : "Could not get a pickup code. Please try again.",
        );
      }
    } finally {
      setIssuing(false);
      issuingRef.current = false;
    }
  }

  function hideCode() {
    setIssued(null);
    setIssueError(null);
  }

  if (!eligible) {
    return (
      <div className="mt-3 border-t pt-3">
        <p className="text-sm text-muted-foreground">
          {pickupIneligibilityReason(orderStatus, paymentStatus)}
        </p>
      </div>
    );
  }

  if (!issued) {
    return (
      <div className="mt-3 flex flex-col gap-2 border-t pt-3">
        <p className="text-sm text-muted-foreground">
          When you reach the store, show the merchant your pickup QR code. Request it only when
          you are ready — the code is shown once and is not stored anywhere.
        </p>
        <div>
          <Button onClick={() => void requestCode()} disabled={issuing}>
            {issuing ? "Requesting QR code…" : "Show Pickup QR"}
          </Button>
        </div>
        {issueError ? <Alert variant="error">{issueError}</Alert> : null}
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col items-center gap-3 border-t pt-4 text-center">
      <p className="text-sm font-medium">
        Show this QR code to the merchant at {issued.store_name || storeName}
      </p>
      <div
        role="img"
        aria-label={`Pickup QR code for order ${orderNumber} at ${issued.store_name || storeName}`}
        className="rounded-lg border bg-white p-4"
      >
        <QRCodeSVG
          value={issued.qr_payload}
          size={256}
          bgColor="#ffffff"
          fgColor="#000000"
          level="M"
          aria-label={`Pickup QR code for order ${orderNumber}`}
        />
      </div>
      <p className="sr-only">
        Pickup QR code for order {orderNumber}. Show this code to the merchant; the code itself is
        not shown as text.
      </p>
      <div className="text-sm">
        <p className="font-medium">Order {orderNumber}</p>
        <p className="text-muted-foreground">{storeAddress}</p>
        <p className="text-muted-foreground">
          Pickup {formatPickupWindow(pickupStartsAt, pickupEndsAt, "Asia/Kolkata")}
        </p>
        <p className="text-muted-foreground">
          This code expires {formatDateTime(issued.expires_at)}.
        </p>
        {issued.pickup_instructions || pickupInstructions ? (
          <p className="text-muted-foreground">
            Instructions: {issued.pickup_instructions || pickupInstructions}
          </p>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground">
        Do not share this QR code with anyone else. Anyone holding it could collect your order.
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        <Button variant="outline" onClick={hideCode}>
          Hide QR code
        </Button>
        <Button
          variant="outline"
          onClick={() => void requestCode()}
          disabled={issuing}
          title="Requesting a fresh code invalidates the current unused code."
        >
          {issuing ? "Requesting…" : "Request a fresh code"}
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Requesting a fresh code invalidates the current unused code — the old code will stop
        working. If a code was lost or never arrived, request a fresh one.
      </p>
      {issueError ? <Alert variant="error">{issueError}</Alert> : null}
    </div>
  );
}
