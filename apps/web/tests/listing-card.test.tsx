import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { MarketplaceListing } from "@savebite/api-client";
import { ListingCard } from "@/components/marketplace/listing-card";

afterEach(() => cleanup());

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/image", () => ({
  default: ({ src, alt }: { src: string; alt: string }) => (
    <img src={src} alt={alt} />
  ),
}));

const baseListing: MarketplaceListing = {
  id: "11111111-1111-4111-8111-111111111111",
  store: {
    id: "22222222-2222-4222-8222-222222222222",
    name: "Sharma Foods",
    locality: "Dwarka Sector 7",
    city: "New Delhi",
    state: "Delhi",
    pincode: "110075",
    timezone: "Asia/Kolkata",
  },
  listing_type: "surprise_bag",
  category_id: null,
  category_name: "Bakery",
  title: "Evening Bakery Bag",
  description: "Fresh breads and pastries.",
  contents_description: null,
  reference_value: "300.00",
  selling_price: "195.00",
  currency: "INR",
  available_quantity: 5,
  dietary_classification: "vegetarian",
  allergen_codes: ["gluten"],
  storage_instructions: null,
  sale_starts_at: "2026-10-31T10:00:00+00:00",
  sale_ends_at: "2026-10-31T17:00:00+00:00",
  pickup_starts_at: "2026-10-31T18:00:00+00:00",
  pickup_ends_at: "2026-10-31T21:00:00+00:00",
  prepared_at: null,
  best_before_at: null,
  images: [
    {
      storage_path: "11111111-1111-4111-8111-111111111111/photo.jpg",
      alt_text: "Bakery bag",
      display_order: 0,
    },
  ],
};

describe("ListingCard", () => {
  it("shows real title, store, price, computed discount, and detail link", () => {
    render(<ListingCard listing={baseListing} />);
    expect(screen.getByText("Evening Bakery Bag")).toBeInTheDocument();
    expect(screen.getByText(/Sharma Foods/)).toBeInTheDocument();
    expect(screen.getByText(/195/)).toBeInTheDocument();
    expect(screen.getByText(/Save 35%/)).toBeInTheDocument();
    expect(screen.getByText(/5 available/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /View details for Evening Bakery Bag/ }),
    ).toHaveAttribute("href", "/marketplace/11111111-1111-4111-8111-111111111111");
    expect(screen.getByRole("img")).toHaveAttribute("alt", "Bakery bag");
  });

  it("shows no discount and a fallback visual when there is no image", () => {
    render(
      <ListingCard
        listing={{ ...baseListing, images: [], reference_value: "195.00" }}
      />,
    );
    expect(screen.queryByText(/Save/)).not.toBeInTheDocument();
    expect(screen.getByText(/No photo provided by the store/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy|checkout|reserve/i })).not.toBeInTheDocument();
  });
});
