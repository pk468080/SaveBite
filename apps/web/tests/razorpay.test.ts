import { describe, expect, it, vi } from "vitest";
import {
  loadRazorpayScript,
  openRazorpayCheckout,
  RAZORPAY_SCRIPT_URL,
} from "@/lib/razorpay";

describe("Razorpay loader", () => {
  it("resolves immediately when the SDK global already exists and injects nothing", async () => {
    const win = window as unknown as { Razorpay?: unknown };
    const previous = win.Razorpay;
    win.Razorpay = class Mock {};
    try {
      await expect(loadRazorpayScript()).resolves.toBeUndefined();
      expect(document.querySelector(`script[src="${RAZORPAY_SCRIPT_URL}"]`)).toBeNull();
    } finally {
      if (previous === undefined) delete win.Razorpay;
      else win.Razorpay = previous;
    }
  });

  it("loads the official script URL exactly once for concurrent callers", async () => {
    const win = window as unknown as { Razorpay?: unknown };
    const previous = win.Razorpay;
    delete win.Razorpay;
    const appendSpy = vi.spyOn(document.body, "appendChild");
    try {
      const first = loadRazorpayScript();
      const second = loadRazorpayScript();
      const scripts = document.querySelectorAll(`script[src="${RAZORPAY_SCRIPT_URL}"]`);
      expect(scripts).toHaveLength(1);
      // Simulate the script finishing: the global appears.
      win.Razorpay = class Mock {};
      scripts[0]!.dispatchEvent(new Event("load"));
      await expect(first).resolves.toBeUndefined();
      await expect(second).resolves.toBeUndefined();
      expect(appendSpy).toHaveBeenCalledTimes(1);
    } finally {
      appendSpy.mockRestore();
      document.querySelectorAll(`script[src="${RAZORPAY_SCRIPT_URL}"]`).forEach((el) => el.remove());
      if (previous === undefined) delete win.Razorpay;
      else win.Razorpay = previous;
    }
  });
});

describe("Razorpay checkout opening (B1 retry)", () => {
  it("opens Checkout with exactly the order id it is given, including a reused one", () => {
    const win = window as unknown as { Razorpay?: unknown };
    const previous = win.Razorpay;
    const seen: Array<Record<string, unknown>> = [];
    let opened = false;
    class MockRazorpay {
      constructor(options: Record<string, unknown>) {
        seen.push(options);
      }
      open() {
        opened = true;
      }
      close() {}
    }
    win.Razorpay = MockRazorpay;
    try {
      // A reused order id from a backend retry response must
      // pass through untouched — the lib never substitutes
      // its own id or reuses a stale one.
      const instance = openRazorpayCheckout({
        key: "rzp_test_public",
        order_id: "order_reused_1",
        amount: 19800,
        currency: "INR",
        handler: () => {},
      });
      expect(instance).toBeInstanceOf(MockRazorpay);
      expect(opened).toBe(true);
      expect(seen).toHaveLength(1);
      expect(seen[0]!["order_id"]).toBe("order_reused_1");
      expect(seen[0]!["key"]).toBe("rzp_test_public");
      expect(seen[0]!["amount"]).toBe(19800);
    } finally {
      if (previous === undefined) delete win.Razorpay;
      else win.Razorpay = previous;
    }
  });

  it("throws when the SDK global is absent", () => {
    const win = window as unknown as { Razorpay?: unknown };
    const previous = win.Razorpay;
    delete win.Razorpay;
    try {
      expect(() =>
        openRazorpayCheckout({
          key: "rzp_test_public",
          order_id: "order_1",
          amount: 19800,
          currency: "INR",
          handler: () => {},
        }),
      ).toThrow();
    } finally {
      if (previous === undefined) delete win.Razorpay;
      else win.Razorpay = previous;
    }
  });
});
