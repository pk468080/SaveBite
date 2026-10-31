import type { MetadataRoute } from "next";
import { config } from "@/lib/config";
import { createPublicServices } from "@/lib/api/public";

export const revalidate = 3600;

/**
 * Sitemap: static public routes plus real listing URLs
 * fetched from the marketplace API (paginated, capped
 * at 500 listings — pilot-scale). If the backend is
 * unreachable at sitemap time, only the static routes
 * are returned rather than failing the sitemap. Listing
 * URLs are never invented: every entry comes from an
 * API-returned listing id.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = config.siteUrl;
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${base}/`, changeFrequency: "daily", priority: 1 },
    { url: `${base}/marketplace`, changeFrequency: "hourly", priority: 0.9 },
    { url: `${base}/sign-in`, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/sign-up`, changeFrequency: "monthly", priority: 0.3 },
  ];
  try {
    const services = createPublicServices();
    const entries: MetadataRoute.Sitemap = [];
    let page = 1;
    while (entries.length < 500) {
      const result = await services.marketplace.listListings({
        sort: "newest",
        page,
        page_size: 100,
      });
      for (const listing of result.items) {
        entries.push({
          url: `${base}/marketplace/${listing.id}`,
          changeFrequency: "daily",
          priority: 0.7,
        });
        if (entries.length >= 500) break;
      }
      if (result.items.length < 100 || page * 100 >= result.total) break;
      page += 1;
    }
    return [...staticRoutes, ...entries];
  } catch {
    return staticRoutes;
  }
}
