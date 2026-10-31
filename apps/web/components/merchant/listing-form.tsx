"use client";

import type { MarketplaceCategory } from "@savebite/api-client";
import { useState } from "react";
import {
  allergenCodesFromInput,
  listingTypeLabel,
  validateListingForm,
  type ListingFormValues,
} from "@/lib/merchant";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert } from "@/components/ui/states";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export const EMPTY_LISTING_FORM: ListingFormValues = {
  listing_type: "surprise_bag",
  category_id: "",
  title: "",
  description: "",
  contents_description: "",
  reference_value: "",
  selling_price: "",
  total_quantity: "",
  sale_starts_at: "",
  sale_ends_at: "",
  pickup_starts_at: "",
  pickup_ends_at: "",
  prepared_at: "",
  best_before_at: "",
  allergen_codes: "",
  dietary_classification: "unknown",
  storage_instructions: "",
  food_safety_notes: "",
};

/** Convert a validated form into the exact
 * ListingCreate / ListingUpdate body shape. */
export function listingFormToBody(values: ListingFormValues): Record<string, unknown> {
  return {
    listing_type: values.listing_type,
    category_id: values.category_id || null,
    title: values.title.trim(),
    description: values.description.trim() || null,
    contents_description: values.contents_description.trim() || null,
    reference_value: values.reference_value,
    selling_price: values.selling_price,
    total_quantity: Number(values.total_quantity),
    sale_starts_at: values.sale_starts_at ? new Date(values.sale_starts_at).toISOString() : null,
    sale_ends_at: new Date(values.sale_ends_at).toISOString(),
    pickup_starts_at: new Date(values.pickup_starts_at).toISOString(),
    pickup_ends_at: new Date(values.pickup_ends_at).toISOString(),
    prepared_at: values.prepared_at ? new Date(values.prepared_at).toISOString() : null,
    best_before_at: values.best_before_at ? new Date(values.best_before_at).toISOString() : null,
    allergen_codes: allergenCodesFromInput(values.allergen_codes),
    dietary_classification: values.dietary_classification,
    storage_instructions: values.storage_instructions.trim() || null,
    food_safety_notes: values.food_safety_notes.trim() || null,
  };
}

/**
 * Listing form (W4, M4). Fields are exactly the
 * ListingCreate columns. Listings are created as
 * draft by the backend — status, published_at and
 * inventory counters are never sent, and this form
 * never offers them. For surprise bags the
 * contents description says what kind of items the
 * bag may contain; the exact selection may vary.
 */
export function ListingForm({
  initial,
  categories,
  submitLabel,
  onSubmit,
  lockType = false,
}: {
  initial: ListingFormValues;
  categories: MarketplaceCategory[];
  submitLabel: string;
  onSubmit: (values: ListingFormValues) => Promise<void>;
  lockType?: boolean;
}) {
  const [values, setValues] = useState<ListingFormValues>(initial);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof ListingFormValues>(key: K, value: ListingFormValues[K]) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const problem = validateListingForm(values);
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    try {
      await onSubmit(values);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Listing could not be saved.");
    } finally {
      setSubmitting(false);
    }
  }

  const field = (label: string, children: React.ReactNode, hint?: string) => (
    <label className="flex flex-col gap-1 text-sm">
      <span>{label}</span>
      {children}
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </label>
  );

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {field(
        "Listing type *",
        <Select
          value={values.listing_type}
          onValueChange={(value) => set("listing_type", value as ListingFormValues["listing_type"])}
          disabled={lockType}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="surprise_bag">{listingTypeLabel("surprise_bag")}</SelectItem>
            <SelectItem value="individual_item">{listingTypeLabel("individual_item")}</SelectItem>
          </SelectContent>
        </Select>,
        values.listing_type === "surprise_bag"
          ? "A bundle of surplus items whose exact selection may vary."
          : "One specific surplus item with its own description, price and quantity.",
      )}
      {field(
        "Category (optional)",
        <Select
          value={values.category_id || "none"}
          onValueChange={(value) => set("category_id", value === "none" ? "" : value)}
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">No category</SelectItem>
            {categories.map((category) => (
              <SelectItem key={category.id} value={category.id}>
                {category.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>,
      )}
      {field(
        "Title *",
        <Input value={values.title} onChange={(event) => set("title", event.target.value)} maxLength={200} required />,
      )}
      {field(
        "Description",
        <Input value={values.description} onChange={(event) => set("description", event.target.value)} maxLength={5000} />,
      )}
      {field(
        "Contents description",
        <Input value={values.contents_description} onChange={(event) => set("contents_description", event.target.value)} maxLength={5000} />,
        "For surprise bags: what kind of items the bag may contain.",
      )}
      <div className="grid gap-4 sm:grid-cols-3">
        {field(
          "Reference / original value (₹) *",
          <Input value={values.reference_value} onChange={(event) => set("reference_value", event.target.value)} inputMode="decimal" required />,
          "0 or more.",
        )}
        {field(
          "Selling price (₹) *",
          <Input value={values.selling_price} onChange={(event) => set("selling_price", event.target.value)} inputMode="decimal" required />,
          "Must be more than 0.",
        )}
        {field(
          "Total quantity *",
          <Input value={values.total_quantity} onChange={(event) => set("total_quantity", event.target.value)} inputMode="numeric" required />,
          "Whole number above 0.",
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {field(
          "Sale starts (optional)",
          <Input type="datetime-local" value={values.sale_starts_at} onChange={(event) => set("sale_starts_at", event.target.value)} />,
          "Blank means the backend default (now).",
        )}
        {field(
          "Sale ends *",
          <Input type="datetime-local" value={values.sale_ends_at} onChange={(event) => set("sale_ends_at", event.target.value)} required />,
        )}
        {field(
          "Pickup starts *",
          <Input type="datetime-local" value={values.pickup_starts_at} onChange={(event) => set("pickup_starts_at", event.target.value)} required />,
        )}
        {field(
          "Pickup ends *",
          <Input type="datetime-local" value={values.pickup_ends_at} onChange={(event) => set("pickup_ends_at", event.target.value)} required />,
          "Must be after pickup start and not before sale end.",
        )}
        {field(
          "Prepared at (optional)",
          <Input type="datetime-local" value={values.prepared_at} onChange={(event) => set("prepared_at", event.target.value)} />,
        )}
        {field(
          "Best before (optional)",
          <Input type="datetime-local" value={values.best_before_at} onChange={(event) => set("best_before_at", event.target.value)} />,
        )}
      </div>
      {field(
        "Dietary classification",
        <Select value={values.dietary_classification} onValueChange={(value) => set("dietary_classification", value)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {["vegetarian", "non_vegetarian", "vegan", "egg", "unknown"].map((diet) => (
              <SelectItem key={diet} value={diet}>
                {diet.replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>,
      )}
      {field(
        "Allergen codes (comma separated)",
        <Input value={values.allergen_codes} onChange={(event) => set("allergen_codes", event.target.value)} placeholder="milk, nuts" />,
        "Lowercase letters, digits, underscores or hyphens. The database has no closed code list.",
      )}
      {field(
        "Storage instructions",
        <Input value={values.storage_instructions} onChange={(event) => set("storage_instructions", event.target.value)} maxLength={2000} />,
      )}
      {field(
        "Food safety notes",
        <Input value={values.food_safety_notes} onChange={(event) => set("food_safety_notes", event.target.value)} maxLength={2000} />,
      )}
      {error ? <Alert variant="error">{error}</Alert> : null}
      <div>
        <Button type="submit" disabled={submitting}>
          {submitting ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
