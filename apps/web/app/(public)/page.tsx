import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const metadata: Metadata = {
  title: "SaveBite — Surplus food, rescued at a discount",
  description:
    "Bakeries, cafes, and restaurants list unsold food at a discount. Reserve it, collect it, and stop good food going to waste.",
  alternates: { canonical: "/" },
};

export default function HomePage() {
  return (
    <div className="flex flex-col gap-12">
      <section className="flex flex-col items-start gap-4 py-8">
        <Badge>Surplus-food marketplace</Badge>
        <h1 className="max-w-2xl text-4xl font-bold tracking-tight sm:text-5xl">
          Good food, rescued before it goes to waste.
        </h1>
        <p className="max-w-xl text-lg text-muted-foreground">
          Bakeries, cafes, and restaurants list unsold food at a discount.
          You reserve it, collect it at the shop, and pay there.
        </p>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link href="/marketplace">Browse the marketplace</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/merchant">Sell surplus food</Link>
          </Button>
        </div>
      </section>

      <section aria-label="How it works" className="grid gap-4 sm:grid-cols-3">
        {[
          {
            title: "1. Find a bag",
            description: "Browse surplus bags and items from shops near you.",
          },
          {
            title: "2. Reserve and pay",
            description: "Reserve your bag and pay securely through the checkout.",
          },
          {
            title: "3. Collect at the shop",
            description: "Show your pickup code at the shop during the pickup window.",
          },
        ].map((step) => (
          <Card key={step.title}>
            <CardHeader>
              <CardTitle className="text-lg">{step.title}</CardTitle>
              <CardDescription>{step.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Full marketplace browsing arrives in the next milestone. This
                page proves the structure, navigation, and design system work.
              </p>
            </CardContent>
          </Card>
        ))}
      </section>
    </div>
  );
}
