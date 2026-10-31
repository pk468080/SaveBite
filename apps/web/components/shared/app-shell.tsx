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
 */
export async function AppShell({
  title,
  items,
  children,
  extraCheck,
}: {
  title: string;
  items: NavItem[];
  children: React.ReactNode;
  extraCheck?: () => Promise<void>;
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
