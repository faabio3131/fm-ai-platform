"use client";

import { API_BASE_URL } from "@/lib/api";

export type KdsDestination =
  | "aceita"
  | "em_preparo"
  | "pausada"
  | "pronta"
  | "retirada"
  | "cancelada";

export interface KdsSector {
  setor_id: string;
  codigo: string;
  nome: string;
  ordem: number;
  sla_segundos: number | null;
  ativo: boolean;
  criado_em: string;
  atualizado_em: string;
}

export interface KdsSla {
  estado: string;
  decorrido_segundos: number;
  restante_segundos: number | null;
  percentual: number | null;
}

export interface KdsOrderItem {
  pedido_item_id: string;
  nome: string;
  quantidade: number;
  observacoes: string | null;
}

export interface KdsTicket {
  producao_id: string;
  pedido_id: string;
  pedido_item_id: string;
  setor_id: string;
  setor_nome: string;
  status: string;
  prioridade: number;
  quantidade: string;
  tentativa: number;
  versao: number;
  criado_em: string;
  atualizado_em: string;
  aceita_em: string | null;
  iniciada_em: string | null;
  pausa_iniciada_em: string | null;
  pronta_em: string | null;
  retirada_em: string | null;
  sla: KdsSla;
  itens: KdsOrderItem[];
}

export interface KdsQueueResponse {
  tickets: KdsTicket[];
  atualizado_em: string;
  degradado: boolean;
  somente_leitura: boolean;
  motivo_degradacao: string | null;
}

interface KdsSectorsResponse {
  setores: KdsSector[];
}

export interface KdsTransitionPayload {
  producao_id: string;
  destino: KdsDestination;
  versao_esperada: number;
  motivo: string | null;
}

export interface KdsTransitionResponse {
  producao_id: string;
  pedido_id: string;
  setor_id: string;
  status: string;
  versao: number;
  pedido_status: string;
  idempotente: boolean;
  atualizado_em: string;
}

export interface KdsSessionContext {
  email: string;
  password: string;
  tenantId: string;
  unitId: string;
}

export class KdsApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "KdsApiError";
  }
}

let activeSession: KdsSessionContext | null = null;

export function configureKdsSession(context: KdsSessionContext): void {
  const email = context.email.trim();
  const tenantId = context.tenantId.trim();
  const unitId = context.unitId.trim();

  if (!email || !context.password || !tenantId || !unitId) {
    throw new Error("Credenciais, tenant e unidade são obrigatórios para operar o KDS.");
  }

  activeSession = {
    email,
    password: context.password,
    tenantId,
    unitId,
  };
}

export function clearKdsSession(): void {
  activeSession = null;
}

function requireSession(): KdsSessionContext {
  if (!activeSession) {
    throw new KdsApiError("Sessão operacional do KDS não configurada.", 401, "kds_session_missing");
  }
  return activeSession;
}

function encodeBasicCredentials(email: string, password: string): string {
  const bytes = new TextEncoder().encode(`${email}:${password}`);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function buildHeaders(options?: { idempotencyKey?: string }): Headers {
  const session = requireSession();
  const headers = new Headers({
    Accept: "application/json",
    Authorization: `Basic ${encodeBasicCredentials(session.email, session.password)}`,
    "X-Tenant-ID": session.tenantId,
    "X-Unit-ID": session.unitId,
    "X-Correlation-ID": crypto.randomUUID(),
  });

  if (options?.idempotencyKey) {
    headers.set("Idempotency-Key", options.idempotencyKey);
  }
  return headers;
}

async function readApiError(response: Response): Promise<KdsApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }

  return new KdsApiError(
    `KDS API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

export async function fetchKdsSectors(): Promise<KdsSector[]> {
  const response = await fetch(`${API_BASE_URL}/v1/kds/setores`, {
    method: "GET",
    headers: buildHeaders(),
    cache: "no-store",
  });
  if (response.status !== 200) throw await readApiError(response);
  return ((await response.json()) as KdsSectorsResponse).setores;
}

export async function fetchKdsQueue(setorId?: string): Promise<KdsQueueResponse> {
  const query = setorId ? `?${new URLSearchParams({ setor_id: setorId })}` : "";
  const response = await fetch(`${API_BASE_URL}/v1/kds/fila${query}`, {
    method: "GET",
    headers: buildHeaders(),
    cache: "no-store",
  });
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as KdsQueueResponse;
}

export async function transitionKds(
  payload: KdsTransitionPayload,
): Promise<KdsTransitionResponse> {
  const headers = buildHeaders({ idempotencyKey: crypto.randomUUID() });
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}/v1/kds/transicionar`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as KdsTransitionResponse;
}
