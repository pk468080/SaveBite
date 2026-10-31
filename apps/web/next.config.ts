import type { NextConfig } from "next";

// Listing images resolve to the public listing-media
// bucket on the Supabase project host. The host comes
// from the environment, never from a hardcoded guess:
// if it is unset, no remote image host is allowed and
// listing cards fall back to the placeholder visual.
const supabaseHostname = (() => {
  try {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    return url ? new URL(url).hostname : undefined;
  } catch {
    return undefined;
  }
})();

const nextConfig: NextConfig = {
  // The API client is a workspace package written in
  // TypeScript source; transpile it for the browser.
  transpilePackages: ["@savebite/api-client"],
  images: {
    remotePatterns: supabaseHostname
      ? [
          {
            protocol: "https",
            hostname: supabaseHostname,
            pathname: "/storage/v1/object/public/listing-media/**",
          },
        ]
      : [],
  },
};

export default nextConfig;
