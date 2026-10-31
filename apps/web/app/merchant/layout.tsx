import { AppShell } from "@/components/shared/app-shell";

const ITEMS = [
  { href: "/merchant", label: "Dashboard" },
  { href: "/merchant/orders", label: "Orders" },
  { href: "/merchant/listings", label: "Listings" },
  { href: "/merchant/inventory", label: "Inventory" },
  { href: "/merchant/analytics", label: "Analytics" },
  { href: "/merchant/notifications", label: "Notifications" },
];

export default async function MerchantLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell title="Merchant" items={ITEMS}>
      {children}
    </AppShell>
  );
}

