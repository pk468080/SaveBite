import Link from "next/link";
import { redirect } from "next/navigation";
import { AppNav, type NavItem } from "@/components/shared/app-nav";
import { Brand } from "@/components/shared/site-header";
import { SignOutButton } from "@/components/shared/sign-out-button";
import { createClient } from "@/lib/supabase/server";

/**
 * Shared application shell. Checks the Supabase
 * session on the server: no session means a redirect
 * to sign-in. Navigation links are a convenience only
 * — every backend API independently verifies access,
 * so hiding a link never grants or denies anything.
 *
 * Phase 1 workspace separation: `title` is the current
 * workspace ("Customer" or "Merchant") and is shown as
 * a mode badge in the header, so the two shells never
 * look identical. `switchHref` / `switchLabel`, when
 * supplied by a workspace layout, render a clearly
 * labelled switch button next to Sign Out — switching
 * workspace changes only which pages are shown, never
 * what the backend allows.
 */
export async function AppShell({
  title,
  items,
  children,
  extraCheck,
  switchHref,
  switchLabel,
}: {
  title: string;
  items: NavItem[];
  children: React.ReactNode;
  extraCheck?: () => Promise<void>;
  switchHref?: string;
  switchLabel?: string;
}) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    redirect("/sign-in");
  }
  if (extraCheck) {
    await extraCheck();
  }
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <Brand href="/" />
          <div className="flex items-center gap-3">
            <span className="rounded-md border px-2 py-1 text-xs font-medium">{title} workspace</span>
            {switchHref && switchLabel ? (
              <Link
                href={switchHref}
                className="rounded-md px-3 py-2 text-sm font-medium hover:bg-accent"
              >
                Switch to {switchLabel}
              </Link>
            ) : null}
            <span className="hidden text-sm text-muted-foreground sm:block">{data.user.email}</span>
            <SignOutButton />
          </div>
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-8 sm:px-6 lg:flex-row">
        <AppNav title={title} items={items} />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
