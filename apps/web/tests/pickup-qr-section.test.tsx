import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@savebite/api-client";
import { PickupQrSection } from "@/components/customer/pickup-qr-section";

const TOKEN = "b".repeat(64);
const postMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/browser", () => ({
  createBrowserApiClient: () => ({ post: postMock }) as unknown as ApiClient,
}));

const ISSUED = {
  order_id: "order-1",
  order_number: "SB-1",
  pickup_token: TOKEN,
  qr_payload: `SB1:${TOKEN}`,
  expires_at: "2026-10-31T21:30:00+00:00",
  pickup_starts_at: "2026-10-31T18:00:00+00:00",
  pickup_ends_at: "2026-10-31T21:00:00+00:00",
  store_name: "Sharma Foods",
  pickup_instructions: "Ask at the counter.",
};

function renderSection(props: Partial<React.ComponentProps<typeof PickupQrSection>> = {}) {
  return render(
    <PickupQrSection
      orderId="order-1"
      orderNumber="SB-1"
      orderStatus="confirmed"
      paymentStatus="captured"
      storeName="Sharma Foods"
      storeAddress="Shop 1, Dwarka Sector 7, New Delhi"
      pickupStartsAt="2026-10-31T18:00:00+00:00"
      pickupEndsAt="2026-10-31T21:00:00+00:00"
      pickupInstructions="Ask at the counter."
      {...props}
    />,
  );
}

afterEach(() => cleanup());

beforeEach(() => {
  postMock.mockReset();
  postMock.mockResolvedValue(ISSUED);
});

describe("PickupQrSection", () => {
  it("requests a token only on click, renders the QR, and never shows the raw token as text", async () => {
    const { container } = renderSection();
    expect(postMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Show this QR code to the merchant/);
    expect(postMock).toHaveBeenCalledTimes(1);
    expect(postMock.mock.calls[0]?.[0]).toBe("/v1/orders/order-1/pickup-token");
    expect(container.querySelector("svg")).not.toBeNull();
    // The QR carries the token; no visible text may contain it.
    expect(document.body.textContent ?? "").not.toContain(TOKEN);
    expect(document.body.textContent ?? "").not.toContain("SB1:");
  });

  it("ignores duplicate clicks while issuing", async () => {
    renderSection();
    const button = screen.getByRole("button", { name: "Show Pickup QR" });
    fireEvent.click(button);
    fireEvent.click(button);
    await screen.findByText(/Show this QR code to the merchant/);
    expect(postMock).toHaveBeenCalledTimes(1);
  });

  it("shows no button and a plain reason for an ineligible order", () => {
    renderSection({ orderStatus: "pending_payment", paymentStatus: "created" });
    expect(screen.queryByRole("button", { name: "Show Pickup QR" })).toBeNull();
    expect(screen.getByText(/Pay for this order first/)).toBeVisible();
    expect(postMock).not.toHaveBeenCalled();
  });

  it("shows a useful error on failed issuance and allows a deliberate retry", async () => {
    postMock.mockRejectedValueOnce(new Error("Pickup token could not be issued"));
    renderSection();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Pickup token could not be issued/);
    expect(screen.getByRole("button", { name: "Show Pickup QR" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Show this QR code to the merchant/);
    expect(postMock).toHaveBeenCalledTimes(2);
  });

  it("hiding the QR clears it, and it can be requested again", async () => {
    const { container } = renderSection();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Show this QR code to the merchant/);
    fireEvent.click(screen.getByRole("button", { name: "Hide QR code" }));
    expect(container.querySelector("svg")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Show this QR code to the merchant/);
    expect(postMock).toHaveBeenCalledTimes(2);
  });

  it("communicates that a fresh code invalidates the current unused code", async () => {
    renderSection();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Show this QR code to the merchant/);
    expect(screen.getByText(/invalidates the current unused code/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Request a fresh code" }));
    await screen.findByText(/Show this QR code to the merchant/);
    expect(postMock).toHaveBeenCalledTimes(2);
  });

  it("clears the token when the order context changes", async () => {
    const { container, rerender } = renderSection();
    fireEvent.click(screen.getByRole("button", { name: "Show Pickup QR" }));
    await screen.findByText(/Show this QR code to the merchant/);
    expect(container.querySelector("svg")).not.toBeNull();
    rerender(
      <PickupQrSection
        orderId="order-2"
        orderNumber="SB-2"
        orderStatus="confirmed"
        paymentStatus="captured"
        storeName="Sharma Foods"
        storeAddress="Shop 1, Dwarka Sector 7, New Delhi"
        pickupStartsAt="2026-10-31T18:00:00+00:00"
        pickupEndsAt="2026-10-31T21:00:00+00:00"
      />,
    );
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByRole("button", { name: "Show Pickup QR" })).toBeVisible();
  });
});
