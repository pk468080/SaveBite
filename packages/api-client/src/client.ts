/**
 * Shared SaveBite API client — framework-independent.
 *
 * Talks only to the existing FastAPI backend. It never
 * talks to Supabase directly, never stores credentials,
 * and never re-implements backend business rules.
 *
 * Error envelope (verified against the backend): every
 * error response is `{"error": {"code", "message",
 * "request_id"}}`. Network failures and timeouts are
 * surfaced as ApiError with code NETWORK_ERROR /
 * TIMEOUT so callers can handle them uniformly.
 */

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.requestId = body.request_id;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }

  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

export interface ApiClientOptions {
  baseUrl: string;
  /** Called before each request; returns the current Supabase access token, if any. */
  getAccessToken?: () => string | null | Promise<string | null>;
  /** Request timeout in milliseconds (default 15000). */
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Extra headers for this request only. */
  headers?: Record<string, string>;
  /** Idempotency key for create/payment/refund calls (backend requirement). */
  idempotencyKey?: string;
}

const DEFAULT_TIMEOUT_MS = 15000;

export class ApiClient {
  private readonly baseUrl: string;
  private readonly getAccessToken?: ApiClientOptions["getAccessToken"];
  private readonly timeoutMs: number;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.getAccessToken = options.getAccessToken;
    this.timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async request<T>(
    method: string,
    path: string,
    body?: unknown,
    options: RequestOptions = {},
  ): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    const signal = options.signal
      ? AbortSignal.any([options.signal, controller.signal])
      : controller.signal;
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...options.headers,
      };
      const token = await this.getAccessToken?.();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      if (options.idempotencyKey) {
        headers["Idempotency-Key"] = options.idempotencyKey;
      }
      let response: Response;
      try {
        response = await this.fetchImpl(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: body === undefined ? undefined : JSON.stringify(body),
          signal,
        });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          throw new ApiError(0, {
            code: "TIMEOUT",
            message: "The request timed out. Please try again.",
          });
        }
        throw new ApiError(0, {
          code: "NETWORK_ERROR",
          message: "Could not reach the SaveBite server. Check your connection and try again.",
        });
      }
      if (!response.ok) {
        throw await ApiClient.parseError(response);
      }
      if (response.status === 204) {
        return undefined as T;
      }
      return (await response.json()) as T;
    } finally {
      clearTimeout(timeout);
    }
  }

  private static async parseError(response: Response): Promise<ApiError> {
    try {
      const data = (await response.json()) as {
        error?: ApiErrorBody;
      };
      if (data?.error?.message) {
        return new ApiError(response.status, data.error);
      }
    } catch {
      // Fall through to a generic error below.
    }
    return new ApiError(response.status, {
      code: `HTTP_${response.status}`,
      message: `Request failed with status ${response.status}.`,
    });
  }

  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>("GET", path, undefined, options);
  }

  post<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>("POST", path, body, options);
  }

  put<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>("PUT", path, body, options);
  }

  patch<T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>("PATCH", path, body, options);
  }
}

export function createApiClient(options: ApiClientOptions): ApiClient {
  return new ApiClient(options);
}
