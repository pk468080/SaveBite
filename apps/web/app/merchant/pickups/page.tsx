"use client";

import { createServices, type PickupVerifyResponse } from "@savebite/api-client";
import { useEffect, useRef, useState } from "react";
import { StoreSelector } from "@/components/merchant/store-selector";
import { useMerchantStores } from "@/components/merchant/store-context";
import { isValidPickupToken, normalisePickupToken } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Pickup verification (W4, M8). The backend
 * owns every check: token authenticity, order
 * eligibility, payment capture, store
 * authorization, pickup window and duplicate
 * collection. This page only sends one request
 * per verification and shows what the backend
 * returns. Scanned tokens are never logged,
 * never stored, and the input is cleared after
 * every attempt. Repeated camera frames cannot
 * send duplicate requests: an in-flight guard
 * plus a last-token guard block them.
 */
export default function MerchantPickupsPage() {
  const { stores, selectedStoreId, loading: storesLoading } = useMerchantStores();
  const [tokenInput, setTokenInput] = useState("");
  const [result, setResult] = useState<PickupVerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [cameraOn, setCameraOn] = useState(false);
  const [scannerSupported, setScannerSupported] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const inFlightRef = useRef(false);
  const lastTokenRef = useRef<string | null>(null);

  useEffect(() => {
    setScannerSupported(
      typeof window !== "undefined" &&
        "BarcodeDetector" in window &&
        typeof navigator !== "undefined" &&
        !!navigator.mediaDevices?.getUserMedia,
    );
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  async function verify(rawToken: string) {
    if (!selectedStoreId) {
      setError("Pick a store first — the store in the request is where the customer is standing.");
      return;
    }
    const token = normalisePickupToken(rawToken);
    if (!isValidPickupToken(token)) {
      setError("Enter a pickup token or scan a SaveBite QR code (it starts with SB1:).");
      return;
    }
    if (inFlightRef.current || lastTokenRef.current === token) {
      return;
    }
    inFlightRef.current = true;
    lastTokenRef.current = token;
    setVerifying(true);
    setError(null);
    setResult(null);
    setTokenInput("");
    try {
      const verified = await createServices(createBrowserApiClient()).pickup.verifyPickupToken({
        store_id: selectedStoreId,
        pickup_token: token,
      });
      setResult(verified);
    } catch (err) {
      // The backend collapses distinct failures
      // into safe messages on purpose; they are
      // shown as-is, without guessing which case.
      setError(err instanceof Error ? err.message : "Pickup could not be verified.");
    } finally {
      setVerifying(false);
      inFlightRef.current = false;
    }
  }

  async function startCamera() {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
      void scanLoop();
    } catch {
      setCameraError(
        "Camera access was denied or is unavailable. Use manual token entry below — it verifies exactly the same way.",
      );
    }
  }

  function stopCamera() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraOn(false);
  }

  async function scanLoop() {
    const Detector = (window as unknown as { BarcodeDetector?: unknown }).BarcodeDetector as
      | (new (options: { formats: string[] }) => {
          detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>>;
        })
      | undefined;
    if (!Detector || !videoRef.current) return;
    const detector = new Detector({ formats: ["qr_code"] });
    const tick = async () => {
      if (!videoRef.current || !streamRef.current) return;
      try {
        const codes = await detector.detect(videoRef.current);
        const value = codes[0]?.rawValue;
        if (value) {
          await verify(value);
          return;
        }
      } catch {
        // A single unreadable frame is not an
        // error worth showing; keep scanning.
      }
      requestAnimationFrame(() => void tick());
    };
    void tick();
  }

  if (storesLoading) return <LoadingState label="Loading stores" />;
  if (stores.length === 0) {
    return <EmptyState title="No stores yet" description="Create a store first, then verify pickups for it." />;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Verify a pickup</h1>
          <p className="text-sm text-muted-foreground">
            Scan the customer QR code or paste the token. Only a successful backend verification
            collects the order — nothing is marked collected locally.
          </p>
        </div>
        <StoreSelector />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Camera scan</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {!scannerSupported ? (
            <p className="text-sm text-muted-foreground">
              QR scanning is not available in this browser. Manual token entry below works exactly
              the same way.
            </p>
          ) : !cameraOn ? (
            <div>
              <Button onClick={() => void startCamera()}>Start camera</Button>
              <p className="mt-2 text-sm text-muted-foreground">
                The camera is used only after you allow it, and only to read the QR code.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <video ref={videoRef} className="max-h-80 w-full rounded-md bg-black" muted playsInline />
              <div>
                <Button variant="outline" onClick={stopCamera}>
                  Stop camera
                </Button>
              </div>
            </div>
          )}
          {cameraError ? <Alert variant="error">{cameraError}</Alert> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Manual token entry</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              void verify(tokenInput);
            }}
          >
            <label className="flex flex-col gap-1 text-sm">
              <span>Pickup token or QR payload</span>
              <input
                className="h-10 rounded-md border border-input bg-background px-3"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="SB1:… or the token itself"
                autoComplete="off"
              />
            </label>
            <div>
              <Button type="submit" disabled={verifying || !selectedStoreId}>
                {verifying ? "Verifying…" : "Verify pickup"}
              </Button>
            </div>
          </form>
          {error ? <Alert variant="error">{error}</Alert> : null}
          {result ? (
            <div className="mt-4 rounded-md border border-primary/50 bg-primary/10 p-4 text-sm">
              <p className="font-semibold">Pickup confirmed</p>
              <p>Order {result.order_number} · Store {result.store_name}</p>
              <p>Collected {formatDateTime(result.collected_at)} · Status {result.status}</p>
              {result.items.length > 0 ? (
                <p>Items: {result.items.map((item) => `${item.title} × ${item.quantity}`).join(", ")}</p>
              ) : null}
              <div className="mt-3">
                <Button
                  variant="outline"
                  onClick={() => {
                    setResult(null);
                    lastTokenRef.current = null;
                  }}
                >
                  Verify another pickup
                </Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
