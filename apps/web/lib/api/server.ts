import { ApiClient } from "@savebite/api-client";
import { config } from "@/lib/config";
import { createClient as createServerSupabase } from "@/lib/supabase/server";

/**
 * Server API client wired to the cookie session.
 * Server-only (uses next/headers through the server
 * Supabase client). If there is no session, no token
 * is sent — the backend then treats the request as
 * anonymous, exactly as it would for a public visitor.
 */
export async function createServerApiClient() {
  const supabase = await createServerSupabase();
  return new ApiClient({
    baseUrl: config.apiBaseUrl,
    getAccessToken: async () => {
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    },
  });
}
