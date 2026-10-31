import { SiteFooter, SiteHeader } from "@/components/shared/site-header";
import { createClient } from "@/lib/supabase/server";

export default async function PublicLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader authenticated={Boolean(data.user)} />
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6">{children}</main>
      <SiteFooter />
    </div>
  );
}
