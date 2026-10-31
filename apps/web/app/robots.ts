import type { MetadataRoute } from "next";
import { config } from "@/lib/config";

/**
 * robots.txt: public pages are indexable; customer,
 * merchant, admin, auth, and API routes are not.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: ["/", "/marketplace"],
        disallow: ["/customer", "/merchant", "/admin", "/sign-in", "/sign-up", "/unauthorized", "/api/"],
      },
    ],
    sitemap: `${config.siteUrl}/sitemap.xml`,
  };
}
