import { describe, expect, it, vi } from "vitest";
import { ApiClient, createServices } from "../src";

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function clientWith(fetchImpl: unknown) {
  return createServices(
    new ApiClient({ baseUrl: "http://localhost:8000", fetchImpl: fetchImpl as unknown as typeof fetch }),
  );
}

/**
 * W6 admin service contracts, pinned to the
 * verified FastAPI admin routes (M11). The
 * backend is authoritative; these tests pin
 * the frontend to its real contract — including
 * the absence of any review moderation or
 * role-management endpoint (there is none to
 * pin, and none is invented).
 */
describe("W6 admin services", () => {
  it("loads the dashboard from the M11 endpoint", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { merchants_total: 0 }));
    const services = clientWith(fetchImpl);
    await services.admin.getDashboard();
    const [url] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/v1/admin/dashboard");
  });

  it("lists merchants with server-side filters and pagination", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { items: [], total: 0, page: 1, page_size: 20 }));
    const services = clientWith(fetchImpl);
    await services.admin.listMerchants({
      status: "pending_review",
      verification_status: "pending",
      search: "Sharma",
      page: 2,
      page_size: 20,
    });
    const [url] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/v1/admin/merchants?");
    expect(url).toContain("status=pending_review");
    expect(url).toContain("verification_status=pending");
    expect(url).toContain("search=Sharma");
    expect(url).toContain("page=2");
  });

  it("reads a merchant detail and reviews it with exactly the M11 body", async () => {
    const calls: Array<[string, RequestInit]> = [];
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      return jsonResponse(200, { merchant_id: "m-1", status: "approved", verification_status: "verified" });
    });
    const services = clientWith(fetchImpl);
    await services.admin.getMerchantDetail("m-1");
    await services.admin.reviewMerchant("m-1", { action: "approve", review_notes: "FSSAI verified" });
    expect(calls[0]?.[0]).toBe("http://localhost:8000/v1/admin/merchants/m-1");
    expect(calls[1]?.[0]).toBe("http://localhost:8000/v1/admin/merchants/m-1/review");
    expect(JSON.parse(String(calls[1]?.[1].body))).toEqual({
      action: "approve",
      review_notes: "FSSAI verified",
    });
  });

  it("reads a store detail and reviews it with the activate boolean", async () => {
    const calls: Array<[string, RequestInit]> = [];
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      return jsonResponse(200, { store_id: "s-1", activated: false });
    });
    const services = clientWith(fetchImpl);
    await services.admin.getStoreDetail("s-1");
    await services.admin.reviewStore("s-1", { activate: false, reason: "Hours missing" });
    expect(calls[0]?.[0]).toBe("http://localhost:8000/v1/admin/stores/s-1");
    expect(calls[1]?.[0]).toBe("http://localhost:8000/v1/admin/stores/s-1/review");
    expect(JSON.parse(String(calls[1]?.[1].body))).toEqual({
      activate: false,
      reason: "Hours missing",
    });
  });

  it("lists orders, payments, refunds, reviews and activity from their M11 endpoints", async () => {
    const urls: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      urls.push(url);
      return jsonResponse(200, { items: [], total: 0, page: 1, page_size: 20 });
    });
    const services = clientWith(fetchImpl);
    await services.admin.listOrders({ order_number: "SB-1" });
    await services.admin.getOrderDetail("o-1");
    await services.admin.listPayments({ payment_status: "failed" });
    await services.admin.listRefunds({});
    await services.admin.listReviews({ rating: 5, moderation_status: "visible" });
    await services.admin.listActivity({ order_number: "SB-1" });
    expect(urls[0]).toContain("/v1/admin/orders?order_number=SB-1");
    expect(urls[1]).toBe("http://localhost:8000/v1/admin/orders/o-1");
    expect(urls[2]).toContain("/v1/admin/payments?payment_status=failed");
    expect(urls[3]).toContain("/v1/admin/refunds");
    expect(urls[4]).toContain("/v1/admin/reviews?");
    expect(urls[4]).toContain("rating=5");
    expect(urls[5]).toContain("/v1/admin/activity?order_number=SB-1");
  });
});
