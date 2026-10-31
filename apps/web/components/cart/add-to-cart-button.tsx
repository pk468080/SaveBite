"use client";

import Link from "next/link";
import { useState } from "react";
import { useCart } from "@/components/cart/cart-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { MarketplaceListing } from "@savebite/api-client";

/**
 * Add-to-cart with the same-store guard. Guests may add
 * items; sign-in is only required at checkout. When the
 * cart already holds another store's items, the customer
 * must deliberately choose to replace the cart — the old
 * items are never silently discarded.
 */
export function AddToCartButton({ listing }: { listing: MarketplaceListing }) {
  const { add, replace } = useCart();
  const [quantity, setQuantity] = useState(1);
  const [pendingStore, setPendingStore] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  const item = {
    listingId: listing.id,
    storeId: listing.store.id,
    storeName: listing.store.name,
    title: listing.title,
    sellingPrice: listing.selling_price,
    currency: listing.currency,
    imagePath: listing.images[0]?.storage_path ?? null,
  };

  function handleAdd() {
    setAdded(false);
    const result = add(item, quantity);
    if ("needsReplace" in result) {
      setPendingStore(result.existingStoreName);
      return;
    }
    if ("ok" in result) setAdded(true);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <label htmlFor="cart-quantity" className="text-sm font-medium">
          Quantity
        </label>
        <input
          id="cart-quantity"
          type="number"
          min={1}
          max={20}
          value={quantity}
          onChange={(event) => setQuantity(Number(event.target.value))}
          className="h-10 w-20 rounded-md border bg-background px-3 text-sm"
        />
        <span className="text-xs text-muted-foreground">Max 20 per item</span>
      </div>
      <Button onClick={handleAdd}>Add to cart</Button>
      {added ? (
        <p role="status" className="text-sm text-primary">
          Added. <Link href="/cart" className="font-medium underline underline-offset-4">Review cart</Link>
        </p>
      ) : null}
      <Dialog open={pendingStore !== null} onOpenChange={(open) => !open && setPendingStore(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Replace your cart?</DialogTitle>
            <DialogDescription>
              Your cart already has items from {pendingStore}. A reservation can only
              contain items from one store, so adding this item means clearing the
              existing cart first.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button variant="outline" onClick={() => setPendingStore(null)}>
              Keep existing cart
            </Button>
            <Button
              onClick={() => {
                replace(item, quantity);
                setPendingStore(null);
                setAdded(true);
              }}
            >
              Replace cart
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
