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
  valor_recebido?: string;
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

/** Compatibilidade legada/M2M. O browser comercial não deve chamar esta função. */
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

function encodeBasicCredentials(email: string, password: string): string {
  const bytes = new TextEncoder().encode(`${email}:${password}`);
  let binary = "";

  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }

  return btoa(binary);
}

function buildHeaders(options?: { idempotencyKey?: string }): Headers {
  const headers = new Headers({
    Accept: "application/json",
    "X-Correlation-ID": crypto.randomUUID(),
  });

  if (activeSession) {
    headers.set(
      "Authorization",
      `Basic ${encodeBasicCredentials(activeSession.email, activeSession.password)}`,
    );
    headers.set("X-Tenant-ID", activeSession.tenantId);
    headers.set("X-Unit-ID", activeSession.unitId);
  }

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
    credentials: "include",
  });

  if (response.status !== 200) {
    throw await readApiError(response);
  }

  const body = (await response.json()) as CatalogResponse;
  return body.produtos;
}

export async function submitCheckout(
  payload: CheckoutPayload,
  idempotencyKey = crypto.randomUUID(),
): Promise<CheckoutResponse> {
  const headers = buildHeaders({ idempotencyKey });
  headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}/v1/pdv/checkout`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    cache: "no-store",
    credentials: "include",
  });

  if (response.status !== 200 && response.status !== 201) {
    throw await readApiError(response);
  }

  return (await response.json()) as CheckoutResponse;
}

export interface PixPagadorPayload {
  nome: string;
  email: string;
  documento: string;
}

export interface PixPagBankCobranca {
  pagamento_id: string;
  order_id: string;
  status_provedor: string;
  status_pagamento: string;
  pix_copia_cola: string | null;
  qr_code_url: string | null;
  idempotente: boolean;
}

export interface PixPagBankStatus {
  pagamento_id: string;
  order_id: string;
  status_pagamento: string;
}

export async function iniciarPixPagBank(
  pagamentoId: string,
  pagador: PixPagadorPayload,
): Promise<PixPagBankCobranca> {
  const headers = buildHeaders();
  headers.set("Content-Type", "application/json");
  const response = await fetch(
    `${API_BASE_URL}/v1/pdv/pagamentos/${encodeURIComponent(pagamentoId)}/iniciar-pix-pagbank`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(pagador),
      cache: "no-store",
      credentials: "include",
    },
  );
  if (response.status !== 200 && response.status !== 201) {
    throw await readApiError(response);
  }
  return (await response.json()) as PixPagBankCobranca;
}

export async function verificarPixPagBank(
  pagamentoId: string,
): Promise<PixPagBankStatus> {
  const response = await fetch(
    `${API_BASE_URL}/v1/pdv/pagamentos/${encodeURIComponent(pagamentoId)}/verificar-pix-pagbank`,
    {
      method: "POST",
      headers: buildHeaders(),
      cache: "no-store",
      credentials: "include",
    },
  );
  if (response.status !== 200) {
    throw await readApiError(response);
  }
  return (await response.json()) as PixPagBankStatus;
}

export interface CartaoTerminalConfirmacao {
  pagamento_id: string;
  status: string;
  metodo: string;
  referencia_terminal: string;
  idempotente: boolean;
}

/** Registro da aprovação emitida no POS físico; não captura cartão. */
export async function confirmarCartaoNoTerminal(
  pagamentoId: string,
  referenciaTerminal: string,
): Promise<CartaoTerminalConfirmacao> {
  const headers = buildHeaders();
  headers.set("Content-Type", "application/json");
  const response = await fetch(
    `${API_BASE_URL}/v1/pdv/pagamentos/${encodeURIComponent(pagamentoId)}/confirmar-cartao-terminal`,
    {
      method: "POST",
      headers,
      cache: "no-store",
      credentials: "include",
      body: JSON.stringify({
        referencia_terminal: referenciaTerminal,
        autorizado_no_terminal: true,
      }),
    },
  );
  if (response.status !== 200) {
    throw await readApiError(response);
  }
  return (await response.json()) as CartaoTerminalConfirmacao;
}

export interface CheckoutCartaoPagBank {
  pagamento_id: string;
  checkout_id: string;
  pagamento_url: string;
  status_provedor: string;
  status_pagamento: string;
  idempotente: boolean;
}

export async function criarCheckoutCartaoPagBank(
  pagamentoId: string,
): Promise<CheckoutCartaoPagBank> {
  const resposta = await fetch(
    `${API_BASE_URL}/v1/pdv/pagamentos/${encodeURIComponent(pagamentoId)}/criar-checkout-cartao-pagbank`,
    {
      method: "POST",
      headers: buildHeaders(),
      credentials: "include",
      cache: "no-store",
    },
  );
  if (resposta.status !== 201 && resposta.status !== 200) {
    throw await readApiError(resposta);
  }
  return (await resposta.json()) as CheckoutCartaoPagBank;
}

export async function verificarCheckoutCartaoPagBank(
  pagamentoId: string,
): Promise<CheckoutCartaoPagBank> {
  const resposta = await fetch(
    `${API_BASE_URL}/v1/pdv/pagamentos/${encodeURIComponent(pagamentoId)}/verificar-checkout-cartao-pagbank`,
    {
      method: "POST",
      headers: buildHeaders(),
      credentials: "include",
      cache: "no-store",
    },
  );
  if (resposta.status !== 200) {
    throw await readApiError(resposta);
  }
  return (await resposta.json()) as CheckoutCartaoPagBank;
}
