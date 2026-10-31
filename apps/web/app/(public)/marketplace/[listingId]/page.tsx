import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Clock, MapPin, ShoppingBag, Store } from "lucide-react";
import { ApiError } from "@savebite/api-client";
import type {
  MarketplaceListing,
  PublicReview,
  StoreRatingSummary,
} from "@savebite/api-client";
import { AddToCartButton } from "@/components/cart/add-to-cart-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/states";
import { createPublicServices } from "@/lib/api/public";
import {
  dietaryLabel,
  discountInfo,
  firstImage,
  formatINR,
  formatPickupWindow,
  listingImageUrl,
  listingTypeLabel,
} from "@/lib/marketplace";

type PageProps = {
  params: Promise<{ listingId: string }>;
};

async function loadDetail(listingId: string): Promise<{
  listing: MarketplaceListing | null;
  rating: StoreRatingSummary | null;
  reviews: PublicReview[];
}> {
  const services = createPublicServices();
  let listing: MarketplaceListing | null = null;
  try {
    listing = await services.marketplace.getListing(listingId);
  } catch (error) {
    if (error instanceof ApiError && error.isNotFound) {
      return { listing: null, rating: null, reviews: [] };
    }
    throw error;
  }
  // Rating and reviews are fetched ONLY for this detail
  // page — never per listing card. Failures degrade to
  // "no reviews shown" rather than breaking the page.
  const [rating, reviews] = await Promise.all([
    services.reviews
      .getStoreRatingSummary(listing.store.id)
      .catch(() => null),
    services.reviews
      .listStoreReviews(listing.store.id, { sort: "newest", page_size: 10 })
      .then((page) => page.items)
      .catch(() => [] as PublicReview[]),
  ]);
  return { listing, rating, reviews };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { listingId } = await params;
  const services = createPublicServices();
  let listing: MarketplaceListing | null = null;
  try {
    listing = await services.marketplace.getListing(listingId);
  } catch {
    listing = null;
  }
  if (!listing) {
    return {
      title: "Listing unavailable · SaveBite",
      description: "This listing is no longer available.",
      alternates: { canonical: `/marketplace/${listingId}` },
    };
  }
  const image = firstImage(listing);
  const description =
    listing.description ?? listing.contents_description ?? `Surplus food from ${listing.store.name}.`;
  return {
    title: `${listing.title} · ${listing.store.name} · SaveBite`,
    description,
    alternates: { canonical: `/marketplace/${listing.id}` },
    openGraph: {
      title: `${listing.title} · ${listing.store.name}`,
      description,
      ...(image ? { images: [{ url: image, alt: listing.title }] } : {}),
    },
  };
}

function Stars({ rating }: { rating: number }) {
  const full = Math.round(rating);
  return (
    <span role="img" aria-label={`${rating} out of 5 stars`} className="text-amber-500">
      {"★".repeat(full)}
      {"☆".repeat(5 - full)}
    </span>
  );
}

