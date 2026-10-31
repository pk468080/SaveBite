import type { Metadata } from "next";
import Link from "next/link";
import { Clock, HandHeart, MapPin, Search, ShoppingBag, Wallet } from "lucide-react";
import type { MarketplaceCategory, MarketplaceListing } from "@savebite/api-client";
import { ListingCard } from "@/components/marketplace/listing-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/states";
import { createPublicServices } from "@/lib/api/public";

export const metadata: Metadata = {
  title: "SaveBite — Surplus food, rescued at a discount",
  description:
    "Discover surplus food from local restaurants, bakeries and food stores at better prices. Choose a Surprise Bag or pick exactly what you love, then collect it at the store.",
  alternates: { canonical: "/" },
};

// Marketplace data changes constantly (availability,
// sale windows), so the homepage always fetches fresh
// data per request — never a stale cached inventory.
async function loadHomepageData(): Promise<{
  categories: MarketplaceCategory[] | null;
  endingSoon: MarketplaceListing[] | null;
  newest: MarketplaceListing[] | null;
}> {
  const services = createPublicServices();
  const [categories, endingSoon, newest] = await Promise.all([
    services.marketplace.listCategories().catch(() => null),
    services.marketplace
      .listListings({ sort: "ending_soon", page_size: 8 })
      .then((page) => page.items)
      .catch(() => null),
    services.marketplace
      .listListings({ sort: "newest", page_size: 8 })
      .then((page) => page.items)
      .catch(() => null),
  ]);
  return { categories, endingSoon, newest };
}

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">{title}</h2>
      <p className="text-muted-foreground">{description}</p>
    </div>
  );
}

