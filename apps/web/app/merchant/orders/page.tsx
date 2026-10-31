import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function MerchantOrdersPage() {
  return (
    <AreaPlaceholder
      title="Merchant orders"
      description="The merchant order queue comes from GET /v1/merchant/orders. Order detail and pickup verification arrive in later milestones."
    />
  );
}
