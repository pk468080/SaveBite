import type { Metadata } from "next";
import { EmptyState } from "@/components/ui/states";

export const metadata: Metadata = {
  title: "Marketplace",
  description: "Browse surplus food from nearby bakeries, cafes, and restaurants.",
};

export default function MarketplacePage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Marketplace</h1>
        <p className="text-muted-foreground">
          Surplus bags and items from nearby shops, at a discount.
        </p>
      </div>
      <EmptyState
        title="Marketplace browsing arrives in the next milestone"
        description="The marketplace API client is ready (see packages/api-client). This placeholder proves the route and layout work; listing cards, filters, and search land in W2."
      />
    </div>
  );
}
