import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { cookies } from "next/headers";
import { config } from "@/lib/config";

/**
 * Server Supabase client (server components, server
 * actions, route handlers). Reads the session from
 * cookies; never trusts local storage, query params,
 * or frontend state for identity.
 */
export async function createClient() {
  const cookieStore = await cookies();
  return createServerClient(config.supabaseUrl, config.supabasePublishableKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet: { name: string; value: string; options: CookieOptions }[]) {
        try {
          for (const { name, value, options } of cookiesToSet) {
            cookieStore.set(name, value, options);
          }
        } catch {
          // Called from a Server Component: cookies can
          // only be read there. Middleware refreshes the
          // session instead (see middleware.ts).
        }
      },
    },
  });
}
