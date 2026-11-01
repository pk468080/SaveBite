"use client";

import { ApiError, createServices, type AdminActivityEvent } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { AccessDenied } from "@/components/admin/access-denied";
import { AdminPager } from "@/components/admin/pager";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { ADMIN_PAGE_SIZE } from "@/lib/admin";
import { formatDateTime } from "@/lib/order-labels";

/**
 * Platform activity (W6, M11). Only recorded
 * order_status_events are returned. Private
 * audit logs (merchant/store review actions),
 * pickup events, and webhook events are NOT
 * readable through the API by design, so no
 * audit-log screen is fabricated here.
 */
export default function AdminActivityPage() {
  const [items, setItems] = useState<AdminActivityEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
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
      .admin.listActivity({
        order_number: search || undefined,
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
          setError(err instanceof Error ? err.message : "Could not load activity.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [search, page]);

  if (denied) return <AccessDenied />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold">Activity</h1>
        <p className="text-sm text-muted-foreground">
          Recorded order status events only. Review actions are recorded in private audit logs
          that this API does not expose, so they are not shown here.
        </p>
      </div>

      <Card>
        <CardContent className="p-4">
          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(searchInput.trim());
              setPage(1);
            }}
          >
            <label className="flex flex-1 flex-col gap-1 text-sm">
              <span>Order number</span>
              <Input
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Search order number"
              />
            </label>
            <Button type="submit">Search</Button>
          </form>
        </CardContent>
      </Card>

      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading activity" />
      ) : items.length === 0 ? (
        <EmptyState title="No activity found" description="Try a different order number." />
      ) : (
        <Card>
          <CardContent className="flex flex-col divide-y p-0">
            {items.map((event, index) => (
              <div key={`${event.order_number}-${event.to_status}-${index}`} className="flex flex-wrap justify-between gap-2 p-4 text-sm">
                <p>
                  Order {event.order_number}: {event.from_status ? `${event.from_status} → ` : ""}
                  {event.to_status}
                  {event.reason ? ` · ${event.reason}` : ""}
                </p>
                <p className="text-muted-foreground">
                  {event.actor_type} · {formatDateTime(event.created_at)}
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      <AdminPager page={page} pageSize={ADMIN_PAGE_SIZE} total={total} onPage={setPage} />
    </div>
  );
}
