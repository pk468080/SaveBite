import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ApiClient } from "@savebite/api-client";
import { NotificationPreferencesSection } from "@/components/shared/notification-preferences";

const getMock = vi.hoisted(() => vi.fn());
const patchMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/browser", () => ({
  createBrowserApiClient: () =>
    ({ get: getMock, patch: patchMock }) as unknown as ApiClient,
}));

const CATEGORIES = [
  {
    key: "pickup_reminders",
    label: "Pickup reminders",
    description: "A reminder before your pickup window starts.",
  },
  {
    key: "payment_updates",
    label: "Payment updates",
    description: "Payment results for your orders.",
  },
];

const STORED = {
  preferences: { pickup_reminders: true, payment_updates: true },
  mandatory_categories: ["payment_updates"],
  persisted: true,
};

afterEach(() => cleanup());

beforeEach(() => {
  getMock.mockReset();
  patchMock.mockReset();
  getMock.mockResolvedValue(STORED);
  patchMock.mockResolvedValue({
    preferences: { pickup_reminders: false, payment_updates: true },
    mandatory_categories: ["payment_updates"],
    persisted: true,
  });
});

describe("NotificationPreferencesSection", () => {
  it("loads values from the API, locks mandatory categories, and never saves on mount", async () => {
    render(<NotificationPreferencesSection categories={CATEGORIES} />);
    await screen.findByText("Pickup reminders");
    expect(getMock).toHaveBeenCalledWith("/v1/notifications/preferences");
    expect(patchMock).not.toHaveBeenCalled();
    // Mandatory categories render locked on.
    expect(
      screen.getByRole("checkbox", { name: "Payment updates" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("checkbox", { name: "Pickup reminders" }),
    ).not.toBeDisabled();
  });

  it("saves only after Save is clicked and confirms only after the API resolves", async () => {
    render(<NotificationPreferencesSection categories={CATEGORIES} />);
    await screen.findByText("Pickup reminders");
    fireEvent.click(screen.getByRole("checkbox", { name: "Pickup reminders" }));
    expect(screen.queryByText("Preferences saved.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await screen.findByText("Preferences saved.");
    expect(patchMock).toHaveBeenCalledTimes(1);
    expect(patchMock.mock.calls[0]?.[0]).toBe(
      "/v1/notifications/preferences",
    );
    expect(patchMock.mock.calls[0]?.[1]).toEqual({
      preferences: { pickup_reminders: false, payment_updates: true },
    });
  });

  it("shows an error and no saved confirmation when saving fails", async () => {
    patchMock.mockRejectedValue(new Error("Network down"));
    render(<NotificationPreferencesSection categories={CATEGORIES} />);
    await screen.findByText("Pickup reminders");
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await screen.findByText("Could not save notification preferences.");
    expect(screen.queryByText("Preferences saved.")).toBeNull();
  });

  it("shows a retry option when loading fails", async () => {
    getMock.mockRejectedValueOnce(new Error("Network down"));
    render(<NotificationPreferencesSection categories={CATEGORIES} />);
    await screen.findByText("Could not load notification preferences.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Pickup reminders");
    expect(getMock).toHaveBeenCalledTimes(2);
  });
});
