import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, type ApiClient } from "@savebite/api-client";
import AdminOverviewPage from "@/app/admin/page";

const getMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/browser", () => ({
  createBrowserApiClient: () => ({ get: getMock }) as unknown as ApiClient,
}));

const DASHBOARD = {
  merchants_total: 3,
  merchants_approved: 1,
  merchants_pending_review: 2,
  stores_total: 2,
  stores_active: 1,
  stores_draft: 1,
  stores_inactive: 0,
  stores_suspended: 0,
  listings_total: 5,
  listings_published: 3,
  listings_draft: 1,
  listings_paused: 1,
  listings_sold_out: 0,
  listings_expired: 0,
  orders_total: 4,
  orders_pending_payment: 1,
  orders_confirmed: 1,
  orders_ready_for_pickup: 1,
  orders_collected: 1,
  orders_cancelled_or_expired: 0,
  captured_payment_count: 2,
  captured_order_value: "450.00",
  failed_payment_count: 0,
  pending_payment_count: 1,
  reconciliation_required_count: 0,
  refund_pending_count: 0,
  visible_reviews_total: 1,
  average_visible_rating: 5,
  recent_orders: [
    {
      id: "o-1",
      order_number: "SB-1001",
      store_id: "s-1",
      store_name: "Sharma Foods",
      merchant_name: "Sharma Foods",
      status: "collected",
      payment_status: "captured",
      total_amount: "195.00",
      currency: "INR",
      created_at: "2026-10-31T18:00:00+00:00",
    },
  ],
};

afterEach(() => cleanup());

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue(DASHBOARD);
});

/**
 * W6 dashboard: real backend fields only,
 * captured value never labelled as earnings
 * or revenue, refresh re-reads, and a 403
 * shows access denied without retrying.
 */
describe("AdminOverviewPage", () => {
  it("renders backend counts and labels captured value honestly", async () => {
    render(<AdminOverviewPage />);
    await screen.findByText("Platform overview");
    expect(screen.getByText("Captured order value")).toBeTruthy();
    expect(
      screen.getByText(/It is not merchant earnings, payouts, revenue, or platform profit/),
    ).toBeTruthy();
    expect(screen.getByText(/Order SB-1001/)).toBeTruthy();
    expect(getMock).toHaveBeenCalledWith("/v1/admin/dashboard");
  });

  it("refresh re-reads the backend", async () => {
    render(<AdminOverviewPage />);
    await screen.findByText("Platform overview");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText("Platform overview");
    expect(getMock).toHaveBeenCalledTimes(2);
  });

  it("shows access denied on a 403 and does not retry", async () => {
    getMock.mockRejectedValueOnce(
      new ApiError(403, { code: "FORBIDDEN", message: "Forbidden" }),
    );
    render(<AdminOverviewPage />);
    await screen.findByText("Access denied");
    expect(getMock).toHaveBeenCalledTimes(1);
  });

  it("shows an error, not an empty dashboard, on a backend failure", async () => {
    getMock.mockRejectedValueOnce(new Error("Backend unreachable"));
    render(<AdminOverviewPage />);
    await screen.findByText(/Backend unreachable/);
  });
});
