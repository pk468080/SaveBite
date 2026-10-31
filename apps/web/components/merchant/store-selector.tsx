"use client";

import { useMerchantStores } from "@/components/merchant/store-context";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Store selector (W4). Shown only when the caller
 * has more than one authorized store; a single
 * store is selected automatically and needs no
 * selector. Selecting "All stores" is offered only
 * on pages whose endpoints accept no store filter
 * (dashboard overview, analytics, orders) — pages
 * that require one store hide the all-stores option.
 */
export function StoreSelector({ allowAll = false }: { allowAll?: boolean }) {
  const { stores, selectedStoreId, selectStore, loading } = useMerchantStores();

  if (loading || stores.length <= 1) {
    return null;
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Store</span>
      <Select
        value={selectedStoreId ?? (allowAll ? "all" : "")}
        onValueChange={(value) => selectStore(value === "all" ? null : value)}
      >
        <SelectTrigger aria-label="Select store" className="w-64">
          <SelectValue placeholder="All my stores" />
        </SelectTrigger>
        <SelectContent>
          {allowAll ? <SelectItem value="all">All my stores</SelectItem> : null}
          {stores.map((store) => (
            <SelectItem key={store.id} value={store.id}>
              {store.name} ({store.city ?? "—"})
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}
