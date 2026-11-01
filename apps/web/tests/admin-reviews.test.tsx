import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@savebite/api-client";
import AdminReviewsPage from "@/app/admin/reviews/page";

const getMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/browser", () => ({
  createBrowserApiClient: () => ({ get: getMock }) as unknown as ApiClient,
}));

afterEach(() => cleanup());

beforeEach(() => {
  getMock.mockReset();
  getMock.mockResolvedValue({
    items: [
      {
        id: "r-1",
        store_id: "s-1",
        store_name: "Sharma Foods",
        rating: 5,
        comment: "Great thali.",
        moderation_status: "visible",
        created_at: "2026-10-31T19:00:00+00:00",
      },
    ],
    total: 1,
    page: 1,
    page_size: 20,
  });
});

/**
 * W6 reviews page: read-only by backend
 * design. No moderation action may appear,
 * because no moderation endpoint exists.
 */
describe("AdminReviewsPage", () => {
  it("renders the visible review and offers no moderation actions", async () => {
    render(<AdminReviewsPage />);
    await screen.findByText("Great thali.");
    expect(screen.queryByRole("button", { name: /hide/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /restore/i })).toBeNull();
    expect(
      screen.getByText(/The backend has no review moderation endpoint/),
    ).toBeTruthy();
  });
});
