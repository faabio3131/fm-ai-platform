"use client";

import { API_BASE_URL } from "@/lib/api";

export type SalaoMesaStatus = "LIVRE" | "OCUPADA" | "INATIVA";

export interface SalaoMesa {
  id: string;
  numero: string;
  nome: string | null;
  capacidade: number;
  status: SalaoMesaStatus;
}

export interface SalaoComandaMapa {
  id: string;
  mesa_id: string | null;
  status_comanda: string;
  total: string;
  aberta_em: string;
}

export interface SalaoFloorMap {
  mesas: SalaoMesa[];
  comandas: SalaoComandaMapa[];
}

export interface OpenComandaPayload {
  mesa_id: string;
  responsavel_nome?: string | null;
  quantidade_pessoas?: number | null;
}

export interface SalaoComanda {
  id: string;
  numero: string;
  mesa_id: string | null;
  status_comanda: string;
  total: string;
  saldo: string;
  aberta_em: string;
  versao: number;
}

export interface SalaoComandaMutation {
  idempotente: boolean;
  comanda: SalaoComanda;
}

export interface SalaoItemPedido {
  id: string;
  pedido_id: string;
  nome: string;
  quantidade: number;
  preco_unitario: string;
  subtotal: string;
  observacao: string | null;
}

export interface SalaoPedido {
  pedido_id: string;
  valor: string;
  criado_em: string;
  itens: SalaoItemPedido[];
}

export interface SalaoComandaDetails extends SalaoComanda {
  pedidos: SalaoPedido[];
}

export interface SalaoSessionContext {
  email: string;
  password: string;
  tenantId: string;
  unitId: string;
}

export class SalaoApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "SalaoApiError";
  }
}

let activeSession: SalaoSessionContext | null = null;

export function configureSalaoSession(context: SalaoSessionContext): void {
  const email = context.email.trim();
  const tenantId = context.tenantId.trim();
  const unitId = context.unitId.trim();

  if (!email || !context.password || !tenantId || !unitId) {
    throw new Error(
      "Credenciais, tenant e unidade são obrigatórios para operar o Salão.",
    );
  }

  activeSession = {
    email,
    password: context.password,
    tenantId,
    unitId,
  };
}

export function clearSalaoSession(): void {
  activeSession = null;
}

function requireSession(): SalaoSessionContext {
  if (!activeSession) {
    throw new SalaoApiError(
      "Sessão operacional do Salão não configurada.",
      401,
      "salao_session_missing",
    );
  }
  return activeSession;
}

function encodeBasicCredentials(email: string, password: string): string {
  const bytes = new TextEncoder().encode(`${email}:${password}`);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function buildHeaders(options?: {
  idempotencyKey?: string;
  json?: boolean;
}): Headers {
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
  if (options?.json) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

async function readApiError(response: Response): Promise<SalaoApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }

  return new SalaoApiError(
    `Salão API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

export async function fetchFloorMap(): Promise<SalaoFloorMap> {
  const response = await fetch(`${API_BASE_URL}/v1/salao/mapa`, {
    method: "GET",
    headers: buildHeaders(),
    cache: "no-store",
  });
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as SalaoFloorMap;
}

export async function openComanda(
  payload: OpenComandaPayload,
  idempotencyKey = crypto.randomUUID(),
): Promise<SalaoComandaMutation> {
  const response = await fetch(`${API_BASE_URL}/v1/salao/comandas/abrir`, {
    method: "POST",
    headers: buildHeaders({ idempotencyKey, json: true }),
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (response.status !== 200 && response.status !== 201) {
    throw await readApiError(response);
  }
  return (await response.json()) as SalaoComandaMutation;
}

export async function fetchComandaDetails(
  id: string,
): Promise<SalaoComandaDetails> {
  const response = await fetch(
    `${API_BASE_URL}/v1/salao/comandas/${encodeURIComponent(id)}`,
    {
      method: "GET",
      headers: buildHeaders(),
      cache: "no-store",
    },
  );
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as SalaoComandaDetails;
}

export async function requestBill(
  id: string,
  idempotencyKey = crypto.randomUUID(),
): Promise<SalaoComandaMutation> {
  const response = await fetch(
    `${API_BASE_URL}/v1/salao/comandas/${encodeURIComponent(id)}/solicitar-conta`,
    {
      method: "POST",
      headers: buildHeaders({ idempotencyKey }),
      cache: "no-store",
    },
  );
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as SalaoComandaMutation;
}
