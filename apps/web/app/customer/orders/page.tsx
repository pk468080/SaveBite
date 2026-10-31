import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function CustomerOrdersPage() {
  return (
    <AreaPlaceholder
      title="My orders"
      description="Order history comes from GET /v1/orders on the FastAPI backend. Listing, detail, and pickup-code screens arrive in later milestones."
    />
  );
}
