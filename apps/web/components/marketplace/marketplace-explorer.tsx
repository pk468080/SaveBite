"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import type { MarketplaceCategory, MarketplaceListing } from "@savebite/api-client";
import { ApiError, createServices } from "@savebite/api-client";
import { ListingCard } from "@/components/marketplace/listing-card";
import { FilterPanel } from "@/components/marketplace/filter-panel";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import {
  DEFAULT_FILTERS,
  filtersToQuery,
  isValidPincode,
  parseMarketplaceFilters,
  validatePriceFilters,
  type MarketplaceFilters,
} from "@/lib/marketplace";

const PAGE_SIZE = 20;

/**
 * Marketplace explorer. The URL query string is the
 * single source of filter truth: every change writes
 * the URL (router.replace, so back/forward work), and
 * every fetch reads the URL. Filters reset pagination.
 * Requests are debounced for search only; other filter
 * changes fetch immediately. A request sequence guard
 * plus AbortController prevents stale responses from
 * overwriting newer results. No local filtering ever
 * happens: the backend is the only filter engine.
 */
export function MarketplaceExplorer() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters = useMemo(
    () => parseMarketplaceFilters(searchParams),
    [searchParams],
  );

  const [categories, setCategories] = useState<MarketplaceCategory[]>([]);
  const [items, setItems] = useState<MarketplaceListing[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchText, setSearchText] = useState(filters.search ?? "");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const requestSeq = useRef(0);

  const updateUrl = useCallback(
    (next: MarketplaceFilters) => {
      router.replace(`${pathname}${filtersToQuery(next)}`, { scroll: false });
    },
    [pathname, router],
  );

  const patchFilters = useCallback(
    (patch: Partial<MarketplaceFilters>, resetPage = true) => {
      updateUrl({
        ...filters,
        ...patch,
        page: resetPage ? 1 : (patch.page ?? filters.page),
      });
    },
    [filters, updateUrl],
  );

  // Keep the search box in sync when the URL changes
  // (back/forward navigation, hero form submission).
  useEffect(() => {
    setSearchText(filters.search ?? "");
  }, [filters.search]);

  // Debounced search: typing does not fire a request
  // per keystroke, and applying search resets the page.
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (searchText !== (filters.search ?? "")) {
        patchFilters({ search: searchText || undefined });
      }
    }, 400);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText]);

  // Categories load once (guest-safe, anonymous).
  useEffect(() => {
    const services = createServices(createBrowserApiClient());
    let cancelled = false;
    services.marketplace
      .listCategories()
      .then((rows) => {
        if (!cancelled) setCategories(rows);
      })
      .catch(() => {
        // Categories failing must not block listings;
        // the filter panel simply shows no categories.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Listings fetch on every filter/URL change.
  useEffect(() => {
    const invalidPincode =
      filters.pincode !== undefined && filters.pincode !== "" && !isValidPincode(filters.pincode);
    const priceErrors = validatePriceFilters(filters.min_price, filters.max_price);
    if (invalidPincode || priceErrors.length > 0) {
      // Invalid input never reaches the backend: show
      // the validation message and keep prior results.
      setError(
        invalidPincode
          ? "Enter a valid 6-digit pincode."
          : priceErrors.join(" "),
      );
      return;
    }
    const seq = ++requestSeq.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    const services = createServices(createBrowserApiClient());
    services.marketplace
      .listListings({
        city: filters.city,
        pincode: filters.pincode,
        category_id: filters.category_id,
        listing_type: filters.listing_type,
        search: filters.search,
        min_price: filters.min_price ? Number(filters.min_price) : undefined,
        max_price: filters.max_price ? Number(filters.max_price) : undefined,
        dietary: filters.dietary,
        sort: filters.sort,
        page: filters.page,
        page_size: PAGE_SIZE,
      }, { signal: controller.signal })
      .then((page) => {
        if (seq !== requestSeq.current) return;
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err: unknown) => {
        if (seq !== requestSeq.current) return;
        if (err instanceof ApiError && err.code === "TIMEOUT") {
          setError("The request timed out. Please try again.");
          return;
        }
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError("Listings could not be loaded. Please try again.");
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
    return () => controller.abort();
  }, [filters]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const retry = useCallback(() => {
    // Re-run the fetch by nudging the URL (same filters).
    updateUrl({ ...filters });
  }, [filters, updateUrl]);

  const filterPanel = (idPrefix: string) => (
    <FilterPanel
      filters={filters}
      categories={categories}
      onChange={(patch) => patchFilters(patch)}
      onClear={() => updateUrl({ ...DEFAULT_FILTERS })}
      idPrefix={idPrefix}
    />
  );

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Explore Food</h1>
        <p className="text-muted-foreground">
          Surplus food from local stores, at better prices. Pickup only — no delivery.
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <label htmlFor="marketplace-search" className="sr-only">
          Search listings
        </label>
        <Input
          id="marketplace-search"
          type="search"
          value={searchText}
          placeholder="Search food, stores, or items…"
          onChange={(event) => setSearchText(event.target.value)}
          className="flex-1"
        />
        <div className="flex gap-2">
          {searchText ? (
            <Button variant="outline" onClick={() => setSearchText("")}>
              Clear search
            </Button>
          ) : null}
          <Dialog open={drawerOpen} onOpenChange={setDrawerOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="gap-2 lg:hidden">
                <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
                Filters
              </Button>
            </DialogTrigger>
            <DialogContent className="max-h-[90vh] overflow-y-auto">
              <DialogHeader>
                <DialogTitle>Filters</DialogTitle>
              </DialogHeader>
              {filterPanel("mobile")}
              <Button onClick={() => setDrawerOpen(false)}>Show results</Button>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {(filters.city || filters.pincode) && (
        <p className="text-sm text-muted-foreground" role="status">
          Showing results
          {filters.city ? ` in ${filters.city}` : ""}
          {filters.pincode ? ` for pincode ${filters.pincode}` : ""}.
        </p>
      )}

      <div className="flex gap-8">
        <aside className="hidden w-72 shrink-0 lg:block">
          <div className="sticky top-24 rounded-lg border bg-card p-5">{filterPanel("desktop")}</div>
        </aside>

        <div className="min-w-0 flex-1">
          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-label="Loading listings">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="flex flex-col gap-3">
                  <Skeleton className="aspect-[4/3] w-full" />
                  <Skeleton className="h-5 w-3/4" />
                  <Skeleton className="h-4 w-1/2" />
                </div>
              ))}
            </div>
          ) : error ? (
            <ErrorState
              title="Could not load listings"
              description={error}
              onRetry={retry}
            />
          ) : items.length === 0 ? (
            <EmptyState
              title="No listings match your search"
              description="Try a different search term, a wider area, or clear your filters to see everything available."
            >
              <Button variant="outline" onClick={() => updateUrl({ ...DEFAULT_FILTERS })}>
                Clear all filters
              </Button>
            </EmptyState>
          ) : (
            <>
              <p className="mb-4 text-sm text-muted-foreground" role="status">
                {total} listing{total === 1 ? "" : "s"} found
                {totalPages > 1 ? ` · page ${filters.page} of ${totalPages}` : ""}.
              </p>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((listing) => (
                  <ListingCard key={listing.id} listing={listing} />
                ))}
              </div>
              {totalPages > 1 ? (
                <nav aria-label="Marketplace pagination" className="mt-8 flex items-center justify-center gap-2">
                  <Button
                    variant="outline"
                    disabled={filters.page <= 1}
                    onClick={() => patchFilters({ page: filters.page - 1 }, false)}
                  >
                    Previous
                  </Button>
                  <span className="px-2 text-sm text-muted-foreground">
                    Page {filters.page} of {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    disabled={filters.page >= totalPages}
                    onClick={() => patchFilters({ page: filters.page + 1 }, false)}
                  >
                    Next
                  </Button>
                </nav>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
