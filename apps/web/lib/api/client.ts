import { ApiClient } from "@savebite/api-client";
import { config } from "@/lib/config";
import { createClient as createBrowserSupabase } from "@/lib/supabase/client";
import { createClient as createServerSupabase } from "@/lib/supabase/server";

/**
 * API client wired to the current Supabase session.
 *
 * Browser version: reads the access token from the
 * browser Supabase client and sends it as
 * `Authorization: Bearer <token>` to FastAPI.
 *
 * Server version: reads the token from the cookie
 * session. If there is no session, no token is sent —
 * the backend then treats the request as anonymous,
 * exactly as it would for a public visitor.
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
