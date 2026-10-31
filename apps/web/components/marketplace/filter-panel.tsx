"use client";

import type { MarketplaceCategory } from "@savebite/api-client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import {
  DIETARY_LABELS,
  isValidPincode,
  LISTING_TYPE_LABELS,
  SORT_OPTIONS,
  validatePriceFilters,
  type MarketplaceFilters,
} from "@/lib/marketplace";

export interface FilterPanelProps {
  filters: MarketplaceFilters;
  categories: MarketplaceCategory[];
  onChange: (patch: Partial<MarketplaceFilters>) => void;
  onClear: () => void;
  /** Prefix for input ids: the panel is rendered twice
   * (desktop sidebar + mobile drawer), and duplicate
   * ids would break label association on mobile. */
  idPrefix: string;
}

/**
 * Marketplace filter form (used in the desktop sidebar
 * and the mobile drawer — one component, no duplicates).
 * Every control maps to exactly one backend parameter:
 * single category only (the API does not support
 * multi-category), exact dietary values, validated
 * pincode and price rules. Nothing here filters locally.
 */
export function FilterPanel({ filters, categories, onChange, onClear, idPrefix }: FilterPanelProps) {
  const priceErrors = validatePriceFilters(filters.min_price, filters.max_price);
  const pincodeError =
    filters.pincode !== undefined && filters.pincode !== "" && !isValidPincode(filters.pincode)
      ? "Enter a valid 6-digit pincode."
      : null;
  const activeCount = [
    filters.city,
    filters.pincode,
    filters.category_id,
    filters.listing_type,
    filters.dietary,
    filters.min_price,
    filters.max_price,
  ].filter(Boolean).length;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">Filters</h2>
        <div className="flex items-center gap-2">
          {activeCount > 0 ? <Badge variant="secondary">{activeCount} active</Badge> : null}
          <Button variant="ghost" size="sm" onClick={onClear} disabled={activeCount === 0}>
            Clear all
          </Button>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-city`} className="text-sm font-medium">
          City
        </label>
        <Input
          id={`${idPrefix}-city`}
          value={filters.city ?? ""}
          placeholder="For example, New Delhi"
          onChange={(event) => onChange({ city: event.target.value || undefined })}
        />
        <p className="text-xs text-muted-foreground">Matches the store city exactly (case-insensitive).</p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-pincode`} className="text-sm font-medium">
          Pincode
        </label>
        <Input
          id={`${idPrefix}-pincode`}
          value={filters.pincode ?? ""}
          inputMode="numeric"
          placeholder="6-digit pincode"
          onChange={(event) => onChange({ pincode: event.target.value || undefined })}
          aria-invalid={Boolean(pincodeError)}
        />
        {pincodeError ? (
          <p role="alert" className="text-sm text-destructive">{pincodeError}</p>
        ) : null}
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-category`} className="text-sm font-medium">
          Category
        </label>
        <Select
          value={filters.category_id ?? "all"}
          onValueChange={(value) => onChange({ category_id: value === "all" ? undefined : value })}
        >
          <SelectTrigger id={`${idPrefix}-category`}>
            <SelectValue placeholder="All categories" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {categories.map((category) => (
              <SelectItem key={category.id} value={category.id}>
                {category.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-type`} className="text-sm font-medium">
          Listing type
        </label>
        <Select
          value={filters.listing_type ?? "all"}
          onValueChange={(value) =>
            onChange({
              listing_type:
                value === "all" ? undefined : (value as keyof typeof LISTING_TYPE_LABELS),
            })
          }
        >
          <SelectTrigger id={`${idPrefix}-type`}>
            <SelectValue placeholder="All types" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            {(Object.keys(LISTING_TYPE_LABELS) as Array<keyof typeof LISTING_TYPE_LABELS>).map((key) => (
              <SelectItem key={key} value={key}>
                {LISTING_TYPE_LABELS[key]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-dietary`} className="text-sm font-medium">
          Dietary preference
        </label>
        <Select
          value={filters.dietary ?? "all"}
          onValueChange={(value) =>
            onChange({ dietary: value === "all" ? undefined : (value as keyof typeof DIETARY_LABELS) })
          }
        >
          <SelectTrigger id={`${idPrefix}-dietary`}>
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any</SelectItem>
            {(Object.keys(DIETARY_LABELS) as Array<keyof typeof DIETARY_LABELS>)
              .filter((key) => key !== "unknown")
              .map((key) => (
                <SelectItem key={key} value={key}>
                  {DIETARY_LABELS[key]}
                </SelectItem>
              ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium" id={`${idPrefix}-price-label`}>
          Price range (₹)
        </span>
        <div className="flex items-center gap-2" aria-labelledby={`${idPrefix}-price-label`}>
          <label htmlFor={`${idPrefix}-min-price`} className="sr-only">
            Minimum price
          </label>
          <Input
            id={`${idPrefix}-min-price`}
            type="number"
            min={0}
            value={filters.min_price ?? ""}
            placeholder="Min"
            onChange={(event) => onChange({ min_price: event.target.value || undefined })}
          />
          <span aria-hidden="true">–</span>
          <label htmlFor={`${idPrefix}-max-price`} className="sr-only">
            Maximum price
          </label>
          <Input
            id={`${idPrefix}-max-price`}
            type="number"
            min={0}
            value={filters.max_price ?? ""}
            placeholder="Max"
            onChange={(event) => onChange({ max_price: event.target.value || undefined })}
          />
        </div>
        {priceErrors.map((error) => (
          <p key={error} role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ))}
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={`${idPrefix}-sort`} className="text-sm font-medium">
          Sort by
        </label>
        <Select
          value={filters.sort}
          onValueChange={(value) => onChange({ sort: value as (typeof SORT_OPTIONS)[number]["value"] })}
        >
          <SelectTrigger id={`${idPrefix}-sort`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}
