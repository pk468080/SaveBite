"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useCart } from "@/components/cart/cart-context";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createPublicServices } from "@/lib/api/public";
import { createClient } from "@/lib/supabase/client";
import { formatINR, listingImageUrl } from "@/lib/marketplace";
import { MAX_QUANTITY } from "@/lib/cart";

/**
 * Cart review (W3). The cart is NOT a reservation:
 * prices shown here are the last-seen listing prices
 * and availability is re-checked at reservation time
 * by the backend. "Refresh prices" re-reads the live
 * listings and flags items that can no longer be
 * reserved, so the customer is never surprised at
 * checkout.
 */
export default function CartPage() {
  const router = useRouter();
  const { cart, setQuantity, remove, clear } = useCart();
  const [mounted, setMounted] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [unavailable, setUnavailable] = useState<Set<string>>(new Set());
  const [refreshError, setRefreshError] = useState<string | null>(null);

  useEffect(() => setMounted(true), []);

  async function refreshPrices() {
    if (!cart) return;
    setRefreshing(true);
    setRefreshError(null);
    try {
      const services = createPublicServices();
      const gone = new Set<string>();
      // Refresh one listing at a time; a failure for one
      // item must not hide the rest of the cart.
      for (const item of cart.items) {
        try {
          const listing = await services.marketplace.getListing(item.listingId);
          if (Number(listing.available_quantity) < item.quantity) gone.add(item.listingId);
          // Prices are refreshed at reservation time by
          // the backend; the stored display price is kept
          // here to avoid rewriting the cart mid-review.
          void listing;
        } catch {
          gone.add(item.listingId);
        }
      }
      setUnavailable(gone);
    } catch {
      setRefreshError("Could not refresh prices. Your cart is unchanged — try again.");
    } finally {
      setRefreshing(false);
    }
  }

  if (!mounted) return <LoadingState label="Loading your cart…" />;

  if (!cart || cart.items.length === 0) {
    return (
      <EmptyState
        title="Your cart is empty"
        description="Browse surplus food nearby and add a Surprise Bag or an item to your cart."
        >
        <Button asChild><Link href="/marketplace">Explore food</Link></Button>
      </EmptyState>
    );
  }

  const displayTotal = cart.items.reduce(
    (sum, item) => sum + Number(item.sellingPrice) * item.quantity,
    0,
  );

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-3xl font-bold">Your cart</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          One store per reservation: {cart.storeName}. Nothing is reserved until
          the backend confirms your reservation at checkout.
        </p>
      </div>

      {refreshError ? <Alert variant="error">{refreshError}</Alert> : null}
      {unavailable.size > 0 ? (
        <Alert variant="error">
          {unavailable.size === 1 ? "An item" : "Some items"} in your cart can no longer be
          reserved at the chosen quantity. Remove {unavailable.size === 1 ? "it" : "them"} or
          lower the quantity before checkout.
        </Alert>
      ) : null}

      <Card>
        <CardContent className="flex flex-col divide-y p-0">
          {cart.items.map((item) => (
            <div key={item.listingId} className="flex gap-4 p-4">
              <div className="relative h-20 w-20 shrink-0 overflow-hidden rounded-md bg-muted">
                {item.imagePath ? (
                  <Image src={listingImageUrl(item.imagePath)} alt={item.title} fill className="object-cover" />
                ) : null}
              </div>
              <div className="flex flex-1 flex-col gap-1">
                <div className="flex items-start justify-between gap-2">
                  <Link href={`/marketplace/${item.listingId}`} className="font-medium hover:underline">
                    {item.title}
                  </Link>
                  <button
                    type="button"
                    onClick={() => remove(item.listingId)}
                    className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                  >
                    Remove
                  </button>
                </div>
                <p className="text-sm text-muted-foreground">
                  {formatINR(item.sellingPrice, item.currency)} each
                </p>
                {unavailable.has(item.listingId) ? (
                  <p role="alert" className="text-sm text-destructive">
                    No longer available at this quantity.
                  </p>
                ) : null}
                <div className="mt-auto flex items-center gap-2">
                  <label htmlFor={`qty-${item.listingId}`} className="sr-only">
                    Quantity for this item
                  </label>
                  <input
                    id={`qty-${item.listingId}`}
                    type="number"
                    min={1}
                    max={MAX_QUANTITY}
                    value={item.quantity}
                    onChange={(event) => setQuantity(item.listingId, Number(event.target.value))}
                    className="h-9 w-20 rounded-md border bg-background px-2 text-sm"
                  />
                  <span className="ml-auto font-medium">
                    {formatINR(Number(item.sellingPrice) * item.quantity, item.currency)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="flex justify-between text-sm">
            <span>Display total (backend total wins at checkout)</span>
            <span className="font-semibold">{formatINR(displayTotal)}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={refreshPrices} disabled={refreshing}>
              {refreshing ? "Refreshing…" : "Refresh availability"}
            </Button>
            <Button variant="outline" onClick={clear}>
              Clear cart
            </Button>
            <Button
              className="ml-auto"
              disabled={unavailable.size > 0}
              onClick={async () => {
                // Preserve the destination: an
                // unauthenticated customer goes to
                // sign-in with ?next= so checkout
                // resumes after login; the cart itself
                // survives in localStorage either way.
                const supabase = createClient();
                const { data } = await supabase.auth.getSession();
                router.push(
                  data.session ? "/customer/checkout" : "/sign-in?next=/customer/checkout",
                );
              }}
            >
              Continue to checkout
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Pickup only — no delivery. You will sign in (or create an account) before
            the reservation is created.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
