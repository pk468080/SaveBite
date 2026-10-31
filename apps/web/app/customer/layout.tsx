import { createServices } from "@savebite/api-client";
import { AppShell } from "@/components/shared/app-shell";
import { createServerApiClient } from "@/lib/api/server";

/**
 * Customer shell (W3). The Notifications entry carries
 * the real unread count from GET /v1/notifications/
 * unread-count when the backend answers; a failure
 * leaves the badge off rather than showing a wrong
 * number. Access never depends on this nav — the
 * backend verifies every operation.
 */
export default async function CustomerLayout({ children }: { children: React.ReactNode }) {
  let unread = 0;
  try {
    const client = await createServerApiClient();
    const count = await createServices(client).notifications.unreadCount();
    unread = count.unread_count;
  } catch {
    unread = 0;
  }

  const items = [
    { href: "/customer", label: "Overview" },
    { href: "/customer/orders", label: "My orders" },
    { href: "/customer/notifications", label: "Notifications", badge: unread },
    { href: "/customer/profile", label: "Profile" },
  ];

  return (
    <AppShell title="Customer" items={items}>
      {children}
    </AppShell>
  );
}
