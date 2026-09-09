import { API_BASE_URL } from "@/lib/api";

export interface AIFinOpsResumo {
  attempts: number;
  success_attempts: number;
  failure_attempts: number;
  fallback_attempts: number;
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  latency_ms_average: string;
  latency_ms_max: number;
  cost_known_events: number;
  cost_unknown_events: number;
  success_rate_pct: string;
  fallback_rate_pct: string;
  cost_coverage_pct: string;
  custos: { moeda: string; valor: string; eventos: number }[];
  mix: { provider: string; model: string; attempts: number }[];
}

export interface AIFinOpsPainel {
  tenant_id: string;
  unidade_id: string;
  inicio: string;
  fim: string;
  resumo: AIFinOpsResumo;
}

export async function obterResumoAIFinOps(
  inicio: string,
  fim: string,
): Promise<AIFinOpsPainel> {
  const query = new URLSearchParams({ inicio, fim });
  const response = await fetch(`${API_BASE_URL}/v1/ai-finops/resumo?${query}`, {
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`AI FinOps respondeu HTTP ${response.status}`);
  }
  return (await response.json()) as AIFinOpsPainel;
}
