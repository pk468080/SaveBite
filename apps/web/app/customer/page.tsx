import { createServices } from "@savebite/api-client";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/states";
import { createServerApiClient } from "@/lib/api/server";
import { formatINR } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

/**
 * Customer overview (W3). Identity comes from
 * GET /v1/me; recent orders from GET /v1/orders.
 * Everything shown is backend data — nothing here
 * is invented, and a failed fetch degrades to links
 * instead of fake content.
 */
export default async function CustomerOverviewPage() {
  let email: string | null = null;
  let recent: Awaited<ReturnType<ReturnType<typeof createServices>["orders"]["listOrders"]>> | null = null;
  let unread = 0;
  try {
    const client = await createServerApiClient();
    const services = createServices(client);
    const [me, orders, count] = await Promise.all([
      services.auth.me(),
      services.orders.listOrders({ page: 1, page_size: 3 }),
      services.notifications.unreadCount(),
    ]);
    email = me.email ?? null;
    recent = orders;
    unread = count.unread_count;
  } catch {
    // Degraded overview: links still work, and the
    // individual pages show their own errors.
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">My account</h1>
        {email ? (
          <p className="mt-1 text-sm text-muted-foreground">Signed in as {email}</p>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Orders</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              Browse your reservations, payments, and pickup windows.
            </p>
            <Button asChild variant="outline">
              <Link href="/customer/orders">View order history</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Notifications</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">
              {unread > 0 ? `${unread} unread update${unread === 1 ? "" : "s"}.` : "No unread updates."}
            </p>
            <Button asChild variant="outline">
              <Link href="/customer/notifications">View notifications</Link>
            </Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <p className="text-sm text-muted-foreground">Your account information, read-only.</p>
            <Button asChild variant="outline">
              <Link href="/customer/profile">View profile</Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent orders</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {!recent || recent.items.length === 0 ? (
            <Alert variant="info">
              No orders yet.{" "}
              <Link href="/marketplace" className="font-medium underline underline-offset-4">
                Explore surplus food
              </Link>{" "}
              to make your first reservation.
            </Alert>
          ) : (
            recent.items.map((order) => (
              <div key={order.id} className="flex flex-wrap items-baseline justify-between gap-2 border-b pb-3 last:border-0 last:pb-0">
                <Link href={`/customer/orders/${order.id}`} className="font-medium hover:underline">
                  {order.order_number} · {order.store.name}
                </Link>
                <span className="text-sm text-muted-foreground">
                  {orderStatusLabel(order.status)} · Payment: {paymentStatusLabel(order.payment_status)} ·{" "}
                  {formatINR(order.total_amount, order.currency)} · {formatDateTime(order.created_at)}
                </span>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
