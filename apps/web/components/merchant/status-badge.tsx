import { Badge } from "@/components/ui/badge";

/** Status badge. Colours are presentation only —
 * the backend status string is always shown in the
 * title text nearby, never replaced by colour. */
export function StatusBadge({ status, label }: { status: string; label: string }) {
  const variant =
    status === "active" || status === "approved" || status === "verified" || status === "collected"
      ? "default"
      : status === "cancelled" || status === "rejected" || status === "expired" || status === "suspended"
        ? "destructive"
        : status === "paused" || status === "pending_payment" || status === "pending_review"
          ? "secondary"
          : "outline";
  return <Badge variant={variant}>{label}</Badge>;
}
