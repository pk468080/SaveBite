import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function AdminActivityPage() {
  return (
    <AreaPlaceholder
      title="Activity"
      description="Operational activity comes from GET /v1/admin/activity (recorded order status events only). Audit logs live in private tables and are not exposed."
    />
  );
}
