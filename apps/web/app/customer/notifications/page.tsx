import { AreaPlaceholder } from "@/components/shared/placeholder";

export default function CustomerNotificationsPage() {
  return (
    <AreaPlaceholder
      title="Notifications"
      description="In-app notifications come from GET /v1/notifications on the FastAPI backend, with unread counts and read-state actions from M12."
    />
  );
}
