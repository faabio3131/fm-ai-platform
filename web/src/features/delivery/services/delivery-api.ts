"use client";

import { API_BASE_URL } from "@/lib/api";

export interface DeliveryClient {
  cliente_id: string;
  origem: string;
  canais: string[];
  criado_em: string;
  versao: number;
}

export interface DeliveryProduct {
  produto_id: string;
  nome: string;
  preco: string;
  estoque_disponivel: string;
  ativo: boolean;
  versao: number;
}

export interface DeliveryContext {
  cliente: DeliveryClient;
  endereco: {
    referencia: string;
    endereco_formatado: string;
    cep: string;
  };
  catalogo: DeliveryProduct[];
  origem_entrega: { endereco_texto: string; versao: number };
  areas_entrega: Array<{
    area_id: string;
    nome: string;
    taxa: string;
    sla_minutos: number;
    sla_maxutos: number;
    versao: number;
    ativa: boolean;
  }>;
}

export interface DeliveryRoute {
  cliente_id: string;
  provedor: "google_maps";
  origem_endereco: string;
  destino_endereco: string;
  distancia_metros: number;
  distancia_km: number;
  eta_minutos: number;
  polyline_codificada: string;
  origem: {
    latitude: number;
    longitude: number;
    versao: number;
  };
  destino: {
    latitude: number;
    longitude: number;
    endereco_ref: string;
  };
}

export interface DeliveryCart {
  carrinho_id: string;
  cliente_id: string;
  versao: number;
  status: string;
  itens: Array<{
    produto_id: string;
    nome: string;
    quantidade: number;
    preco_unitario: string;
    subtotal: string;
    produto_versao: number;
  }>;
  endereco: null | {
    endereco_id: string;
    cep: string;
    logradouro: string;
    numero: string;
    bairro: string;
    cidade: string;
    uf: string;
  };
  cotacao: null | {
    area_id: string;
    nome_area: string;
    taxa: string;
    sla_minutos: number;
    sla_maxutos: number;
    versao_area: number;
  };
  subtotal: string;
  taxa_entrega: string;
  desconto_cupom: string;
  cashback_reservado: string;
  total: string;
  pedido_id: string | null;
}

export interface DeliveryConfirmation {
  pedido_id: string;
  entrega_id: string;
  status_pedido: string;
  status_entrega: string;
}

export interface DeliveryTracking {
  pedido_id: string;
  status_pedido: string;
  entrega_id: string;
  status_entrega: string;
  total: string;
  eventos: Array<{
    tipo: string;
    ocorrido_em: string;
    status_entrega: string;
  }>;
}

export class DeliveryApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "DeliveryApiError";
  }
}

function requestHeaders(idempotencyKey?: string): Headers {
  const headers = new Headers({
    Accept: "application/json",
    "X-Correlation-ID": crypto.randomUUID(),
  });
  if (idempotencyKey) headers.set("Idempotency-Key", idempotencyKey);
  return headers;
}

async function apiError(response: Response): Promise<DeliveryApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }
  return new DeliveryApiError(
    `Delivery respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers: requestHeaders(),
    credentials: "include",
    cache: "no-store",
  });
  if (response.status !== 200) throw await apiError(response);
  return (await response.json()) as T;
}

async function postJson<T>(
  path: string,
  body: unknown,
  { idempotent = false }: { idempotent?: boolean } = {},
): Promise<T> {
  const headers = requestHeaders(idempotent ? crypto.randomUUID() : undefined);
  headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    credentials: "include",
    cache: "no-store",
    body: JSON.stringify(body),
  });
  if (response.status < 200 || response.status >= 300) throw await apiError(response);
  return (await response.json()) as T;
}

export async function listDeliveryClients(): Promise<DeliveryClient[]> {
  const result = await getJson<{ itens: DeliveryClient[] }>("/v1/delivery/clientes");
  return result.itens;
}

export function getDeliveryContext(clientId: string): Promise<DeliveryContext> {
  return getJson(`/v1/delivery/clientes/${encodeURIComponent(clientId)}/contexto`);
}

export function getDeliveryRoute(clientId: string): Promise<DeliveryRoute> {
  return getJson(`/v1/delivery/clientes/${encodeURIComponent(clientId)}/rota`);
}

export function openDeliveryCart(clientId: string, cartId: string): Promise<DeliveryCart> {
  return postJson("/v1/delivery/carrinhos", {
    cliente_id: clientId,
    carrinho_id: cartId,
  });
}

export function addDeliveryItem(
  clientId: string,
  cartId: string,
  productId: string,
  expectedVersion: number,
  quantity = 1,
): Promise<DeliveryCart> {
  return postJson(
    `/v1/delivery/clientes/${encodeURIComponent(clientId)}/carrinhos/${encodeURIComponent(cartId)}/itens`,
    {
      produto_id: productId,
      quantidade: quantity,
      versao_esperada: expectedVersion,
    },
  );
}

export function quoteDelivery(
  clientId: string,
  cartId: string,
  expectedVersion: number,
): Promise<DeliveryCart> {
  return postJson(
    `/v1/delivery/clientes/${encodeURIComponent(clientId)}/carrinhos/${encodeURIComponent(cartId)}/cotacao`,
    { versao_esperada: expectedVersion },
  );
}

export function confirmDeliveryOrder(
  clientId: string,
  cartId: string,
  paymentMethod: string,
): Promise<DeliveryConfirmation> {
  return postJson(
    `/v1/delivery/clientes/${encodeURIComponent(clientId)}/carrinhos/${encodeURIComponent(cartId)}/confirmar`,
    { metodo_pagamento: paymentMethod },
    { idempotent: true },
  );
}

export function getDeliveryTracking(
  clientId: string,
  orderId: string,
): Promise<DeliveryTracking> {
  return getJson(
    `/v1/delivery/clientes/${encodeURIComponent(clientId)}/pedidos/${encodeURIComponent(orderId)}`,
  );
}

export function cancelDeliveryOrder(
  clientId: string,
  orderId: string,
  reason: string,
): Promise<DeliveryTracking> {
  return postJson(
    `/v1/delivery/clientes/${encodeURIComponent(clientId)}/pedidos/${encodeURIComponent(orderId)}/cancelar`,
    { motivo: reason },
    { idempotent: true },
  );
}
