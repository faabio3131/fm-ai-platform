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


export type CommercialPaymentMethod = "pix" | "card" | "boleto" | "bank_transfer";

export interface CommercialCheckoutResult {
  subscription_id: string;
  subscription_status: string;
  provider_code: string;
  provider_account_id: string;
  external_checkout_ref: string;
  billing_binding_id: string;
  checkout_url: string;
}

export async function startCommercialCheckout(input: {
  plan_code: string;
  plan_version_id: string;
  price_id: string;
  payment_method: CommercialPaymentMethod;
}): Promise<CommercialCheckoutResult> {
  const currentUrl = new URL(window.location.href);
  const successUrl = new URL(currentUrl);
  successUrl.searchParams.set("commercial_checkout", "success");
  const cancelUrl = new URL(currentUrl);
  cancelUrl.searchParams.set("commercial_checkout", "cancel");

  const response = await fetch(`${API_BASE_URL}/v1/commercial/checkout`, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({
      ...input,
      success_url: successUrl.toString(),
      cancel_url: cancelUrl.toString(),
    }),
  });
  if (!response.ok) {
    throw new Error(`commercial_checkout_error:${response.status}`);
  }
  return (await response.json()) as CommercialCheckoutResult;
}
