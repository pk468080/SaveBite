import { ApiClient } from "@savebite/api-client";
import { config } from "@/lib/config";
import { createClient as createBrowserSupabase } from "@/lib/supabase/client";

/**
 * Browser API client wired to the current Supabase
 * session. Browser-only: this module must never import
 * the server Supabase client (next/headers), or client
 * components that import it will fail the production
 * build. Server code uses lib/api/server.ts instead.
 */
export function createBrowserApiClient() {
  const supabase = createBrowserSupabase();
  return new ApiClient({
    baseUrl: config.apiBaseUrl,
    getAccessToken: async () => {
      const { data } = await supabase.auth.getSession();
      return data.session?.access_token ?? null;
    },
  });
}
