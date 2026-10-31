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
 * W4 merchant service contracts: application,
 * store, hours, listing, transition, inventory,
 * image, dashboard and pickup-verify request
 * shapes, pinned to the verified FastAPI routes
 * (M3, M4, M7, M8, M10). The backend is
 * authoritative; these tests pin the frontend
 * to its real contract.
 */
describe("W4 merchant services", () => {
  it("submits the application with exactly the M3 fields", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(201, { id: "merchant-1" }));
    const services = clientWith(fetchImpl);
    await services.merchants.submitApplication({
      legal_name: "Sharma Foods Pvt Ltd",
      display_name: "Sharma Foods",
      business_type: "bakery",
      business_email: null,
      business_phone: null,
    });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/v1/merchants/applications");
    expect(JSON.parse(String(init.body))).toEqual({
      legal_name: "Sharma Foods Pvt Ltd",
      display_name: "Sharma Foods",
      business_type: "bakery",
      business_email: null,
      business_phone: null,
    });
  });

  it("creates a store under the merchant and updates hours with the weekday payload", async () => {
    const calls: Array<[string, RequestInit]> = [];
    const fetchImpl = vi.fn(async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      return jsonResponse(201, { id: "store-1" });
    });
    const services = clientWith(fetchImpl);
    await services.merchants.createStore("merchant-1", {
      name: "Sharma Foods",
      slug: "sharma-foods",
      address_line_1: "Shop 1",
      city: "New Delhi",
      state: "Delhi",
      pincode: "110075",
    });
    await services.merchants.updateStoreHours("store-1", [
      { weekday: 0, is_closed: false, opens_at: "09:00", closes_at: "21:00" },
      { weekday: 6, is_closed: true, opens_at: null, closes_at: null },
    ]);
    expect(calls[0]![0]).toBe("http://localhost:8000/v1/merchants/merchant-1/stores");
    expect(calls[1]![0]).toBe("http://localhost:8000/v1/stores/store-1/hours");
    expect(JSON.parse(String(calls[1]![1].body))).toEqual({
      hours: [
        { weekday: 0, is_closed: false, opens_at: "09:00", closes_at: "21:00" },
        { weekday: 6, is_closed: true, opens_at: null, closes_at: null },
      ],
    });
  });

  it("uses the dedicated transition endpoints and the inventory read endpoint", async () => {
    const urls: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      urls.push(url);
      return jsonResponse(200, { id: "listing-1" });
    });
    const services = clientWith(fetchImpl);
    await services.listings.publish("listing-1");
    await services.listings.pause("listing-1");
    await services.listings.resume("listing-1");
    await services.listings.cancel("listing-1");
    await services.listings.getInventory("listing-1");
    expect(urls).toEqual([
      "http://localhost:8000/v1/listings/listing-1/publish",
      "http://localhost:8000/v1/listings/listing-1/pause",
      "http://localhost:8000/v1/listings/listing-1/resume",
      "http://localhost:8000/v1/listings/listing-1/cancel",
      "http://localhost:8000/v1/listings/listing-1/inventory",
    ]);
  });

  it("registers images with a storage path only, never a URL", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(201, { id: "image-1" }));
    const services = clientWith(fetchImpl);
    await services.listings.addImage("listing-1", {
      storage_path: "listing-1/photo.jpg",
      alt_text: "Evening bag",
      display_order: 0,
    });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/v1/listings/listing-1/images");
    expect(JSON.parse(String(init.body)).storage_path).toBe("listing-1/photo.jpg");
  });

  it("sends store_id + pickup_token for pickup verification", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { order_id: "order-1" }));
    const services = clientWith(fetchImpl);
    await services.pickup.verifyPickupToken({ store_id: "store-1", pickup_token: "abcdef123456" });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/v1/merchant/pickups/verify");
    expect(JSON.parse(String(init.body))).toEqual({
      store_id: "store-1",
      pickup_token: "abcdef123456",
    });
  });

  it("passes dashboard filters through as query params", async () => {
    const urls: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      urls.push(url);
      return jsonResponse(200, { buckets: [], totals: {} });
    });
    const services = clientWith(fetchImpl);
    await services.merchantDashboard.getSales({ store_id: "store-1", group_by: "week" });
    await services.merchantDashboard.getInventory({ store_id: "store-1", low_stock_threshold: 5 });
    expect(urls[0]).toContain("/v1/merchant/dashboard/sales?store_id=store-1&group_by=week");
    expect(urls[1]).toContain("/v1/merchant/dashboard/inventory?store_id=store-1&low_stock_threshold=5");
  });
});
