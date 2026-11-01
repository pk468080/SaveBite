import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@savebite/api-client";
import { MerchantReviewPanel } from "@/components/admin/merchant-review-panel";
import { StoreReviewPanel } from "@/components/admin/store-review-panel";

const postMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/browser", () => ({
  createBrowserApiClient: () => ({ post: postMock }) as unknown as ApiClient,
}));

afterEach(() => cleanup());

beforeEach(() => {
  postMock.mockReset();
  postMock.mockResolvedValue({ merchant_id: "m-1", status: "approved", verification_status: "verified" });
});

/**
 * W6 review panels: confirm before acting,
 * one API call per decision, failure leaves
 * the shown status untouched, success asks the
 * parent to re-read from the backend.
 */
describe("MerchantReviewPanel", () => {
  it("asks for confirmation first, then calls the review API once and refreshes", async () => {
    const onReviewed = vi.fn();
    render(<MerchantReviewPanel merchantId="m-1" onReviewed={onReviewed} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    // No API call before confirmation.
    expect(postMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm approve" }));
    await screen.findByText(/Application approved/);
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock.mock.calls[0]?.[0]).toBe("/v1/admin/merchants/m-1/review");
    expect(postMock.mock.calls[0]?.[1]).toEqual({ action: "approve", review_notes: undefined });
    expect(onReviewed).toHaveBeenCalledTimes(1);
  });

  it("blocks duplicate submissions while a decision is in flight", async () => {
    let resolvePost: (value: unknown) => void = () => {};
    postMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolvePost = resolve;
        }),
    );
    render(<MerchantReviewPanel merchantId="m-1" onReviewed={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reject" }));
    fireEvent.click(screen.getByRole("button", { name: "Saving…" }));
    expect(postMock).toHaveBeenCalledTimes(1);
    resolvePost({ merchant_id: "m-1", status: "rejected", verification_status: "rejected" });
    await screen.findByText(/Application rejected/);
    expect(postMock).toHaveBeenCalledTimes(1);
  });

  it("shows the backend error and does not refresh on failure", async () => {
    const onReviewed = vi.fn();
    postMock.mockRejectedValueOnce(new Error("Approval needs a verified FSSAI document."));
    render(<MerchantReviewPanel merchantId="m-1" onReviewed={onReviewed} />);
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approve" }));
    await screen.findByText(/Approval needs a verified FSSAI document/);
    expect(onReviewed).not.toHaveBeenCalled();
  });
});

describe("StoreReviewPanel", () => {
  it("deactivates only after confirmation and reports the backend result", async () => {
    postMock.mockResolvedValue({ store_id: "s-1", activated: false });
    const onReviewed = vi.fn();
    render(<StoreReviewPanel storeId="s-1" currentActive onReviewed={onReviewed} />);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    expect(postMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm deactivation" }));
    await screen.findByText(/Store deactivated/);
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock.mock.calls[0]?.[0]).toBe("/v1/admin/stores/s-1/review");
    expect(postMock.mock.calls[0]?.[1]).toEqual({ activate: false, reason: undefined });
    expect(onReviewed).toHaveBeenCalledTimes(1);
  });

  it("does not offer activation for an already-active store", () => {
    render(<StoreReviewPanel storeId="s-1" currentActive onReviewed={() => {}} />);
    expect(screen.getByRole("button", { name: "Activate" })).toBeDisabled();
  });
});
