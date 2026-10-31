import { describe, expect, it } from "vitest";
import {
  dietaryLabel,
  discountInfo,
  filtersToQuery,
  formatINR,
  isValidPincode,
  listingTypeLabel,
  parseMarketplaceFilters,
  validatePriceFilters,
} from "@/lib/marketplace";

const listing = {
  reference_value: "300.00",
  selling_price: "195.00",
} as Parameters<typeof discountInfo>[0];

describe("pincode validation", () => {
  it("accepts six digits starting 1-9 and rejects the rest", () => {
    expect(isValidPincode("110075")).toBe(true);
    expect(isValidPincode("011007")).toBe(false);
    expect(isValidPincode("11007")).toBe(false);
    expect(isValidPincode("1100755")).toBe(false);
    expect(isValidPincode("abc")).toBe(false);
  });
});

describe("price validation", () => {
  it("rejects negatives and min above max", () => {
    expect(validatePriceFilters("-1", undefined)).toHaveLength(1);
    expect(validatePriceFilters(undefined, "-5")).toHaveLength(1);
    expect(validatePriceFilters("500", "100")).toHaveLength(1);
    expect(validatePriceFilters("100", "500")).toHaveLength(0);
    expect(validatePriceFilters(undefined, undefined)).toHaveLength(0);
  });
});

describe("discount math", () => {
  it("computes savings only when reference exceeds selling", () => {
    const info = discountInfo(listing);
    expect(info?.saved).toBeCloseTo(105);
    expect(info?.percent).toBe(35);
    expect(
      discountInfo({ reference_value: "100.00", selling_price: "100.00" } as never),
    ).toBeNull();
    expect(
      discountInfo({ reference_value: "50.00", selling_price: "100.00" } as never),
    ).toBeNull();
  });
});

describe("labels", () => {
  it("maps backend enum values to readable labels", () => {
    expect(listingTypeLabel("surprise_bag")).toBe("Surprise Bag");
    expect(listingTypeLabel("individual_item")).toBe("Individual Item");
    expect(dietaryLabel("vegetarian")).toBe("Veg");
    expect(dietaryLabel("vegan")).toBe("Vegan");
    expect(dietaryLabel("unknown")).toBeNull();
  });
});

describe("INR formatting", () => {
  it("formats with Indian digit grouping", () => {
    expect(formatINR("195.00")).toContain("195");
    expect(formatINR("100000")).toContain("1,00,000");
  });
});

describe("filter URL round-trip", () => {
  it("parses and rebuilds the same query", () => {
    const query =
      "?search=thali&city=New%20Delhi&pincode=110075&category_id=abc&listing_type=surprise_bag&dietary=vegan&min_price=50&max_price=500&sort=lowest_price&page=3";
    const filters = parseMarketplaceFilters(new URLSearchParams(query));
    expect(filters.city).toBe("New Delhi");
    expect(filters.pincode).toBe("110075");
    expect(filters.listing_type).toBe("surprise_bag");
    expect(filters.sort).toBe("lowest_price");
    expect(filters.page).toBe(3);
    const rebuilt = new URLSearchParams(filtersToQuery(filters).slice(1));
    expect(rebuilt.get("search")).toBe("thali");
    expect(rebuilt.get("max_price")).toBe("500");
  });

  it("rejects unknown sort and listing types instead of passing them through", () => {
    const filters = parseMarketplaceFilters(
      new URLSearchParams("?sort=bogus&listing_type=bogus&dietary=bogus"),
    );
    expect(filters.sort).toBe("newest");
    expect(filters.listing_type).toBeUndefined();
    expect(filters.dietary).toBeUndefined();
  });

  it("omits defaults from the query string", () => {
    expect(filtersToQuery({ sort: "newest", page: 1 })).toBe("");
  });
});
