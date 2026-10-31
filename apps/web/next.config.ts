import type { NextConfig } from "next";

// Listing images resolve to the public listing-media
// bucket on the Supabase project host. The host comes
// from the environment, never from a hardcoded guess:
// if it is unset, no remote image host is allowed and
// listing cards fall back to the placeholder visual.
// W3: protocol follows the URL (https for the real
// project, http for a local stub/dev Supabase), so
// listing images work in both environments.
const supabaseImage = (() => {
  try {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    if (!url) return undefined;
    const parsed = new URL(url);
    return {
      protocol: parsed.protocol === "http:" ? "http" : "https",
      hostname: parsed.hostname,
    } as const;
  } catch {
    return undefined;
  }
})();

const nextConfig: NextConfig = {
  // The API client is a workspace package written in
  // TypeScript source; transpile it for the browser.
  transpilePackages: ["@savebite/api-client"],
  images: {
    remotePatterns: supabaseImage
      ? [
          {
            protocol: supabaseImage.protocol,
            hostname: supabaseImage.hostname,
            pathname: "/storage/v1/object/public/listing-media/**",
          },
        ]
      : [],
  },
};

export default nextConfig;
