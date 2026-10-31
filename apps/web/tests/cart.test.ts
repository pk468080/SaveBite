import { describe, expect, it } from "vitest";
import {
  addToCart,
  cartDisplayTotal,
  cartFingerprint,
  cartItemCount,
  parseCart,
  removeFromCart,
  replaceCart,
  setCartQuantity,
} from "@/lib/cart";

const bag = {
  listingId: "listing-1",
  storeId: "store-1",
  storeName: "Bakery One",
  title: "Surprise Bag",
  sellingPrice: "99.00",
  currency: "INR",
};

const item = {
  listingId: "listing-2",
  storeId: "store-2",
  storeName: "Cafe Two",
  title: "Sandwich Box",
  sellingPrice: "50.00",
  currency: "INR",
};

describe("cart", () => {
  it("adds an item and computes count and display total", () => {
    const result = addToCart(null, bag, 2);
    expect(result).toMatchObject({ ok: true });
    if (!("ok" in result)) throw new Error("expected ok");
    expect(cartItemCount(result.cart)).toBe(2);
    expect(cartDisplayTotal(result.cart)).toBe(198);
  });

  it("refuses a second store and asks for a deliberate replacement", () => {
    const first = addToCart(null, bag, 1);
    if (!("ok" in first)) throw new Error("expected ok");
    const second = addToCart(first.cart, item, 1);
    expect(second).toEqual({ needsReplace: true, existingStoreName: "Bakery One" });
    const replaced = replaceCart(item, 1);
    expect(replaced.storeId).toBe("store-2");
    expect(replaced.items).toHaveLength(1);
  });

  it("clamps quantity to 1–20 and caps a reservation at 20 unique items", () => {
    const added = addToCart(null, bag, 99);
    if (!("ok" in added)) throw new Error("expected ok");
    expect(added.cart.items[0]!.quantity).toBe(20);
    const lowered = setCartQuantity(added.cart, "listing-1", 0);
    expect(lowered.items[0]!.quantity).toBe(1);
    let cart = added.cart;
    for (let i = 2; i <= 20; i += 1) {
      const next = addToCart(cart, { ...bag, listingId: `listing-${i}` }, 1);
      if (!("ok" in next)) throw new Error("expected ok");
      cart = next.cart;
    }
    const over = addToCart(cart, { ...bag, listingId: "listing-21" }, 1);
    expect(over).toMatchObject({ error: expect.stringContaining("20") });
  });

  it("removes the last item by clearing the cart", () => {
    const added = addToCart(null, bag, 1);
    if (!("ok" in added)) throw new Error("expected ok");
    expect(removeFromCart(added.cart, "listing-1")).toBeNull();
  });

  it("fingerprints contents independent of insertion order", () => {
    const a = addToCart(null, bag, 2);
    const b = addToCart(null, { ...bag, listingId: "listing-9" }, 1);
    if (!("ok" in a) || !("ok" in b)) throw new Error("expected ok");
    const cartA = addToCart(a.cart, { ...bag, listingId: "listing-9" }, 1);
    const cartB = addToCart(b.cart, bag, 2);
    if (!("ok" in cartA) || !("ok" in cartB)) throw new Error("expected ok");
    expect(cartFingerprint(cartA.cart)).toBe(cartFingerprint(cartB.cart));
  });

  it("rejects malformed stored carts", () => {
    expect(parseCart(null)).toBeNull();
    expect(parseCart("not json")).toBeNull();
    expect(parseCart(JSON.stringify({ storeId: 42, items: "nope" }))).toBeNull();
    expect(parseCart(JSON.stringify({ storeId: "s", storeName: "S", items: [] }))).toBeNull();
  });
});
