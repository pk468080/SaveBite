/**
 * Customer cart (W3). A cart is a browser-side shopping
 * list ONLY — it is not an inventory reservation, it does
 * not decrement stock, and its prices are display values:
 * the backend re-validates availability and price at
 * reservation time and its totals are authoritative.
 *
 * Same-store rule (enforced by the database function
 * behind POST /v1/orders/reservations): one reservation
 * may contain listings from ONE store only. The cart
 * therefore holds one store at a time. Adding an item
 * from another store returns { needsReplace: true } and
 * the caller must ask the customer to deliberately
 * replace the cart — items are never silently dropped.
 *
 * Backend constraints (M5, verified against
 * ReservationCreate): 1–20 unique listings per
 * reservation, quantity 1–20 per listing.
 */

export const CART_STORAGE_KEY = "savebite_cart_v1";
export const MAX_CART_ITEMS = 20;
export const MAX_QUANTITY = 20;

export interface CartItem {
  listingId: string;
  storeId: string;
  storeName: string;
  title: string;
  /** Display price only; the backend price wins at reservation. */
  sellingPrice: string;
  currency: string;
  imagePath?: string | null;
  quantity: number;
}

export interface CartState {
  storeId: string;
  storeName: string;
  items: CartItem[];
}

export function emptyCart(): CartState | null {
  return null;
}

export function cartItemCount(cart: CartState | null): number {
  if (!cart) return 0;
  return cart.items.reduce((sum, item) => sum + item.quantity, 0);
}

/** Display total only. Never used for payment. */
export function cartDisplayTotal(cart: CartState | null): number {
  if (!cart) return 0;
  return cart.items.reduce(
    (sum, item) => sum + Number(item.sellingPrice) * item.quantity,
    0,
  );
}

export type AddResult =
  | { ok: true; cart: CartState }
  | { needsReplace: true; existingStoreName: string }
  | { error: string };

export function addToCart(
  cart: CartState | null,
  item: Omit<CartItem, "quantity">,
  quantity: number,
): AddResult {
  const qty = Math.max(1, Math.min(MAX_QUANTITY, Math.floor(quantity) || 1));
  if (cart && cart.storeId !== item.storeId) {
    return { needsReplace: true, existingStoreName: cart.storeName };
  }
  if (!cart) {
    return {
      ok: true,
      cart: {
        storeId: item.storeId,
        storeName: item.storeName,
        items: [{ ...item, quantity: qty }],
      },
    };
  }
  const existing = cart.items.find((i) => i.listingId === item.listingId);
  if (existing) {
    return {
      ok: true,
      cart: {
        ...cart,
        items: cart.items.map((i) =>
          i.listingId === item.listingId
            ? { ...i, quantity: Math.min(MAX_QUANTITY, i.quantity + qty) }
            : i,
        ),
      },
    };
  }
  if (cart.items.length >= MAX_CART_ITEMS) {
    return { error: `A reservation can hold at most ${MAX_CART_ITEMS} different items.` };
  }
  return { ok: true, cart: { ...cart, items: [...cart.items, { ...item, quantity: qty }] } };
}

export function replaceCart(
  item: Omit<CartItem, "quantity">,
  quantity: number,
): CartState {
  const qty = Math.max(1, Math.min(MAX_QUANTITY, Math.floor(quantity) || 1));
  return { storeId: item.storeId, storeName: item.storeName, items: [{ ...item, quantity: qty }] };
}

export function removeFromCart(cart: CartState, listingId: string): CartState | null {
  const items = cart.items.filter((i) => i.listingId !== listingId);
  return items.length === 0 ? null : { ...cart, items };
}

export function setCartQuantity(
  cart: CartState,
  listingId: string,
  quantity: number,
): CartState {
  const qty = Math.max(1, Math.min(MAX_QUANTITY, Math.floor(quantity) || 1));
  return {
    ...cart,
    items: cart.items.map((i) => (i.listingId === listingId ? { ...i, quantity: qty } : i)),
  };
}

/** Stable fingerprint of a cart's contents, used to key
 * the reservation idempotency key in session storage. */
export function cartFingerprint(cart: CartState): string {
  return cart.items
    .map((i) => `${i.listingId}:${i.quantity}`)
    .sort()
    .join("|");
}

export function parseCart(raw: string | null): CartState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as CartState;
    if (!parsed || typeof parsed.storeId !== "string" || !Array.isArray(parsed.items)) {
      return null;
    }
    const items = parsed.items.filter(
      (i) =>
        i &&
        typeof i.listingId === "string" &&
        typeof i.storeId === "string" &&
        typeof i.title === "string" &&
        typeof i.sellingPrice === "string" &&
        Number.isFinite(i.quantity),
    );
    if (items.length === 0) return null;
    return {
      storeId: parsed.storeId,
      storeName: typeof parsed.storeName === "string" ? parsed.storeName : "Store",
      items: items.map((i) => ({
        ...i,
        quantity: Math.max(1, Math.min(MAX_QUANTITY, Math.floor(i.quantity) || 1)),
      })),
    };
  } catch {
    return null;
  }
}
