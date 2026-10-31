"use client";

import { MerchantStoreProvider } from "@/components/merchant/store-context";

/** Client boundary so the server merchant layout
 * can wrap its pages in the store context. */
export function MerchantProviders({ children }: { children: React.ReactNode }) {
  return <MerchantStoreProvider>{children}</MerchantStoreProvider>;
}
