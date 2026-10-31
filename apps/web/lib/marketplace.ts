import type {
  DietaryValue,
  ListingTypeValue,
  MarketplaceListing,
  MarketplaceSortValue,
} from "@savebite/api-client";
import { config } from "@/lib/config";

/**
 * Marketplace presentation helpers (W2). Pure
 * functions, unit tested, no backend calls here.
 *
 * Images: the API returns a STORAGE PATH in the public
 * listing-media bucket, never a URL. The public bucket
 * URL pattern is
 * {SUPABASE_URL}/storage/v1/object/public/listing-media/{path}.
 * That is the documented resolution, not a guessed
 * storage URL — and paths are never built from user
 * input, only from API-returned storage paths.
 */

export function listingImageUrl(storagePath: string): string {
  return `${config.supabaseUrl.replace(/\/$/, "")}/storage/v1/object/public/listing-media/${storagePath}`;
}

export function firstImage(listing: MarketplaceListing): string | null {
  const sorted = [...(listing.images ?? [])].sort(
    (a, b) => (a.display_order ?? 0) - (b.display_order ?? 0),
  );
  const first = sorted[0];
  return first ? listingImageUrl(first.storage_path) : null;
}

export function formatINR(amount: string | number, currency = "INR"): string {
  const value = typeof amount === "string" ? Number(amount) : amount;
  if (!Number.isFinite(value)) {
    return String(amount);
  }
  if (currency === "INR") {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(value);
  }
  return `${value} ${currency}`;
}

/** Discount is shown ONLY when the reference value
 * genuinely exceeds the selling price. Otherwise null
 * — never an invented percentage. */
export function discountInfo(listing: MarketplaceListing): {
  saved: number;
  percent: number;
} | null {
  const reference = Number(listing.reference_value);
  const selling = Number(listing.selling_price);
  if (!Number.isFinite(reference) || !Number.isFinite(selling)) {
    return null;
  }
  if (reference <= selling) {
    return null;
  }
  return {
    saved: reference - selling,
    percent: Math.round(((reference - selling) / reference) * 100),
  };
}

export const LISTING_TYPE_LABELS: Record<ListingTypeValue, string> = {
  surprise_bag: "Surprise Bag",
  individual_item: "Individual Item",
};

export function listingTypeLabel(value: string): string {
  return LISTING_TYPE_LABELS[value as ListingTypeValue] ?? value;
}

export const DIETARY_LABELS: Record<DietaryValue, string | null> = {
  vegetarian: "Veg",
  non_vegetarian: "Non-veg",
  vegan: "Vegan",
  egg: "Contains egg",
  unknown: null,
};

export function dietaryLabel(value: string): string | null {
  return DIETARY_LABELS[value as DietaryValue] ?? null;
}

export const SORT_OPTIONS: Array<{ value: MarketplaceSortValue; label: string }> = [
  { value: "newest", label: "Newest first" },
  { value: "lowest_price", label: "Price: Low to High" },
  { value: "highest_price", label: "Price: High to Low" },
  { value: "ending_soon", label: "Ending Soon" },
];

/** Indian pincode: exactly six digits, first digit 1–9
 * (the backend enforces the same pattern). */
export const PINCODE_PATTERN = /^[1-9][0-9]{5}$/;

export function isValidPincode(value: string): boolean {
  return PINCODE_PATTERN.test(value.trim());
}

export interface MarketplaceFilters {
  search?: string;
  city?: string;
  pincode?: string;
  category_id?: string;
  listing_type?: ListingTypeValue;
  dietary?: DietaryValue;
  min_price?: string;
  max_price?: string;
  sort: MarketplaceSortValue;
  page: number;
}

export const DEFAULT_FILTERS: MarketplaceFilters = {
  sort: "newest",
  page: 1,
};

export function parseMarketplaceFilters(params: URLSearchParams): MarketplaceFilters {
  const sortRaw = params.get("sort");
  const sort: MarketplaceSortValue = SORT_OPTIONS.some((o) => o.value === sortRaw)
    ? (sortRaw as MarketplaceSortValue)
    : "newest";
  const page = Math.max(1, Number(params.get("page")) || 1);
  const listingType = params.get("listing_type");
  const dietary = params.get("dietary");
  return {
    search: params.get("search") ?? undefined,
    city: params.get("city") ?? undefined,
    pincode: params.get("pincode") ?? undefined,
    category_id: params.get("category_id") ?? undefined,
    listing_type:
      listingType === "surprise_bag" || listingType === "individual_item"
        ? listingType
        : undefined,
    dietary:
      ["vegetarian", "non_vegetarian", "vegan", "egg", "unknown"].includes(dietary ?? "")
        ? (dietary as DietaryValue)
        : undefined,
    min_price: params.get("min_price") ?? undefined,
    max_price: params.get("max_price") ?? undefined,
    sort,
    page,
  };
}

/** Price validation, mirroring the backend rules:
 * non-negative, min must not exceed max. Returns
 * error messages (empty = valid). */
export function validatePriceFilters(
  minPrice?: string,
  maxPrice?: string,
): string[] {
  const errors: string[] = [];
  const min = minPrice === undefined || minPrice === "" ? undefined : Number(minPrice);
  const max = maxPrice === undefined || maxPrice === "" ? undefined : Number(maxPrice);
  if (min !== undefined && (!Number.isFinite(min) || min < 0)) {
    errors.push("Minimum price must not be negative.");
  }
  if (max !== undefined && (!Number.isFinite(max) || max < 0)) {
    errors.push("Maximum price must not be negative.");
  }
  if (
    min !== undefined &&
    max !== undefined &&
    Number.isFinite(min) &&
    Number.isFinite(max) &&
    min > max
  ) {
    errors.push("Minimum price must not exceed maximum price.");
  }
  return errors;
}

export function filtersToQuery(filters: MarketplaceFilters): string {
  const params = new URLSearchParams();
  if (filters.search) params.set("search", filters.search);
  if (filters.city) params.set("city", filters.city);
  if (filters.pincode) params.set("pincode", filters.pincode);
  if (filters.category_id) params.set("category_id", filters.category_id);
  if (filters.listing_type) params.set("listing_type", filters.listing_type);
  if (filters.dietary) params.set("dietary", filters.dietary);
  if (filters.min_price) params.set("min_price", filters.min_price);
  if (filters.max_price) params.set("max_price", filters.max_price);
  if (filters.sort !== "newest") params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Pickup window display in the store's timezone
 * (default Asia/Kolkata). Times are instants; the
 * timezone only affects how they are shown. */
export function formatPickupWindow(
  startsAt: string,
  endsAt: string,
  timeZone = "Asia/Kolkata",
): string {
  const format = (value: string, withDate: boolean) =>
    new Intl.DateTimeFormat("en-IN", {
      timeZone,
      ...(withDate
        ? { day: "numeric", month: "short" }
        : {}),
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value));
  const startDate = new Date(startsAt);
  const endDate = new Date(endsAt);
  const sameDay =
    startDate.toLocaleDateString("en-CA", { timeZone }) ===
    endDate.toLocaleDateString("en-CA", { timeZone });
  if (sameDay) {
    return `${format(startsAt, true)} – ${format(endsAt, false)}`;
  }
  return `${format(startsAt, true)} – ${format(endsAt, true)}`;
}
