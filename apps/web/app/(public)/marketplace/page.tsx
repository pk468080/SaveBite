import type { Metadata } from "next";
import { Suspense } from "react";
import { MarketplaceExplorer } from "@/components/marketplace/marketplace-explorer";
import { LoadingState } from "@/components/ui/states";

export const metadata: Metadata = {
  title: "Explore Food — Surplus food marketplace",
  description:
    "Browse surplus food from local restaurants, bakeries and food stores. Search, filter by city, pincode, category, price and dietary preference, and collect at the store.",
  // Canonical points at the bare marketplace URL so
  // arbitrary filter combinations do not create
  // thousands of duplicate indexable URLs.
  alternates: { canonical: "/marketplace" },
};

export default function MarketplacePage() {
  return (
    <Suspense fallback={<LoadingState label="Loading marketplace…" />}>
      <MarketplaceExplorer />
    </Suspense>
  );
}
