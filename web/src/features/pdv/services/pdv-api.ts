"use client";

import { API_BASE_URL } from "@/lib/api";

export type PaymentMethod =
  | "dinheiro"
  | "pix"
  | "cartao_debito"
  | "cartao_credito";

export interface CatalogItem {
  id: string;
  nome: string;
  categoria: string | null;
  preco: string;
  disponivel: boolean;
}

interface CatalogResponse {
  produtos: CatalogItem[];
}

export interface CheckoutItemPayload {
  produto_id: string;
  quantidade: number;
  observacoes: string | null;
}

export interface CheckoutPayload {
  itens: CheckoutItemPayload[];
  metodo_pagamento: PaymentMethod;
  desconto: string;
  cliente_id: string | null;
}

export interface CheckoutOrderItem {
  produto_id: string | null;
  nome: string;
  quantidade: number;
  preco_unitario: string;
  subtotal: string;
  observacoes: string | null;
}

export interface CheckoutOrder {
  pedido_id: string;
  status: string;
  itens: CheckoutOrderItem[];
  subtotal: string;
  descontos: string;
  total: string;
}

export interface CheckoutPayment {
  id: string;
  status: string;
  metodo: string;
  valor_previsto: string;
  valor_pago: string;
  saldo: string;
}

export interface CheckoutResponse {
  comanda: CheckoutOrder;
  pagamento: CheckoutPayment | null;
  idempotente: boolean;
  correlation_id: string;
}

export interface PdvSessionContext {
  email: string;
  password: string;
  tenantId: string;
  unitId: string;
}

export class PdvApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "PdvApiError";
  }
}

let activeSession: PdvSessionContext | null = null;

export function configurePdvSession(context: PdvSessionContext): void {
  const email = context.email.trim();
  const tenantId = context.tenantId.trim();
  const unitId = context.unitId.trim();

  if (!email || !context.password || !tenantId || !unitId) {
    throw new Error("Credenciais, tenant e unidade são obrigatórios para operar o PDV.");
  }

  activeSession = {
    email,
    password: context.password,
    tenantId,
    unitId,
  };
}

export function clearPdvSession(): void {
  activeSession = null;
}

export function hasPdvSession(): boolean {
  return activeSession !== null;
}

function requireSession(): PdvSessionContext {
  if (!activeSession) {
    throw new PdvApiError("Sessão operacional do PDV não configurada.", 401, "pdv_session_missing");
  }
  return activeSession;
}

function encodeBasicCredentials(email: string, password: string): string {
  const bytes = new TextEncoder().encode(`${email}:${password}`);
  let binary = "";

  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

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

async function readApiError(response: Response): Promise<PdvApiError> {
  let code: string | undefined;

  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") {
      code = body.erro;
    }
  } catch {
    code = undefined;
  }

  const detail = code ? ` (${code})` : "";
  return new PdvApiError(
    `PDV API respondeu HTTP ${response.status}${detail}`,
    response.status,
    code,
  );
}

export async function fetchCatalog(): Promise<CatalogItem[]> {
  const response = await fetch(`${API_BASE_URL}/v1/pdv/produtos`, {
    method: "GET",
    headers: buildHeaders(),
    cache: "no-store",
  });

  if (response.status !== 200) {
    throw await readApiError(response);
  }

  const body = (await response.json()) as CatalogResponse;
  return body.produtos;
}

export async function submitCheckout(
  payload: CheckoutPayload,
): Promise<CheckoutResponse> {
  const idempotencyKey = crypto.randomUUID();
  const headers = buildHeaders({ idempotencyKey });
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}/v1/pdv/checkout`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
  });

  if (response.status !== 200 && response.status !== 201) {
    throw await readApiError(response);
  }

  return (await response.json()) as CheckoutResponse;
}
