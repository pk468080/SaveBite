import { createBrowserClient } from "@supabase/ssr";
import { config } from "@/lib/config";

/**
 * Browser Supabase client (client components only).
 * Uses the publishable key — never the service-role key.
 * Session is stored in cookies via @supabase/ssr so
 * server components and middleware see the same session.
 */
export function createClient() {
  return createBrowserClient(config.supabaseUrl, config.supabasePublishableKey);
}
