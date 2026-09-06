export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface ApiContext {
  token?: string;
  tenantId?: string;
  unitId?: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly endpoint: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function buildHeaders(
  init: RequestInit,
  context: ApiContext,
): Headers {
  const headers = new Headers(init.headers);

  if (context.token) {
    headers.set("Authorization", `Bearer ${context.token}`);
  }
  if (context.tenantId) {
    headers.set("X-Tenant-ID", context.tenantId);
  }
  if (context.unitId) {
    headers.set("X-Unit-ID", context.unitId);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  return headers;
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  context: ApiContext = {},
): Promise<T> {
  const endpoint = `${API_BASE_URL}${path}`;
  const response = await fetch(endpoint, {
    ...init,
    headers: buildHeaders(init, context),
    cache: "no-store",
  });

  if (!response.ok) {
    throw new ApiError(
      `Kordena API respondeu HTTP ${response.status}`,
      response.status,
      endpoint,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export interface BackendHealth {
  ok: boolean;
  backend?: string;
  detail?: string | null;
}

export interface BackendHealthResult {
  endpoint: "/health/live" | "/healthz";
  health: BackendHealth;
}

export async function checkBackendHealth(): Promise<BackendHealthResult> {
  const candidates = ["/health/live", "/healthz"] as const;
  let lastError: unknown;

  for (const endpoint of candidates) {
    try {
      const health = await apiRequest<BackendHealth>(endpoint);
      return { endpoint, health };
    } catch (error) {
      lastError = error;
      if (error instanceof ApiError && error.status === 404) {
        continue;
      }
      throw error;
    }
  }

  throw lastError ?? new Error("Backend health endpoint indisponível");
}
