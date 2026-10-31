import { AppShell } from "@/components/shared/app-shell";

const ITEMS = [
  { href: "/customer", label: "Overview" },
  { href: "/customer/orders", label: "My orders" },
  { href: "/customer/notifications", label: "Notifications" },
];

export default async function CustomerLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell title="Customer" items={ITEMS}>
      {children}
    </AppShell>
  );
}

