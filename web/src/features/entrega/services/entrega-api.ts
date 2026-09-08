"use client";

import { API_BASE_URL } from "@/lib/api";

export interface EntregaItem {
  entrega_id: string;
  pedido_id: string;
  endereco_id: string;
  modalidade: string;
  status: string;
  versao: number;
  tentativa: number;
  entregador_id: string | null;
  producao_pronta_em: string | null;
  checklist_concluido_em: string | null;
  atribuida_em: string | null;
  coletada_em: string | null;
  saiu_em: string | null;
  entregue_em: string | null;
  prova_entrega_ref: string | null;
}

export interface EntregaEvent {
  event_id: string;
  tipo: string;
  ocorrido_em: string;
  versao_entrega: number;
  correlation_id: string;
  payload: Record<string, unknown>;
}

export interface EntregaDetail {
  entrega: EntregaItem;
  eventos: EntregaEvent[];
}

export interface EntregadorElegivel {
  usuario_id: string;
  email: string;
}

export class EntregaApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "EntregaApiError";
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

async function apiError(response: Response): Promise<EntregaApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }
  return new EntregaApiError(
    `Expedição/Entrega respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers: headers(),
    credentials: "include",
    cache: "no-store",
  });
  if (response.status !== 200) throw await apiError(response);
  return (await response.json()) as T;
}

async function command<T>(path: string, body: unknown): Promise<T> {
  const requestHeaders = headers(crypto.randomUUID());
  requestHeaders.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: requestHeaders,
    credentials: "include",
    cache: "no-store",
    body: JSON.stringify(body),
  });
  if (response.status < 200 || response.status >= 300) throw await apiError(response);
  return (await response.json()) as T;
}

export async function listEntregas(): Promise<EntregaItem[]> {
  const result = await getJson<{ itens: EntregaItem[] }>("/v1/entregas");
  return result.itens;
}

export function getEntregaDetail(entregaId: string): Promise<EntregaDetail> {
  return getJson(`/v1/entregas/${encodeURIComponent(entregaId)}`);
}

export async function listEligibleDrivers(): Promise<EntregadorElegivel[]> {
  const result = await getJson<{ itens: EntregadorElegivel[] }>(
    "/v1/entregas/entregadores-elegiveis",
  );
  return result.itens;
}

export function completeChecklist(
  entregaId: string,
  expectedVersion: number,
  values: {
    itens_conferidos: boolean;
    embalagem_conferida: boolean;
    identificacao_conferida: boolean;
    observacao_operacional?: string;
  },
): Promise<EntregaItem> {
  return command(`/v1/entregas/${encodeURIComponent(entregaId)}/checklist`, {
    versao_esperada: expectedVersion,
    ...values,
  });
}

export function assignDriver(
  entregaId: string,
  expectedVersion: number,
  driverId: string,
): Promise<EntregaItem> {
  return command(`/v1/entregas/${encodeURIComponent(entregaId)}/atribuir`, {
    versao_esperada: expectedVersion,
    entregador_id: driverId,
  });
}

export function collectDelivery(
  entregaId: string,
  expectedVersion: number,
): Promise<EntregaItem> {
  return command(`/v1/entregas/${encodeURIComponent(entregaId)}/coletar`, {
    versao_esperada: expectedVersion,
  });
}

export function startRoute(
  entregaId: string,
  expectedVersion: number,
): Promise<EntregaItem> {
  return command(`/v1/entregas/${encodeURIComponent(entregaId)}/sair-em-rota`, {
    versao_esperada: expectedVersion,
  });
}

export function confirmDelivered(
  entregaId: string,
  expectedVersion: number,
  proofReference: string,
): Promise<EntregaItem> {
  return command(`/v1/entregas/${encodeURIComponent(entregaId)}/confirmar`, {
    versao_esperada: expectedVersion,
    prova_referencia: proofReference,
    prova_tipo: "confirmacao",
  });
}

export function registerFailedAttempt(
  entregaId: string,
  expectedVersion: number,
  reason: string,
): Promise<EntregaItem> {
  return command(`/v1/entregas/${encodeURIComponent(entregaId)}/tentativa-falha`, {
    versao_esperada: expectedVersion,
    motivo: reason,
  });
}
