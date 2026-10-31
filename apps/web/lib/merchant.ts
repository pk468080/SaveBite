/**
 * Merchant portal helpers (W4). Labels mirror the
 * backend enums exactly; validation mirrors the
 * backend rules so the form fails fast, but the
 * backend remains the authority and its error is
 * always shown when it disagrees.
 */

export const BUSINESS_TYPES = [
  "restaurant",
  "bakery",
  "cafe",
  "supermarket",
  "hotel",
  "cloud_kitchen",
  "grocery_store",
  "food_manufacturer",
  "sweet_shop",
  "other",
] as const;

export function businessTypeLabel(value: string): string {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function merchantStatusLabel(status: string): string {
  switch (status) {
    case "pending_review":
      return "Pending review";
    case "additional_information_required":
      return "More information needed";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "suspended":
      return "Suspended";
    default:
      return status;
  }
}

export function verificationLabel(status: string): string {
  switch (status) {
    case "pending":
      return "Verification pending";
    case "under_review":
      return "Verification under review";
    case "verified":
      return "Verified";
    case "rejected":
      return "Verification rejected";
    case "expired":
      return "Verification expired";
    default:
      return status;
  }
}

export function storeStatusLabel(status: string): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "active":
      return "Active";
    case "inactive":
      return "Inactive";
    case "suspended":
      return "Suspended";
    default:
      return status;
  }
}

export function listingStatusLabel(status: string): string {
  switch (status) {
    case "draft":
      return "Draft";
    case "scheduled":
      return "Scheduled";
    case "active":
      return "Active";
    case "paused":
      return "Paused";
    case "sold_out":
      return "Sold out";
    case "expired":
      return "Expired";
    case "cancelled":
      return "Cancelled";
    default:
      return status;
  }
}

export function listingTypeLabel(value: string): string {
  return value === "surprise_bag" ? "Surprise Bag" : "Individual Item";
}

/** Allowed transitions through the backend API
 * (M4 _TRANSITIONS). Publish and resume both move
 * a listing to active; there is no transition into
 * scheduled, sold_out or expired from the portal. */
export function allowedListingActions(status: string): string[] {
  switch (status) {
    case "draft":
    case "scheduled":
      return ["publish", "cancel"];
    case "active":
      return ["pause", "cancel"];
    case "paused":
      return ["resume", "cancel"];
    case "sold_out":
    case "expired":
      return ["cancel"];
    default:
      return [];
  }
}

export const PINCODE_PATTERN = /^[1-9][0-9]{5}$/;
export const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
export const ALLERGEN_PATTERN = /^[a-z0-9_-]+$/;

export function validateIndianMobile(value: string): string | null {
  const cleaned = value.replace(/[\s-]/g, "");
  if (cleaned.startsWith("+91")) {
    const digits = cleaned.slice(3);
    if (cleaned.length !== 13 || !/^[0-9]+$/.test(digits) || !"6789".includes(digits.charAt(0))) {
      return "Enter a valid Indian mobile number";
    }
    return null;
  }
  if (cleaned.length !== 10 || !/^[0-9]+$/.test(cleaned) || !"6789".includes(cleaned.charAt(0))) {
    return "Enter a valid Indian mobile number";
  }
  return null;
}

export interface ListingFormValues {
  listing_type: "surprise_bag" | "individual_item";
  category_id: string;
  title: string;
  description: string;
  contents_description: string;
  reference_value: string;
  selling_price: string;
  total_quantity: string;
  sale_starts_at: string;
  sale_ends_at: string;
  pickup_starts_at: string;
  pickup_ends_at: string;
  prepared_at: string;
  best_before_at: string;
  allergen_codes: string;
  dietary_classification: string;
  storage_instructions: string;
  food_safety_notes: string;
}

/** Mirror of the backend window CHECKs + price /
 * quantity rules. Returns the first problem found,
 * or null when the form is consistent. */
export function validateListingForm(values: ListingFormValues): string | null {
  if (!values.title.trim()) return "Title is required";
  const reference = Number(values.reference_value);
  const price = Number(values.selling_price);
  if (!Number.isFinite(reference) || reference < 0) {
    return "Reference value must be 0 or more";
  }
  if (!Number.isFinite(price) || price <= 0) {
    return "Selling price must be more than 0";
  }
  const quantity = Number(values.total_quantity);
  if (!Number.isInteger(quantity) || quantity <= 0) {
    return "Total quantity must be a whole number above 0";
  }
  if (!values.sale_ends_at || !values.pickup_starts_at || !values.pickup_ends_at) {
    return "Sale end, pickup start and pickup end are required";
  }
  const saleEnd = new Date(values.sale_ends_at).getTime();
  const pickupStart = new Date(values.pickup_starts_at).getTime();
  const pickupEnd = new Date(values.pickup_ends_at).getTime();
  if (Number.isNaN(saleEnd) || Number.isNaN(pickupStart) || Number.isNaN(pickupEnd)) {
    return "Sale and pickup times must be valid dates";
  }
  if (values.sale_starts_at) {
    const saleStart = new Date(values.sale_starts_at).getTime();
    if (!Number.isNaN(saleStart) && !(saleEnd > saleStart)) {
      return "Sale end must be after sale start";
    }
  }
  if (!(pickupEnd > pickupStart)) {
    return "Pickup end must be after pickup start";
  }
  if (!(pickupEnd >= saleEnd)) {
    return "Pickup end must not be before sale end";
  }
  if (values.prepared_at && values.best_before_at) {
    if (new Date(values.best_before_at).getTime() < new Date(values.prepared_at).getTime()) {
      return "Best-before must not be before prepared time";
    }
  }
  for (const code of values.allergen_codes.split(",").map((c) => c.trim().toLowerCase()).filter(Boolean)) {
    if (!ALLERGEN_PATTERN.test(code)) {
      return `Allergen code "${code}" must use only letters, digits, underscores or hyphens`;
    }
  }
  return null;
}

export function allergenCodesFromInput(input: string): string[] {
  const seen = new Set<string>();
  for (const raw of input.split(",")) {
    const code = raw.trim().toLowerCase();
    if (code) seen.add(code);
  }
  return [...seen];
}

/**
 * QR payload handling (M8). The customer QR payload
 * is `SB1:<64-hex-token>`; the verify endpoint
 * accepts the payload and strips the prefix itself,
 * but the portal normalises here too so a pasted
 * raw token and a scanned payload behave the same.
 * Tokens are never logged or stored.
 */
export function normalisePickupToken(input: string): string {
  // Mirror the backend strip: trim, drop the
  // SB1: prefix when present, lowercase (issued
  // tokens are lowercase hex).
  const lowered = input.trim().toLowerCase();
  return lowered.startsWith("sb1:") ? lowered.slice(4) : lowered;
}

export function isValidPickupToken(token: string): boolean {
  // Issued tokens are always 64 lowercase hex
  // chars (M8). Anything else is rejected by the
  // backend route before any RPC call, so the
  // portal says so locally instead of sending a
  // request that cannot succeed.
  return /^[0-9a-f]{64}$/.test(token);
}
