export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL === "__SAME_ORIGIN__"
    ? ""
    : process.env.NEXT_PUBLIC_API_URL ||
      (process.env.NODE_ENV === "production" ? "/backend" : "http://localhost:8000");

export const ADMIN_STEP_UP_REQUIRED_EVENT = "kordena:admin-step-up-required";

function notifyAdminStepUpRequired(status: number, code?: string): void {
  if (
    status === 403 &&
    code === "seguranca.admin_step_up_exigido" &&
    typeof window !== "undefined"
  ) {
    window.dispatchEvent(new Event(ADMIN_STEP_UP_REQUIRED_EVENT));
  }
}

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
    public readonly code?: string,
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
    let code: string | undefined;
    try {
      const payload = (await response.json()) as { erro?: unknown };
      if (typeof payload?.erro === "string" && payload.erro.trim()) {
        code = payload.erro.trim();
      }
    } catch {
      // A fronteira HTTP pode responder sem JSON. O status continua sendo a fonte segura.
    }

    notifyAdminStepUpRequired(response.status, code);

    throw new ApiError(
      `Kordena API respondeu HTTP ${response.status}`,
      response.status,
      endpoint,
      code,
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
