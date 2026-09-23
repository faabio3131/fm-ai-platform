const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:8000";

export interface CommercialAccessStatus {
  tenant_id: string;
  enforcement_enabled: boolean;
  managed: boolean;
  product_account_id: string | null;
  operational_allowed: boolean;
  entitled: boolean;
  access_mode: "full" | "limited" | "billing_only" | "blocked" | null;
  reason: string;
  revision: number | null;
  stale: boolean;
}

export interface CommercialPlanPrice {
  price_id: string;
  currency: string;
  billing_period: string;
  amount: string;
}

export interface CommercialPlan {
  plan_code: string;
  rank: number;
  plan_version_id: string;
  display_name: string;
  description: string | null;
  marketing_badge: string | null;
  prices: CommercialPlanPrice[];
}

async function commercialRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`commercial_api_error:${response.status}`);
  }
  return (await response.json()) as T;
}

export function getCommercialAccess(): Promise<CommercialAccessStatus> {
  return commercialRequest<CommercialAccessStatus>("/v1/commercial/access");
}

export function getCommercialPlans(): Promise<CommercialPlan[]> {
  return commercialRequest<CommercialPlan[]>("/v1/commercial/plans");
}
