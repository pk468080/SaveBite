import Image from "next/image";
import Link from "next/link";
import { MapPin, ShoppingBag } from "lucide-react";
import type { MarketplaceListing } from "@savebite/api-client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  dietaryLabel,
  discountInfo,
  firstImage,
  formatINR,
  formatPickupWindow,
  listingTypeLabel,
} from "@/lib/marketplace";
import { cn } from "@/lib/utils";

/**
 * Marketplace listing card. Shows ONLY values the
 * backend returned: no invented original prices (the
 * discount comes from reference_value vs selling_price
 * only when reference exceeds selling), no fabricated
 * ratings on cards (rating-summary is fetched only on
 * the detail page, per the W2 plan), no purchase
 * action in W2 — View details goes to the real detail
 * page, and reservation/checkout belong to W3.
 */
export function ListingCard({ listing }: { listing: MarketplaceListing }) {
  const image = firstImage(listing);
  const discount = discountInfo(listing);
  const diet = dietaryLabel(listing.dietary_classification);
  return (
    <Card className="overflow-hidden transition-shadow hover:shadow-md">
      <Link href={`/marketplace/${listing.id}`} aria-label={`View details for ${listing.title}`}>
        <div className="relative aspect-[4/3] w-full bg-muted">
          {image ? (
            <Image
              src={image}
              alt={listing.images[0]?.alt_text ?? listing.title}
              fill
              sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
              className="object-cover"
              loading="lazy"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
              <ShoppingBag className="h-10 w-10" aria-hidden="true" />
              <span className="text-xs">No photo provided by the store</span>
            </div>
          )}
          <span className="absolute left-3 top-3">
            <Badge>{listingTypeLabel(listing.listing_type)}</Badge>
          </span>
          {discount ? (
            <span className="absolute right-3 top-3">
              <Badge variant="destructive">Save {discount.percent}%</Badge>
            </span>
          ) : null}
        </div>
      </Link>
      <CardContent className="flex flex-col gap-2 p-4">
        <Link href={`/marketplace/${listing.id}`} className="hover:underline">
          <h3 className="line-clamp-2 font-semibold leading-snug">{listing.title}</h3>
        </Link>
        <p className="flex items-center gap-1 text-sm text-muted-foreground">
          <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="truncate">
            {listing.store.name} · {listing.store.locality ?? listing.store.city}
          </span>
        </p>
        <div className="flex items-baseline gap-2">
          <span className="text-lg font-bold">{formatINR(listing.selling_price, listing.currency)}</span>
          {discount ? (
            <span className="text-sm text-muted-foreground line-through">
              {formatINR(listing.reference_value, listing.currency)}
            </span>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{listing.available_quantity} available</span>
          <span aria-hidden="true">·</span>
          <span>
            Pickup {formatPickupWindow(listing.pickup_starts_at, listing.pickup_ends_at, listing.store.timezone)}
          </span>
          {diet ? (
            <>
              <span aria-hidden="true">·</span>
              <Badge variant="secondary" className={cn(diet === "Veg" && "text-green-700")}>
                {diet}
              </Badge>
            </>
          ) : null}
        </div>
        {listing.category_name ? (
          <p className="text-xs text-muted-foreground">{listing.category_name}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