export default async function HomePage() {
  const { categories, endingSoon, newest } = await loadHomepageData();
  return (
    <div className="flex flex-col gap-16">
      {/* Hero */}
      <section className="grid items-center gap-8 py-6 lg:grid-cols-2">
        <div className="flex flex-col items-start gap-5">
          <p className="text-sm font-semibold uppercase tracking-wide text-primary">
            Good Food. Better Prices. Less Waste.
          </p>
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Rescue Great Food. Save More. Waste Less.
          </h1>
          <p className="max-w-xl text-lg text-muted-foreground">
            Discover delicious surplus food from local restaurants, bakeries
            and food stores at better prices. Find a surprise or pick exactly
            what you love — then collect it at the store.
          </p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/marketplace">Explore Food</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link href="#how-it-works">How It Works</Link>
            </Button>
          </div>
          {/* Location entry: a plain GET form, so the
              chosen location lands in a shareable URL.
              No geolocation, no IP inference, no assumed
              city — the visitor types it. */}
          <form action="/marketplace" method="get" className="flex w-full max-w-xl flex-col gap-2 sm:flex-row">
            <label htmlFor="hero-city" className="sr-only">
              City
            </label>
            <input
              id="hero-city"
              name="city"
              type="text"
              placeholder="City (for example, New Delhi)"
              className="flex h-11 flex-1 rounded-md border border-input bg-background px-3 text-sm"
            />
            <label htmlFor="hero-pincode" className="sr-only">
              Pincode
            </label>
            <input
              id="hero-pincode"
              name="pincode"
              type="text"
              inputMode="numeric"
              placeholder="Pincode (6 digits)"
              pattern="[1-9][0-9]{5}"
              title="Enter a valid 6-digit Indian pincode"
              className="flex h-11 w-full rounded-md border border-input bg-background px-3 text-sm sm:w-44"
            />
            <Button type="submit" size="lg" className="gap-2">
              <Search className="h-4 w-4" aria-hidden="true" />
              Search
            </Button>
          </form>
          <p className="text-sm text-muted-foreground">
            Pickup only — SaveBite does not deliver. You collect your order
            from the store during its pickup window.
          </p>
        </div>
        <div
          aria-hidden="true"
          className="flex aspect-[4/3] flex-col items-center justify-center gap-4 rounded-2xl bg-gradient-to-br from-green-700 via-green-600 to-emerald-500 p-8 text-white"
        >
          <ShoppingBag className="h-16 w-16" />
          <p className="text-center text-2xl font-bold">Surprise Bags &amp; Individual Items</p>
          <p className="max-w-sm text-center text-white/90">
            A surprise selection at a better price — or the exact item you
            want. Every listing shows its real price, store, and pickup window.
          </p>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="flex scroll-mt-20 flex-col gap-6">
        <SectionHeading
          title="How it works"
          description="Three steps between a shop's surplus and your table."
        />
        <div className="grid gap-4 sm:grid-cols-3">
          {[
            {
              icon: Search,
              title: "1. Discover",
              description: "Find available surplus food nearby — Surprise Bags and Individual Items from local stores.",
            },
            {
              icon: Wallet,
              title: "2. Reserve and Pay",
              description: "Choose your food and pay securely. (Reservation and checkout arrive in the next milestone.)",
            },
            {
              icon: Clock,
              title: "3. Pick Up",
              description: "Collect your order from the store during its pickup window. Show your pickup code at the counter.",
            },
          ].map((step) => (
            <Card key={step.title}>
              <CardHeader>
                <step.icon className="h-8 w-8 text-primary" aria-hidden="true" />
                <CardTitle className="text-lg">{step.title}</CardTitle>
                <CardDescription>{step.description}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      </section>

      {/* Categories — real API data only */}
      <section className="flex flex-col gap-6">
        <SectionHeading
          title="Explore categories"
          description="Categories offered by stores on SaveBite right now."
        />
        {categories === null ? (
          <Alert variant="error">
            Categories could not be loaded right now. You can still{" "}
            <Link href="/marketplace" className="font-medium underline">
              browse all listings
            </Link>
            .
          </Alert>
        ) : categories.length === 0 ? (
          <EmptyState
            title="No categories yet"
            description="No store has listed a categorised item yet. Check the marketplace for whatever is available today."
          />
        ) : (
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {categories.map((category) => (
              <li key={category.id}>
                <Link
                  href={`/marketplace?category_id=${category.id}`}
                  className="block rounded-lg border bg-card p-4 font-medium transition-shadow hover:shadow-md"
                >
                  {category.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Listings sorted by the backend — labelled by
          their real sort, never "featured" or "popular". */}
      <section className="flex flex-col gap-6">
        <div className="flex items-end justify-between gap-4">
          <SectionHeading
            title="Ending soon"
            description="Sale windows closing soonest, straight from the marketplace."
          />
          <Button asChild variant="outline">
            <Link href="/marketplace?sort=ending_soon">View all</Link>
          </Button>
        </div>
        {endingSoon === null ? (
          <Alert variant="error">Listings could not be loaded right now. Please try again shortly.</Alert>
        ) : endingSoon.length === 0 ? (
          <EmptyState
            title="Nothing available right now"
            description="No eligible listings at the moment. Availability changes as stores list surplus food — check back soon."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {endingSoon.map((listing) => (
              <ListingCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-6">
        <div className="flex items-end justify-between gap-4">
          <SectionHeading
            title="Newly listed"
            description="The most recently listed surplus food."
          />
          <Button asChild variant="outline">
            <Link href="/marketplace?sort=newest">View all</Link>
          </Button>
        </div>
        {newest === null ? (
          <Alert variant="error">Listings could not be loaded right now. Please try again shortly.</Alert>
        ) : newest.length === 0 ? (
          <EmptyState
            title="Nothing available right now"
            description="No eligible listings at the moment. Availability changes as stores list surplus food — check back soon."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {newest.map((listing) => (
              <ListingCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </section>

      {/* Trust / sustainability — no invented statistics */}
      <section id="about" className="flex scroll-mt-20 flex-col gap-6">
        <SectionHeading
          title="Why surplus food matters"
          description="Perfectly good food goes unsold every day. SaveBite gives it a second chance."
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader>
              <HandHeart className="h-8 w-8 text-primary" aria-hidden="true" />
              <CardTitle className="text-lg">Less waste</CardTitle>
              <CardDescription>
                Food that would otherwise be thrown away finds a home instead.
                We report only verified figures — no invented impact statistics.
              </CardDescription>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <Wallet className="h-8 w-8 text-primary" aria-hidden="true" />
              <CardTitle className="text-lg">Better prices</CardTitle>
              <CardDescription>
                Stores set a reference value and a selling price. You see both,
                and any saving shown is computed from those real numbers.
              </CardDescription>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader>
              <MapPin className="h-8 w-8 text-primary" aria-hidden="true" />
              <CardTitle className="text-lg">Local stores</CardTitle>
              <CardDescription>
                Every listing names its store, locality, city, and pickup
                window. You always know exactly where to collect.
              </CardDescription>
            </CardHeader>
          </Card>
        </div>
        <Card>
          <CardContent className="flex flex-col items-start gap-3 p-6">
            <p className="text-lg font-semibold">Ready to explore?</p>
            <p className="text-muted-foreground">
              Browse what is available near you. When you are ready to buy,
              sign in or create an account — reservation and checkout arrive
              in the next milestone.
            </p>
            <Button asChild>
              <Link href="/marketplace">Explore Food</Link>
            </Button>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
