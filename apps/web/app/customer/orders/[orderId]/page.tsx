import { ApiError, createServices } from "@savebite/api-client";
import Image from "next/image";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, EmptyState } from "@/components/ui/states";
import { createServerApiClient } from "@/lib/api/server";
import { formatINR, formatPickupWindow, listingImageUrl, listingTypeLabel } from "@/lib/marketplace";
import { formatDateTime, orderStatusLabel, paymentStatusLabel } from "@/lib/order-labels";

/**
 * Customer order detail (W3, server-rendered). Item
 * prices are the order-time SNAPSHOTS from the backend,
 * never live listing prices. The timeline shows only
 * real recorded order-status events. Payment status and
 * fulfilment status are kept visually separate.
 * Another customer's order returns the same 404 as a
 * missing one, and this page shows the same safe
 * not-found experience for both — the backend never
 * reveals which case it was.
 */
export default async function OrderDetailPage({
  params,
}: {
  params: Promise<{ orderId: string }>;
}) {
  const { orderId } = await params;
  let order = null;
  let failed = false;
  try {
    const client = await createServerApiClient();
    order = await createServices(client).orders.getOrder(orderId);
  } catch (caught) {
    if (caught instanceof ApiError && caught.status === 404) {
      order = null;
    } else {
      failed = true;
    }
  }

  if (failed) {
    return <Alert variant="error">Could not load this order. Please try again.</Alert>;
  }

  if (!order) {
    return (
      <EmptyState
        title="Order not found"
        description="This order does not exist or does not belong to your account."
        >
        <Button asChild><Link href="/customer/orders">Back to order history</Link></Button>
      </EmptyState>
    );
  }

  const store = order.store;
  const address = [
    store.address_line_1,
    store.address_line_2,
    store.locality,
    `${store.city}, ${store.state} ${store.pincode}`,
  ]
    .filter(Boolean)
    .join(", ");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Order {order.order_number}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Placed {formatDateTime(order.created_at)} · {orderStatusLabel(order.status)} · Payment:{" "}
          {paymentStatusLabel(order.payment.status)}
        </p>
      </div>

      {order.status === "pending_payment" ? (
        <Alert variant="info">
          This order is still awaiting payment.{" "}
          <Link href={`/customer/checkout?orderId=${order.id}`} className="font-medium underline underline-offset-4">
            Pay now
          </Link>{" "}
          while the reservation is open.
        </Alert>
      ) : null}
      {order.payment.status === "reconciliation_required" ? (
        <Alert variant="info">
          This payment needs verification. It is not shown as a successful purchase, and no refund
          has been promised. Check back shortly for the backend-confirmed status.
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Items</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col divide-y p-0">
          {order.items.map((item) => (
            <div key={item.listing_id} className="flex gap-4 p-4">
              <div className="relative h-16 w-16 shrink-0 overflow-hidden rounded-md bg-muted">
                {item.image_path ? (
                  <Image src={listingImageUrl(item.image_path)} alt={item.title} fill className="object-cover" />
                ) : null}
              </div>
              <div className="flex flex-1 flex-col gap-1">
                <p className="font-medium">{item.title}</p>
                <p className="text-sm text-muted-foreground">
                  {listingTypeLabel(item.listing_type)} · {formatINR(item.unit_price, order.currency)} each
                </p>
                <p className="mt-auto flex justify-between text-sm">
                  <span className="text-muted-foreground">Quantity {item.quantity}</span>
                  <span className="font-medium">{formatINR(item.line_total, order.currency)}</span>
                </p>
              </div>
            </div>
          ))}
          <div className="flex flex-col gap-1 p-4 text-sm">
            <p className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>{formatINR(order.subtotal_amount, order.currency)}</span>
            </p>
            {Number(order.discount_amount) !== 0 ? (
              <p className="flex justify-between">
                <span className="text-muted-foreground">Discount</span>
                <span>−{formatINR(order.discount_amount, order.currency)}</span>
              </p>
            ) : null}
            {Number(order.platform_fee_amount) !== 0 ? (
              <p className="flex justify-between">
                <span className="text-muted-foreground">Platform fee</span>
                <span>{formatINR(order.platform_fee_amount, order.currency)}</span>
              </p>
            ) : null}
            {Number(order.tax_amount) !== 0 ? (
              <p className="flex justify-between">
                <span className="text-muted-foreground">Tax</span>
                <span>{formatINR(order.tax_amount, order.currency)}</span>
              </p>
            ) : null}
            <p className="flex justify-between border-t pt-2 font-semibold">
              <span>Total</span>
              <span>{formatINR(order.total_amount, order.currency)}</span>
            </p>
            <p className="flex justify-between text-muted-foreground">
              <span>Amount confirmed paid</span>
              <span>{formatINR(order.payment.amount_paid, order.currency)}</span>
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Pickup</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          <p className="font-medium">{store.name}</p>
          <p className="text-muted-foreground">{address}</p>
          {store.contact_phone ? (
            <p className="text-muted-foreground">Store phone: {store.contact_phone}</p>
          ) : null}
          <p>
            Pickup window:{" "}
            <span className="font-medium">
              {formatPickupWindow(order.pickup_starts_at, order.pickup_ends_at, "Asia/Kolkata")}
            </span>
          </p>
          {store.pickup_instructions ? (
            <p className="text-muted-foreground">Instructions: {store.pickup_instructions}</p>
          ) : null}
          <p className="text-muted-foreground">
            Collect your food at the store — there is no delivery. The pickup code screen arrives
            in a later milestone; nothing on this page is a pickup code.
          </p>
          {order.reservation_expires_at && order.status === "pending_payment" ? (
            <p className="text-muted-foreground">
              Reservation expires {formatDateTime(order.reservation_expires_at)}.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2 text-sm">
          {order.timeline.length === 0 ? (
            <p className="text-muted-foreground">
              No recorded events yet — the status above is the current state.
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {order.timeline.map((event, index) => (
                <li key={`${event.occurred_at}-${index}`} className="flex justify-between gap-4">
                  <span>
                    {event.label} <span className="text-muted-foreground">({event.actor_type})</span>
                  </span>
                  <span className="text-muted-foreground">{formatDateTime(event.occurred_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap gap-2">
        <Button asChild variant="outline">
          <Link href={`/customer/orders/${order.id}/payment`}>Payment status</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/customer/orders">Back to order history</Link>
        </Button>
      </div>
    </div>
  );
}
