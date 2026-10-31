import { createServices } from "@savebite/api-client";
import { AppShell } from "@/components/shared/app-shell";
import { MerchantProviders } from "@/components/merchant/merchant-providers";
import { createServerApiClient } from "@/lib/api/server";

/**
 * Merchant shell (W4). Sign-in is enforced by
 * AppShell; merchant membership is NOT decided
 * here — every page loads through backend APIs
 * that check memberships, and a user with no
 * merchant memberships sees the onboarding entry
 * point, not operational pages. The notification
 * badge is a convenience only: a failed count fetch
 * leaves the badge off rather than showing a wrong
 * number.
 */
export default async function MerchantLayout({ children }: { children: React.ReactNode }) {
  let unread = 0;
  try {
    const client = await createServerApiClient();
    const count = await createServices(client).notifications.unreadCount();
    unread = count.unread_count;
  } catch {
    unread = 0;
  }

  const items = [
    { href: "/merchant", label: "Dashboard" },
    { href: "/merchant/onboarding", label: "Onboarding" },
    { href: "/merchant/stores", label: "Stores" },
    { href: "/merchant/listings", label: "Listings" },
    { href: "/merchant/inventory", label: "Inventory" },
    { href: "/merchant/orders", label: "Orders" },
    { href: "/merchant/pickups", label: "Pickups" },
    { href: "/merchant/analytics", label: "Analytics" },
    { href: "/merchant/reviews", label: "Reviews" },
    { href: "/merchant/notifications", label: "Notifications", badge: unread },
    { href: "/merchant/settings", label: "Settings" },
  ];

  return (
    <AppShell title="Merchant" items={items}>
      <MerchantProviders>{children}</MerchantProviders>
    </AppShell>
  );
}
