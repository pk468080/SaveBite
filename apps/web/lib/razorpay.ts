/**
 * Razorpay Checkout web SDK loader (W3).
 *
 * Only the OFFICIAL script is ever loaded, and only
 * once per page lifetime: concurrent callers share one
 * promise, and a failed load clears the promise so a
 * later retry can try again. The public key_id comes
 * from the backend checkout response — no secret, no
 * webhook secret, and no provider payload ever enters
 * browser code.
 *
 * A Checkout success callback is NOT payment success:
 * the caller must submit the callback fields to
 * POST /v1/payments/verify and then re-read the order
 * detail before showing any success state.
 */

export const RAZORPAY_SCRIPT_URL = "https://checkout.razorpay.com/v1/checkout.js";

export interface RazorpayCheckoutResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface RazorpayOptions {
  key: string;
  order_id: string;
  amount: number;
  currency: string;
  name?: string;
  description?: string;
  prefill?: { email?: string };
  theme?: { color?: string };
  handler: (response: RazorpayCheckoutResponse) => void;
  modal?: { ondismiss?: () => void };
}

export interface RazorpayInstance {
  open: () => void;
  close: () => void;
}

declare global {
  interface Window {
    Razorpay?: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

let loadPromise: Promise<void> | null = null;

export function loadRazorpayScript(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Razorpay Checkout needs a browser window."));
  }
  if (window.Razorpay) return Promise.resolve();
  if (loadPromise) return loadPromise;
  loadPromise = new Promise<void>((resolve, reject) => {
    const existing = document.querySelector(`script[src="${RAZORPAY_SCRIPT_URL}"]`);
    if (existing) {
      // Another part of the page already injected it;
      // wait for the global instead of adding a copy.
      const check = () => {
        if (window.Razorpay) resolve();
        else setTimeout(check, 50);
      };
      check();
      return;
    }
    const script = document.createElement("script");
    script.src = RAZORPAY_SCRIPT_URL;
    script.async = true;
    script.onload = () => {
      if (window.Razorpay) resolve();
      else {
        loadPromise = null;
        reject(new Error("Razorpay Checkout failed to initialise."));
      }
    };
    script.onerror = () => {
      loadPromise = null;
      reject(new Error("Could not load the payment window. Check your connection and try again."));
    };
    document.body.appendChild(script);
  });
  return loadPromise;
}

export function openRazorpayCheckout(options: RazorpayOptions): RazorpayInstance {
  if (!window.Razorpay) {
    throw new Error("Razorpay Checkout is not loaded yet.");
  }
  const instance = new window.Razorpay(options);
  instance.open();
  return instance;
}
