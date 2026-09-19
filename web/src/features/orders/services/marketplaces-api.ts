"use client";

import { API_BASE_URL } from "@/lib/api";

export interface MarketplaceIntegration {
  configuracao_id: string;
  plataforma: string;
  conta_externa: string;
  ambiente: string;
  habilitada: boolean;
  homologada: boolean;
  evidencia_homologacao_ref: string | null;
  pedidos_sincronizados: number;
  pronta_para_sincronizar: boolean;
}

export interface MarketplaceSyncResult {
  recebidos: number;
  processados: number;
  duplicados: number;
  retry: number;
  dlq: number;
  reconhecidos: number;
}

async function marketplaceApi<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Correlation-ID", crypto.randomUUID());
  const response = await fetch(
    `${API_BASE_URL}/v1/marketplaces${path}`,
    {
      ...init,
      headers,
      credentials: "include",
      cache: "no-store",
    },
  );
  if (!response.ok) {
    let code = "marketplace_indisponivel";
    try {
      const body = (await response.json()) as { erro?: unknown };
      if (typeof body.erro === "string") code = body.erro;
    } catch {
      // boundary permanece fail-closed
    }
    throw new Error(
      `Marketplace respondeu HTTP ${response.status} (${code})`,
    );
  }
  return (await response.json()) as T;
}

export async function listMarketplaceIntegrations(): Promise<
  MarketplaceIntegration[]
> {
  const result = await marketplaceApi<{ integracoes: MarketplaceIntegration[] }>(
    "",
  );
  return result.integracoes;
}

export async function syncMarketplace(
  configurationId: string,
): Promise<MarketplaceSyncResult> {
  return marketplaceApi(
    `/${encodeURIComponent(configurationId)}/sincronizar`,
    { method: "POST" },
  );
}
