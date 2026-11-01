"use client";

import { ApiError, createServices, type AdminMerchantSummary } from "@savebite/api-client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { AdminPager } from "@/components/admin/pager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { ADMIN_PAGE_SIZE, merchantStatusLabel, merchantVerificationLabel } from "@/lib/admin";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Merchant application list (W6, M11). Filters
 * and pagination are server-side: the backend
 * filters by status, verification status and
 * display-name search, and returns one page at
 * a time. Search covers display_name only (the
 * backend documents that legal-name search is
 * not supported), so the hint says so.
 */
const STATUSES = ["pending_review", "additional_information_required", "approved", "rejected", "suspended"];
const VERIFICATIONS = ["pending", "under_review", "verified", "rejected", "expired"];

export default function AdminMerchantsPage() {
  const [items, setItems] = useState<AdminMerchantSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("all");
  const [verification, setVerification] = useState("all");
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDenied(false);
    createServices(createBrowserApiClient())
      .admin.listMerchants({
        status: status === "all" ? undefined : status,
        verification_status: verification === "all" ? undefined : verification,
        search: search || undefined,
        page,
        page_size: ADMIN_PAGE_SIZE,
      })
      .then((data) => {
        if (cancelled) return;
        setItems(data.items);
        setTotal(data.total);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.isUnauthorized || err.isForbidden)) {
          setDenied(true);
        } else {
          setError(err instanceof Error ? err.message : "Could not load merchants.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [status, verification, search, page]);

  if (denied) return <AccessDenied />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Merchant applications</h1>
        <p className="text-sm text-muted-foreground">
          Review merchant applications. Search matches the display name only.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Application status</span>
            <Select value={status} onValueChange={(value) => { setStatus(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {merchantStatusLabel(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm">
            <span>Verification status</span>
            <Select value={verification} onValueChange={(value) => { setVerification(value); setPage(1); }}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All verification states</SelectItem>
                {VERIFICATIONS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {merchantVerificationLabel(value)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
          <form
            className="flex flex-1 items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchInput.trim());
              setPage(1);
            }}
          >
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span>Display name</span>
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search display name"
              />
            </label>
            <Button type="submit">Search</Button>
          </form>
        </CardContent>
      </Card>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading merchants" />
      ) : items.length === 0 ? (
        <EmptyState title="No merchants found" description="Try a different filter or search." />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y p-0">
            {items.map((merchant) => (
              <div key={merchant.id} className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm">
                <div>
                  <Link href={`/admin/merchants/${merchant.id}`} className="font-medium underline underline-offset-4">
                    {merchant.display_name}
                  </Link>
                  <p className="text-muted-foreground">
                    {merchant.legal_name} · {merchant.business_type} · {merchant.store_count}{" "}
                    store(s)
                  </p>
                  <p className="text-muted-foreground">
                    Applied {formatDateTime(merchant.created_at)}
                    {merchant.approved_at ? ` · Approved ${formatDateTime(merchant.approved_at)}` : ""}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-medium">{merchantStatusLabel(merchant.status)}</p>
                  <p className="text-muted-foreground">
                    {merchantVerificationLabel(merchant.verification_status)}
                  </p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      <AdminPager page={page} pageSize={ADMIN_PAGE_SIZE} total={total} onPage={setPage} />
    </div>
  );
}
