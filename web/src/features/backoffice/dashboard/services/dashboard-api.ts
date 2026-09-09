import { API_BASE_URL } from "@/lib/api";

export interface FinanceiroExecutivo {
  vendas_reconhecidas: string;
  quantidade_vendas: number;
  ticket_medio: string;
  pagamentos_pagos: string;
  pagamentos_pendentes: string;
  pagamentos_estornados: string;
  recebido_dinheiro: string;
  cmv_estimado_atual: string | null;
  margem_estimada_atual: string | null;
  cobertura_cmv_itens_pct: string;
}

export interface OperacaoExecutiva {
  pedidos: number;
  estoque_fisico_total: string;
  estoque_reservado_total: string;
  entregas_por_status: { status: string; quantidade: number }[];
  integracoes_configuradas: number;
  integracoes_homologadas: number;
  usuarios_ativos: number;
}

export interface PainelExecutivo {
  tenant_id: string;
  unidades: string[];
  financeiro: FinanceiroExecutivo;
  operacional: OperacaoExecutiva;
}

export async function obterPainelExecutivo(): Promise<PainelExecutivo> {
  const response = await fetch(`${API_BASE_URL}/v1/admin/painel-executivo`, {
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Painel executivo respondeu HTTP ${response.status}`);
  }
  return (await response.json()) as PainelExecutivo;
}
