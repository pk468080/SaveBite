"use client";

import Link from "next/link";
import { StatusBadge } from "@/components/merchant/status-badge";
import { useMerchantStores } from "@/components/merchant/store-context";
import { storeStatusLabel } from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";

/**
 * Store list (W4, M3). Only stores belonging to
 * the caller's own merchant memberships are ever
 * listed, because the list itself comes from those
 * membership endpoints. Store creation is owner /
 * admin only on the backend; the button is shown
 * to every merchant member, and the backend still
 * enforces the role — hiding it would not be a
 * security mechanism.
 */
export default function MerchantStoresPage() {
  const { merchants, stores, loading, error, selectStore } = useMerchantStores();

  if (loading) return <LoadingState label="Loading stores" />;
  if (error) return <Alert variant="error">{error}</Alert>;
  if (merchants.length === 0) {
    return (
      <EmptyState
        title="No merchant application yet"
        description="Submit an application first — stores belong to an approved merchant."
      >
        <Button asChild>
          <Link href="/merchant/onboarding">Start onboarding</Link>
        </Button>
      </EmptyState>
    );
  }
  if (stores.length === 0) {
    return (
      <EmptyState
        title="No stores yet"
        description="Create your first store. A new store starts as a draft — it is not active immediately."
      >
        <Button asChild>
          <Link href="/merchant/stores/new">Create a store</Link>
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold">Stores</h1>
        <Button asChild>
          <Link href="/merchant/stores/new">Create a store</Link>
        </Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {stores.map((store) => (
          <Card key={store.id}>
            <CardHeader>
              <CardTitle>
                <Link
                  className="underline"
                  href={`/merchant/stores/${store.id}`}
                  onClick={() => selectStore(store.id)}
                >
                  {store.name}
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-2 text-sm">
              <p className="text-muted-foreground">
                {[store.locality, store.city, store.state, store.pincode].filter(Boolean).join(", ")}
              </p>
              <div>
                <StatusBadge status={store.status} label={storeStatusLabel(store.status)} />
              </div>
              <div className="flex gap-2">
                <Button asChild variant="outline" size="sm">
                  <Link href={`/merchant/stores/${store.id}`}>Details</Link>
                </Button>
                <Button asChild variant="outline" size="sm">
                  <Link href={`/merchant/stores/${store.id}/hours`}>Hours</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
