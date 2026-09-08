"use client";

import { API_BASE_URL } from "@/lib/api";

export interface OrderCenterFinancial {
  situacao: string;
  valor_previsto: string;
  valor_pago: string;
  pagamento_ids: string[];
  venda_financeira_id: string | null;
  venda_legada_id: string | null;
  reconciliacao_id: string | null;
  reconciliacao_status: string | null;
}

export interface OrderCenterSummary {
  pedido_id: string;
  canal: string;
  status: string;
  criado_em: string;
  atualizado_em: string;
  total: string;
  quantidade_itens: number;
  cliente_id: string | null;
  financeiro: OrderCenterFinancial;
  possui_alerta: boolean;
  origem: string;
  versao: number;
}

export interface OrderCenterPage {
  itens: OrderCenterSummary[];
  pagina: number;
  tamanho_pagina: number;
  total: number;
}

export interface OrderCenterItem {
  item_id: string;
  nome: string;
  quantidade: number;
  preco_unitario: string;
  subtotal: string;
  observacao: string | null;
  adicionais: [string, number, string, string][];
}

export interface OrderCenterEvent {
  evento_id: string;
  tipo: string;
  ocorrido_em: string;
  versao: number;
  correlation_id: string;
}

export interface OrderCenterAlert {
  tipo: string;
  severidade: string;
  mensagem: string;
}

export interface OrderCenterDetail {
  resumo: OrderCenterSummary;
  subtotal: string;
  descontos: string;
  taxas: string;
  itens: OrderCenterItem[];
  observacoes: string[];
  timeline: OrderCenterEvent[];
  financeiro: OrderCenterFinancial;
  alertas: OrderCenterAlert[];
}

export interface OrderCenterTransition {
  pedido_id: string;
  status: string;
  versao: number;
  idempotente: boolean;
  correlation_id: string;
}

export interface OrderCenterFilters {
  busca?: string;
  status?: string;
  canal?: string;
  somenteComAlertas?: boolean;
  situacaoFinanceira?: string;
  pagina?: number;
  tamanhoPagina?: number;
}

export class OrdersApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "OrdersApiError";
  }
}

function headers(idempotencyKey?: string): Headers {
  const value = new Headers({
    Accept: "application/json",
    "X-Correlation-ID": crypto.randomUUID(),
  });
  if (idempotencyKey) value.set("Idempotency-Key", idempotencyKey);
  return value;
}

async function apiError(response: Response): Promise<OrdersApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }
  return new OrdersApiError(
    `Central de Pedidos respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

export async function listOrders(
  filters: OrderCenterFilters = {},
): Promise<OrderCenterPage> {
  const query = new URLSearchParams();
  if (filters.busca?.trim()) query.set("busca", filters.busca.trim());
  if (filters.status?.trim()) query.append("status", filters.status.trim());
  if (filters.canal?.trim()) query.append("canal", filters.canal.trim());
  if (filters.somenteComAlertas) query.set("somente_com_alertas", "true");
  if (filters.situacaoFinanceira?.trim()) {
    query.set("situacao_financeira", filters.situacaoFinanceira.trim());
  }
  query.set("pagina", String(filters.pagina ?? 1));
  query.set("tamanho_pagina", String(filters.tamanhoPagina ?? 25));

  const response = await fetch(`${API_BASE_URL}/v1/pedidos?${query.toString()}`, {
    method: "GET",
    headers: headers(),
    credentials: "include",
    cache: "no-store",
  });
  if (response.status !== 200) throw await apiError(response);
  return (await response.json()) as OrderCenterPage;
}

export async function getOrderDetail(orderId: string): Promise<OrderCenterDetail> {
  const response = await fetch(
    `${API_BASE_URL}/v1/pedidos/${encodeURIComponent(orderId)}`,
    {
      method: "GET",
      headers: headers(),
      credentials: "include",
      cache: "no-store",
    },
  );
  if (response.status !== 200) throw await apiError(response);
  return (await response.json()) as OrderCenterDetail;
}

export async function sendOrderToConfirmation(
  orderId: string,
  expectedVersion: number,
): Promise<OrderCenterTransition> {
  const requestHeaders = headers(crypto.randomUUID());
  requestHeaders.set("Content-Type", "application/json");
  const response = await fetch(
    `${API_BASE_URL}/v1/pedidos/${encodeURIComponent(orderId)}/enviar-confirmacao`,
    {
      method: "POST",
      headers: requestHeaders,
      credentials: "include",
      cache: "no-store",
      body: JSON.stringify({ versao_esperada: expectedVersion }),
    },
  );
  if (response.status !== 200) throw await apiError(response);
  return (await response.json()) as OrderCenterTransition;
}

export async function cancelOrder(
  orderId: string,
  expectedVersion: number,
  reason: string,
): Promise<OrderCenterTransition> {
  const requestHeaders = headers(crypto.randomUUID());
  requestHeaders.set("Content-Type", "application/json");
  const response = await fetch(
    `${API_BASE_URL}/v1/pedidos/${encodeURIComponent(orderId)}/cancelar`,
    {
      method: "POST",
      headers: requestHeaders,
      credentials: "include",
      cache: "no-store",
      body: JSON.stringify({ versao_esperada: expectedVersion, motivo: reason }),
    },
  );
  if (response.status !== 200) throw await apiError(response);
  return (await response.json()) as OrderCenterTransition;
}
