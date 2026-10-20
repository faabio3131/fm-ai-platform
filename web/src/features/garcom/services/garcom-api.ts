"use client";

import { API_BASE_URL } from "@/lib/api";

export type ModoRecebimento = "na_mesa" | "no_caixa" | "hibrido";
export type DestinoRecebimento = "mesa" | "caixa";
export type MetodoFechamento =
  | "dinheiro"
  | "pix"
  | "cartao_credito"
  | "cartao_debito"
  | "voucher"
  | "recebimento_posterior";

export interface GarcomMesa {
  id: string;
  codigo: string;
  nome: string | null;
  capacidade: number;
  status: string;
  versao: number;
  disponivel_para_abertura: boolean;
}

export interface GarcomComanda {
  id: string;
  mesa_id: string | null;
  numero: string;
  status: string;
  responsavel_id: string;
  total: string;
  saldo: string;
  versao: number;
  propria: boolean;
}

export interface GarcomPainel {
  papel: string;
  kds_degradado: boolean;
  atualizado_em: string;
  mesas: GarcomMesa[];
  comandas: GarcomComanda[];
  alertas_prontos: Array<{
    producao_id: string;
    pedido_id: string;
    setor_nome: string;
    comanda_id: string;
    comanda_numero: string;
    mesa_id: string | null;
    mesa_codigo: string | null;
    pronta_em: string;
    versao: number;
  }>;
}

export interface ConfiguracaoFechamento {
  tenant_id: string;
  unidade_id: string;
  modo_recebimento: ModoRecebimento;
  taxa_servico_percentual: string;
  couvert_ativado: boolean;
  couvert_valor: string;
  versao: number;
}

export interface DemonstrativoFechamento {
  comanda_id: string;
  consumo: string;
  couvert_artistico: string;
  taxa_servico_percentual: string;
  taxa_servico_valor: string;
  taxa_servico_incluida: boolean;
  desconto: string;
  total: string;
  saldo: string;
  configuracao_versao: number;
  consolidado: boolean;
  destino_recebimento: DestinoRecebimento | null;
}

export interface ParcelaFechamento {
  metodo: MetodoFechamento;
  valor: string;
  participante_id?: string | null;
}

export interface PagamentoGarcom {
  id: string;
  pedido_id: string;
  comanda_id: string;
  metodo: string;
  status: string;
  valor_previsto: string;
  valor_pago: string;
  saldo: string;
  versao: number;
  idempotente: boolean;
}

export class GarcomApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "GarcomApiError";
  }
}

async function api<T>(
  path: string,
  init: RequestInit = {},
  idempotencyKey?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Correlation-ID", crypto.randomUUID());
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);

  const response = await fetch(`${API_BASE_URL}/v1/garcom${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    let code: string | undefined;
    try {
      const body = (await response.json()) as { erro?: unknown };
      if (typeof body.erro === "string") code = body.erro;
    } catch {
      code = undefined;
    }
    throw new GarcomApiError(
      `Garçom API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
      response.status,
      code,
    );
  }
  return (await response.json()) as T;
}

export function fetchGarcomPainel(): Promise<GarcomPainel> {
  return api("/painel");
}

export function abrirComandaGarcom(
  mesaId: string,
  versao: number,
  idempotencyKey = crypto.randomUUID(),
): Promise<{ comanda: GarcomComanda }> {
  return api(
    `/mesas/${encodeURIComponent(mesaId)}/comandas`,
    { method: "POST", body: JSON.stringify({ versao }) },
    idempotencyKey,
  );
}

export function solicitarContaGarcom(
  comandaId: string,
  versao: number,
  idempotencyKey = crypto.randomUUID(),
): Promise<{ comanda: GarcomComanda }> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/solicitar-conta`,
    { method: "POST", body: JSON.stringify({ versao }) },
    idempotencyKey,
  );
}

export function retomarConsumoGarcom(
  comandaId: string,
  versao: number,
  idempotencyKey = crypto.randomUUID(),
): Promise<{ comanda: GarcomComanda }> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/retomar-consumo`,
    { method: "POST", body: JSON.stringify({ versao }) },
    idempotencyKey,
  );
}

export function fetchConfiguracaoFechamento(): Promise<ConfiguracaoFechamento> {
  return api("/configuracao-fechamento");
}

export function salvarConfiguracaoFechamento(
  payload: Pick<
    ConfiguracaoFechamento,
    "modo_recebimento" | "couvert_ativado" | "couvert_valor" | "versao"
  >,
): Promise<ConfiguracaoFechamento> {
  return api("/configuracao-fechamento", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function fetchDemonstrativo(
  comandaId: string,
  incluirTaxaServico = true,
): Promise<DemonstrativoFechamento> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/demonstrativo?incluir_taxa_servico=${incluirTaxaServico}`,
  );
}

export function consolidarComponentes(
  comandaId: string,
  versao: number,
  incluirTaxaServico: boolean,
  idempotencyKey = crypto.randomUUID(),
): Promise<DemonstrativoFechamento> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/componentes`,
    {
      method: "POST",
      body: JSON.stringify({
        versao,
        incluir_taxa_servico: incluirTaxaServico,
      }),
    },
    idempotencyKey,
  );
}

export function definirDestino(
  comandaId: string,
  versao: number,
  destino: DestinoRecebimento,
  idempotencyKey = crypto.randomUUID(),
): Promise<{ destino: DestinoRecebimento }> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/destino`,
    { method: "POST", body: JSON.stringify({ versao, destino }) },
    idempotencyKey,
  );
}

export function definirDivisao(
  comandaId: string,
  versao: number,
  parcelas: ParcelaFechamento[],
  idempotencyKey = crypto.randomUUID(),
): Promise<{ comanda: GarcomComanda }> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/divisao`,
    { method: "POST", body: JSON.stringify({ versao, parcelas }) },
    idempotencyKey,
  );
}

export function criarPagamentoGarcom(
  comandaId: string,
  payload: {
    pagamento_id: string;
    pedido_id: string;
    metodo: MetodoFechamento;
    valor: string;
    provedor?: string | null;
  },
  idempotencyKey = crypto.randomUUID(),
): Promise<PagamentoGarcom> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/pagamentos`,
    { method: "POST", body: JSON.stringify(payload) },
    idempotencyKey,
  );
}

export function confirmarPagamentoGarcom(
  comandaId: string,
  pagamentoId: string,
  payload: {
    metodo: MetodoFechamento;
    valor: string;
    versao_pagamento: number;
    referencia_externa?: string | null;
  },
  idempotencyKey = crypto.randomUUID(),
): Promise<PagamentoGarcom> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/pagamentos/${encodeURIComponent(pagamentoId)}/confirmar`,
    { method: "POST", body: JSON.stringify(payload) },
    idempotencyKey,
  );
}

export function aplicarPagamentoGarcom(
  comandaId: string,
  pagamentoId: string,
  payload: {
    metodo: MetodoFechamento;
    valor: string;
    versao: number;
  },
  idempotencyKey = crypto.randomUUID(),
): Promise<{ comanda: GarcomComanda }> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/pagamentos/${encodeURIComponent(pagamentoId)}/aplicar`,
    { method: "POST", body: JSON.stringify(payload) },
    idempotencyKey,
  );
}

export function fecharComandaGarcom(
  comandaId: string,
  versao: number,
  idempotencyKey = crypto.randomUUID(),
): Promise<{ comanda: GarcomComanda }> {
  return api(
    `/comandas/${encodeURIComponent(comandaId)}/fechar`,
    { method: "POST", body: JSON.stringify({ versao }) },
    idempotencyKey,
  );
}
