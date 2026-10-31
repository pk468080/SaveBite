import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function AdminMerchantsPage() {
  return (
    <AreaPlaceholder
      title="Merchant management"
      description="Merchant review comes from GET /v1/admin/merchants and POST /v1/admin/merchants/{id}/review. The review workflow arrives in a later milestone."
    />
  );
}
