"use client";

import { ApiError, createServices } from "@savebite/api-client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert, EmptyState, LoadingState } from "@/components/ui/states";
import { createBrowserApiClient } from "@/lib/api/browser";
import { formatDateTime } from "@/lib/order-labels";
import type { NotificationItem } from "@savebite/api-client";

/**
 * Merchant notifications (W4, M12 read APIs
 * only). Generation is not active yet, so this
 * page shows only records that exist — no mock
 * merchant alerts, and no claim that alerts will
 * arrive automatically. Preferences are NOT
 * persisted (PATCH returns 501), so no
 * preferences form is offered here either.
 */
export default function MerchantNotificationsPage() {
  const [items, setItems] = useState<NotificationItem[] | null>(null);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [unreadOnly, setUnreadOnly] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const services = createServices(createBrowserApiClient());
      const [list, count] = await Promise.all([
        services.notifications.list({ unread_only: unreadOnly || undefined, page_size: 50 }),
        services.notifications.unreadCount(),
      ]);
      setItems(list.items);
      setUnread(count.unread_count);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not load notifications.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unreadOnly]);

  async function markRead(id: string) {
    try {
      await createServices(createBrowserApiClient()).notifications.markRead(id);
      setItems((current) =>
        current ? current.map((item) => (item.id === id ? { ...item, is_read: true } : item)) : current,
      );
      setUnread((value) => Math.max(0, value - 1));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not mark that notification as read.");
    }
  }

  async function markAllRead() {
    try {
      await createServices(createBrowserApiClient()).notifications.markAllRead();
      setItems((current) => (current ? current.map((item) => ({ ...item, is_read: true })) : current));
      setUnread(0);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not mark all as read.");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Notifications</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {unread > 0 ? `${unread} unread` : "All caught up"} · Only notifications that actually
            exist are shown. Notification generation is not active yet, so do not expect automatic
            alerts until the platform enables delivery.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setUnreadOnly((value) => !value)}>
            {unreadOnly ? "Show all" : "Unread only"}
          </Button>
          <Button variant="outline" onClick={markAllRead} disabled={unread === 0}>
            Mark all as read
          </Button>
        </div>
      </div>
      {error ? <Alert variant="error">{error}</Alert> : null}
      {loading ? (
        <LoadingState label="Loading notifications" />
      ) : items && items.length === 0 ? (
        <EmptyState
          title="No notifications yet"
          description="When SaveBite records an update for your account, it will show up here."
        />
      ) : (
        <div className="flex flex-col gap-3">
          {items?.map((item) => (
            <Card key={item.id} className={item.is_read ? "" : "border-primary/50"}>
              <CardContent className="flex flex-col gap-1 p-5">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="font-semibold">{item.title}</p>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
                <p className="text-sm text-muted-foreground">{item.body}</p>
                {!item.is_read ? (
                  <div className="mt-2">
                    <Button variant="outline" size="sm" onClick={() => void markRead(item.id)}>
                      Mark as read
                    </Button>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
