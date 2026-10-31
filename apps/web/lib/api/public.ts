import { ApiClient, createServices } from "@savebite/api-client";
import { config } from "@/lib/config";

/**
 * Anonymous API client for public pages (homepage,
 * marketplace, listing detail). Guest browsing needs
 * no Supabase session: the FastAPI marketplace routes
 * are anonymous by design, and this client sends no
 * token at all.
 */
export function createPublicApiClient() {
  return new ApiClient({ baseUrl: config.apiBaseUrl });
}

export function createPublicServices() {
  return createServices(createPublicApiClient());
}