export default async function ListingDetailPage({ params }: PageProps) {
  const { listingId } = await params;
  let data: Awaited<ReturnType<typeof loadDetail>>;
  try {
    data = await loadDetail(listingId);
  } catch {
    return (
      <Alert variant="error">
        This listing could not be loaded right now. Please try again shortly, or{" "}
        <Link href="/marketplace" className="font-medium underline">
          browse the marketplace
        </Link>
        .
      </Alert>
    );
  }
  const { listing, rating, reviews } = data;
  if (!listing) {
    return (
      <EmptyState
        title="This listing is no longer available"
        description="It may have sold out, expired, or been removed. Listings that are not eligible are not shown — their existence is not leaked beyond this message."
      >
        <Button asChild className="mt-2">
          <Link href="/marketplace">Browse the marketplace</Link>
        </Button>
      </EmptyState>
    );
  }
  const discount = discountInfo(listing);
  const diet = dietaryLabel(listing.dietary_classification);
  const mainImage = firstImage(listing);
  const extraImages = (listing.images ?? [])
    .slice()
    .sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0))
    .slice(1);

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl bg-muted">
            {mainImage ? (
              <Image
                src={mainImage}
                alt={listing.images[0]?.alt_text ?? listing.title}
                fill
                sizes="(max-width: 1024px) 100vw, 50vw"
                className="object-cover"
                priority
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center gap-2 text-muted-foreground">
                <ShoppingBag className="h-12 w-12" aria-hidden="true" />
                <span className="text-sm">No photo provided by the store</span>
              </div>
            )}
          </div>
          {extraImages.length > 0 ? (
            <div className="grid grid-cols-3 gap-3">
              {extraImages.map((image) => (
                <div key={image.storage_path} className="relative aspect-square overflow-hidden rounded-lg bg-muted">
                  <Image
                    src={listingImageUrl(image.storage_path)}
                    alt={image.alt_text ?? listing.title}
                    fill
                    sizes="(max-width: 1024px) 33vw, 16vw"
                    className="object-cover"
                    loading="lazy"
                  />
                </div>
              ))}
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap gap-2">
            <Badge>{listingTypeLabel(listing.listing_type)}</Badge>
            {listing.category_name ? <Badge variant="secondary">{listing.category_name}</Badge> : null}
            {diet ? <Badge variant="secondary">{diet}</Badge> : null}
          </div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">{listing.title}</h1>
          <div className="flex items-baseline gap-3">
            <span className="text-3xl font-bold">{formatINR(listing.selling_price, listing.currency)}</span>
            {discount ? (
              <>
                <span className="text-lg text-muted-foreground line-through">
                  {formatINR(listing.reference_value, listing.currency)}
                </span>
                <Badge variant="destructive">
                  Save {formatINR(discount.saved, listing.currency)} ({discount.percent}%)
                </Badge>
              </>
            ) : null}
          </div>
          {listing.description ? <p className="text-muted-foreground">{listing.description}</p> : null}
          {listing.contents_description ? (
            <p>
              <span className="font-medium">What is inside: </span>
              {listing.contents_description}
            </p>
          ) : null}
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-muted-foreground">Available</dt>
              <dd className="font-medium">{listing.available_quantity} left</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Sale ends</dt>
              <dd className="font-medium">
                {new Intl.DateTimeFormat("en-IN", {
                  day: "numeric",
                  month: "short",
                  hour: "numeric",
                  minute: "2-digit",
                  timeZone: listing.store.timezone,
                }).format(new Date(listing.sale_ends_at))}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-muted-foreground">Pickup window</dt>
              <dd className="font-medium">
                {formatPickupWindow(listing.pickup_starts_at, listing.pickup_ends_at, listing.store.timezone)}
              </dd>
            </div>
            {listing.allergen_codes.length > 0 ? (
              <div className="col-span-2">
                <dt className="text-muted-foreground">Allergens</dt>
                <dd className="font-medium">{listing.allergen_codes.join(", ")}</dd>
              </div>
            ) : null}
            {listing.storage_instructions ? (
              <div className="col-span-2">
                <dt className="text-muted-foreground">Storage</dt>
                <dd className="font-medium">{listing.storage_instructions}</dd>
              </div>
            ) : null}
          </dl>

          <Card>
            <CardContent className="flex flex-col gap-3 p-5">
              <p className="flex items-center gap-2 font-semibold">
                <Clock className="h-5 w-5 text-primary" aria-hidden="true" />
                Pickup only — no delivery
              </p>
              <p className="text-sm text-muted-foreground">
                Add this to your cart, then sign in at checkout to reserve
                and pay. Nothing is reserved until the backend confirms
                your reservation.
              </p>
              <AddToCartButton listing={listing} />
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <Link href="/cart">Review cart</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Store className="h-5 w-5 text-primary" aria-hidden="true" />
              {listing.store.name}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2 text-sm">
            <p className="flex items-start gap-2 text-muted-foreground">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
              <span>
                {listing.store.locality ? `${listing.store.locality}, ` : ""}
                {listing.store.city}, {listing.store.state} {listing.store.pincode}
              </span>
            </p>
            <p className="text-muted-foreground">
              Collect during the pickup window shown above. The store address
              shown here is the public store summary from the listing — no
              phone number or private merchant details are published.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Store rating &amp; reviews</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {rating && rating.average_rating !== null ? (
              <p className="flex items-center gap-2">
                <Stars rating={rating.average_rating} />
                <span className="font-semibold">{rating.average_rating.toFixed(2)}</span>
                <span className="text-sm text-muted-foreground">
                  from {rating.total_reviews} public review{rating.total_reviews === 1 ? "" : "s"}
                </span>
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">
                This store has no public reviews yet.
              </p>
            )}
            {reviews.length > 0 ? (
              <ul className="flex flex-col gap-4">
                {reviews.map((review) => (
                  <li key={review.id} className="border-t pt-4 first:border-t-0 first:pt-0">
                    <p className="flex items-center gap-2">
                      <Stars rating={review.rating} />
                      <span className="text-xs text-muted-foreground">
                        {new Intl.DateTimeFormat("en-IN", {
                          day: "numeric",
                          month: "short",
                          year: "numeric",
                        }).format(new Date(review.created_at))}
                      </span>
                    </p>
                    {review.comment ? <p className="mt-1 text-sm">{review.comment}</p> : null}
                    <p className="mt-1 text-xs text-muted-foreground">
                      Public review — reviewer names are not published by SaveBite.
                    </p>
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
