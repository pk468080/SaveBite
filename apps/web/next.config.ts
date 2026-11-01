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
  // W8: minimal security headers. No CSP yet: a content
  // security policy needs allowlisting for the Razorpay
  // checkout script and Supabase hosts, which must be
  // tested against the live checkout flow before it is
  // added; see docs/w8-production-readiness for the
  // follow-up. These headers are safe for all routes.
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
