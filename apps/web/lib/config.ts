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

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable ${name}. Copy apps/web/.env.example to .env.local and fill it in.`,
    );
  }
  return value;
}

export const config = {
  get supabaseUrl(): string {
    return required("NEXT_PUBLIC_SUPABASE_URL");
  },
  get supabasePublishableKey(): string {
    return required("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY");
  },
  get apiBaseUrl(): string {
    return required("NEXT_PUBLIC_API_BASE_URL");
  },
  get siteUrl(): string {
    return process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  },
};

/** Non-throwing check used by pages that render a
 * helpful setup message instead of crashing. */
export function configProblems(): string[] {
  const problems: string[] = [];
  for (const name of [
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY",
    "NEXT_PUBLIC_API_BASE_URL",
  ]) {
    if (!process.env[name]) {
      problems.push(name);
    }
  }
  return problems;
}
