"use client";

import { ApiError, createServices, type AdminStoreSummary } from "@savebite/api-client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { AdminPager } from "@/components/admin/pager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { ADMIN_PAGE_SIZE, storeStatusLabel } from "@/lib/admin";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Store list (W6, M11). Filters and pagination
 * are server-side. Search matches the store name
 * only, per the backend contract.
 */
const STATUSES = ["draft", "active", "inactive", "suspended"];

export default function AdminStoresPage() {
  const [items, setItems] = useState<AdminStoreSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("all");
  const [cityInput, setCityInput] = useState("");
  const [city, setCity] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDenied(false);
    createServices(createBrowserApiClient())
      .admin.listStores({
        status: status === "all" ? undefined : status,
        city: city || undefined,
        search: search || undefined,
        page,
        page_size: ADMIN_PAGE_SIZE,
      })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
          setDenied(true);
        } else {
          setError(err instanceof Error ? err.message : "Could not load stores.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, city, search, page]);

  if (denied) return <AccessDenied />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Stores</h1>
        <p className="text-sm text-muted-foreground">
          Platform stores. Search matches the store name only.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Store status</span>
            <Select value={status} onValueChange={(value) => { setStatus(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {storeStatusLabel(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <form
            className="flex flex-1 items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setCity(cityInput.trim());
              setSearch(searchInput.trim());
              setPage(1);
            }}
          >
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span>City</span>
              <Input
                value={cityInput}
                onChange={(event) => setCityInput(event.target.value)}
                placeholder="City"
              />
            </label>
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span>Store name</span>
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search store name"
              />
            </label>
            <Button type="submit">Search</Button>
          </form>
        </CardContent>
      </Card>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading stores" />
      ) : items.length === 0 ? (
        <EmptyState title="No stores found" description="Try a different filter or search." />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y p-0">
            {items.map((store) => (
              <div key={store.id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
                <div>
                  <Link href={`/admin/stores/${store.id}`} className="font-medium underline underline-offset-4">
                    {store.name}
                  </Link>
                  <p className="text-muted-foreground">
                    {store.merchant_name} · {store.city} {store.pincode} · {store.listing_count}{" "}
                    listing(s) · {store.order_count} order(s)
                  </p>
                  {store.created_at ? (
                    <p className="text-muted-foreground">Created {formatDateTime(store.created_at)}</p>
                  ) : null}
                </div>
                <p className="font-medium">{storeStatusLabel(store.status)}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      <AdminPager page={page} pageSize={ADMIN_PAGE_SIZE} total={total} onPage={setPage} />
    </div>
  );
}
