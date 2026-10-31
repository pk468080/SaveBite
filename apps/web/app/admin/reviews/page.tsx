import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function AdminReviewsPage() {
  return (
    <AreaPlaceholder
      title="Reviews"
      description="Review visibility comes from GET /v1/admin/reviews (visible reviews only, per the M11/M12 RLS rules). Moderation actions do not exist in the backend."
    />
  );
}
