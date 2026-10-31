/**
 * Environment configuration for the website.
 *
 * Only NEXT_PUBLIC_* values reach the browser. The
 * Supabase service-role key, Razorpay secrets, and
 * database passwords must NEVER appear here or in any
 * .env file committed to this repository.
 *
 * Required (client-safe):
 * - NEXT_PUBLIC_SUPABASE_URL
 * - NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
 * - NEXT_PUBLIC_API_BASE_URL (FastAPI base URL)
 * - NEXT_PUBLIC_SITE_URL (canonical origin, for metadata)
 *
 * Missing values fail loudly at the integration
 * boundary instead of silently producing broken pages.
 */

// NOTE: Next.js inlines NEXT_PUBLIC_* variables into
// the browser bundle ONLY for static property access
// (process.env.NEXT_PUBLIC_X). Dynamic indexing such
// as process.env[name] is NOT inlined, so the browser
// build would see an empty object and every getter
// would throw. Read each variable once, statically,
// at module load. (This latent W1 bug surfaced in W2
// when the marketplace first read config in the browser.)
const supabaseUrlValue = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabasePublishableKeyValue =
  process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const apiBaseUrlValue = process.env.NEXT_PUBLIC_API_BASE_URL;
const siteUrlValue = process.env.NEXT_PUBLIC_SITE_URL;

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing required environment variable ${name}. Copy apps/web/.env.example to .env.local and fill it in.`,
    );
  }
  return value;
}

export const config = {
  get supabaseUrl(): string {
    return required("NEXT_PUBLIC_SUPABASE_URL", supabaseUrlValue);
  },
  get supabasePublishableKey(): string {
    return required(
      "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
      supabasePublishableKeyValue,
    );
  },
  get apiBaseUrl(): string {
    return required("NEXT_PUBLIC_API_BASE_URL", apiBaseUrlValue);
  },
  get siteUrl(): string {
    return siteUrlValue ?? "http://localhost:3000";
  },
};

/** Non-throwing check used by pages that render a
 * helpful setup message instead of crashing. */
export function configProblems(): string[] {
  const problems: string[] = [];
  if (!supabaseUrlValue) {
    problems.push("NEXT_PUBLIC_SUPABASE_URL");
  }
  if (!supabasePublishableKeyValue) {
    problems.push("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");
  }
  if (!apiBaseUrlValue) {
    problems.push("NEXT_PUBLIC_API_BASE_URL");
  }
  return problems;
}
