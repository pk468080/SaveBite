import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function AdminPaymentsPage() {
  return (
    <AreaPlaceholder
      title="Payments and refunds"
      description="Payment exception visibility comes from GET /v1/admin/payments and refund visibility from GET /v1/admin/refunds. Both are read-only; no refund execution exists."
    />
  );
}
