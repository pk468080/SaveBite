import { redirect } from "next/navigation";
import { ApiError } from "@savebite/api-client";
import { AppShell } from "@/components/shared/app-shell";
import { createServerApiClient } from "@/lib/api/client";

const ITEMS = [
  { href: "/admin", label: "Platform overview" },
  { href: "/admin/merchants", label: "Merchants" },
  { href: "/admin/stores", label: "Stores" },
  { href: "/admin/orders", label: "Orders" },
  { href: "/admin/payments", label: "Payments and refunds" },
  { href: "/admin/reviews", label: "Reviews" },
  { href: "/admin/activity", label: "Activity" },
];

/**
 * Admin shell gate: after the session check, the
 * layout asks the BACKEND whether this user may use
 * the admin APIs (GET /v1/admin/dashboard). A 401 or
 * 403 sends the user to /unauthorized. This is a
 * navigation convenience only — the backend enforces
 * admin access on every admin operation, and merchant
 * membership never counts as platform-admin access.
 * Other backend errors (for example the API being
 * unreachable) do not redirect: the pages themselves
 * surface those errors honestly.
 */
async function adminCheck() {
  try {
    const api = await createServerApiClient();
    await api.get("/v1/admin/dashboard");
  } catch (error) {
    if (error instanceof ApiError && (error.isUnauthorized || error.isForbidden)) {
      redirect("/unauthorized");
    }
  }
}

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AppShell title="Platform admin" items={ITEMS} extraCheck={adminCheck}>
      {children}
    </AppShell>
  );
}

