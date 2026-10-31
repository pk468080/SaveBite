"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { MerchantSummary, StoreSummary } from "@savebite/api-client";
import { createServices } from "@savebite/api-client";
import { createBrowserApiClient } from "@/lib/api/browser";

const STORAGE_KEY = "savebite_merchant_store_v1";

export interface MerchantStoreState {
  merchants: MerchantSummary[];
  stores: StoreSummary[];
  selectedStoreId: string | null;
  selectedStore: StoreSummary | null;
  loading: boolean;
  error: string | null;
  selectStore: (storeId: string | null) => void;
  refresh: () => Promise<void>;
}

const StoreContext = createContext<MerchantStoreState | null>(null);

/**
 * Merchant store context (W4). Stores come only
 * from the caller's own merchant memberships via
 * GET /v1/merchants + GET /v1/merchants/{id}/stores.
 * The selected store is a UI preference in
 * localStorage: it is validated against the loaded
 * stores on every load, and it never grants access
 * — every backend call re-checks membership, and a
 * store id outside the caller's memberships simply
 * returns no data. A merchant with one store gets
 * that store selected automatically, with no
 * selector noise.
 */
export function MerchantStoreProvider({ children }: { children: React.ReactNode }) {
  const [merchants, setMerchants] = useState<MerchantSummary[]>([]);
  const [stores, setStores] = useState<StoreSummary[]>([]);
  const [selectedStoreId, setSelectedStoreId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const services = createServices(createBrowserApiClient());
      const found = await services.merchants.listMerchants();
      const allStores: StoreSummary[] = [];
      for (const merchant of found) {
        const merchantStores = await services.merchants.listStores(merchant.id);
        allStores.push(...merchantStores);
      }
      setMerchants(found);
      setStores(allStores);
      const stored =
        typeof window !== "undefined" ? window.localStorage.getItem(STORAGE_KEY) : null;
      if (stored && allStores.some((store) => store.id === stored)) {
        setSelectedStoreId(stored);
      } else if (allStores.length === 1) {
        setSelectedStoreId(allStores[0]!.id);
      } else {
        setSelectedStoreId(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your stores");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectStore = useCallback(
    (storeId: string | null) => {
      setSelectedStoreId(storeId);
      if (typeof window !== "undefined") {
        if (storeId) {
          window.localStorage.setItem(STORAGE_KEY, storeId);
        } else {
          window.localStorage.removeItem(STORAGE_KEY);
        }
      }
    },
    [],
  );

  const value = useMemo<MerchantStoreState>(
    () => ({
      merchants,
      stores,
      selectedStoreId,
      selectedStore: stores.find((store) => store.id === selectedStoreId) ?? null,
      loading,
      error,
      selectStore,
      refresh,
    }),
    [merchants, stores, selectedStoreId, loading, error, selectStore, refresh],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useMerchantStores(): MerchantStoreState {
  const context = useContext(StoreContext);
  if (!context) {
    throw new Error("useMerchantStores must be used inside MerchantStoreProvider");
  }
  return context;
}
