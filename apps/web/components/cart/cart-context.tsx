"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  CART_STORAGE_KEY,
  addToCart,
  cartDisplayTotal,
  cartItemCount,
  parseCart,
  removeFromCart,
  replaceCart,
  setCartQuantity,
  type AddResult,
  type CartItem,
  type CartState,
} from "@/lib/cart";

interface CartContextValue {
  cart: CartState | null;
  itemCount: number;
  displayTotal: number;
  add: (item: Omit<CartItem, "quantity">, quantity?: number) => AddResult;
  replace: (item: Omit<CartItem, "quantity">, quantity?: number) => void;
  remove: (listingId: string) => void;
  setQuantity: (listingId: string, quantity: number) => void;
  clear: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [cart, setCart] = useState<CartState | null>(null);

  useEffect(() => {
    setCart(parseCart(window.localStorage.getItem(CART_STORAGE_KEY)));
  }, []);

  useEffect(() => {
    if (cart) {
      window.localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
    } else {
      window.localStorage.removeItem(CART_STORAGE_KEY);
    }
  }, [cart]);

  const add = useCallback(
    (item: Omit<CartItem, "quantity">, quantity = 1) => {
      let result: AddResult = { error: "Could not add to cart." };
      setCart((current) => {
        result = addToCart(current, item, quantity);
        return "ok" in result ? result.cart : current;
      });
      return result;
    },
    [],
  );

  const value = useMemo<CartContextValue>(
    () => ({
      cart,
      itemCount: cartItemCount(cart),
      displayTotal: cartDisplayTotal(cart),
      add,
      replace: (item, quantity = 1) => setCart(replaceCart(item, quantity)),
      remove: (listingId) => setCart((current) => (current ? removeFromCart(current, listingId) : null)),
      setQuantity: (listingId, quantity) =>
        setCart((current) => (current ? setCartQuantity(current, listingId, quantity) : null)),
      clear: () => setCart(null),
    }),
    [cart, add],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextValue {
  const context = useContext(CartContext);
  if (!context) throw new Error("useCart must be used inside CartProvider.");
  return context;
}
