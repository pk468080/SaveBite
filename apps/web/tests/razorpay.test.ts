import { describe, expect, it, vi } from "vitest";
import { loadRazorpayScript, RAZORPAY_SCRIPT_URL } from "@/lib/razorpay";

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
