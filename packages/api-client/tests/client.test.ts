import { describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "../src/client";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("ApiClient", () => {
  it("attaches the bearer token when authenticated", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { ok: true }));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000/",
      getAccessToken: () => "tok-123",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    await client.get("/v1/me");
    const call = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    const [, init] = call;
    expect(call[0]).toBe("http://localhost:8000/v1/me");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-123");
  });

  it("sends no token when unauthenticated", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(200, { ok: true }));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    await client.get("/v1/marketplace/listings");
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("parses the FastAPI error envelope", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(422, {
        error: { code: "VALIDATION_ERROR", message: "Invalid rating", request_id: "req-1" },
      }),
    );
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    await expect(client.get("/v1/nope")).rejects.toMatchObject({
      status: 422,
      code: "VALIDATION_ERROR",
      requestId: "req-1",
    });
  });

  it("classifies 401 and 403", async () => {
    const make = (status: number) =>
      new ApiClient({
        baseUrl: "http://localhost:8000",
        fetchImpl: (async () =>
          jsonResponse(status, { error: { code: "X", message: "denied" } })) as unknown as typeof fetch,
      });
    await expect(make(401).get("/v1/me")).rejects.toMatchObject({ isUnauthorized: true });
    await expect(make(403).get("/v1/admin/dashboard")).rejects.toMatchObject({
      isForbidden: true,
    });
  });

  it("passes idempotency keys through", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse(201, { ok: true }));
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: fetchImpl as unknown as typeof fetch,
    });
    await client.post("/v1/orders/reservations", {}, { idempotencyKey: "key-1" });
    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe("key-1");
  });

  it("handles network failure as NETWORK_ERROR", async () => {
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: (async () => {
        throw new TypeError("fetch failed");
      }) as unknown as typeof fetch,
    });
    await expect(client.get("/v1/me")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("honours caller cancellation", async () => {
    const controller = new AbortController();
    controller.abort();
    const client = new ApiClient({
      baseUrl: "http://localhost:8000",
      fetchImpl: (async (_url: string, init?: RequestInit) => {
        if (init?.signal?.aborted) {
          throw new DOMException("Aborted", "AbortError");
        }
        return jsonResponse(200, {});
      }) as unknown as typeof fetch,
    });
    await expect(
      client.get("/v1/me", { signal: controller.signal }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
