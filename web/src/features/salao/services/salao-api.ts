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

export interface SalaoProduto {
  id: string;
  nome: string;
  categoria: string | null;
  preco: string;
  disponivel: boolean;
}

interface CatalogoProduto {
  id: string;
  nome: string;
  categoria: string | null;
  preco: number;
  ativo: boolean;
}

export interface LancamentoPedidoItemPayload {
  produto_id: string;
  quantidade: number;
  observacao?: string | null;
}

export interface LancamentoPedidoPayload {
  itens: LancamentoPedidoItemPayload[];
}

export interface SalaoLancamentoPedido {
  idempotente: boolean;
  comanda: SalaoComanda;
  pedido: SalaoPedido;
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

/** Compatibilidade legada/M2M. O browser comercial usa fm_ai_session. */
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
    credentials: "include",
  });
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as SalaoFloorMap;
}

export async function fetchProdutosSalao(): Promise<SalaoProduto[]> {
  const response = await fetch(
    `${API_BASE_URL}/v1/catalogo/produtos?apenas_ativos=true`,
    {
      method: "GET",
      headers: buildHeaders(),
      cache: "no-store",
      credentials: "include",
    },
  );
  if (response.status !== 200) throw await readApiError(response);
  const produtos = (await response.json()) as CatalogoProduto[];
  return produtos.map((produto) => ({
    id: `legacy:produto:${produto.id}`,
    nome: produto.nome,
    categoria: produto.categoria,
    preco: String(produto.preco),
    disponivel: produto.ativo,
  }));
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
    credentials: "include",
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
      credentials: "include",
    },
  );
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as SalaoComandaDetails;
}

export async function launchOrder(
  id: string,
  payload: LancamentoPedidoPayload,
  idempotencyKey = crypto.randomUUID(),
): Promise<SalaoLancamentoPedido> {
  const response = await fetch(
    `${API_BASE_URL}/v1/salao/comandas/${encodeURIComponent(id)}/pedidos`,
    {
      method: "POST",
      headers: buildHeaders({ idempotencyKey, json: true }),
      body: JSON.stringify(payload),
      cache: "no-store",
      credentials: "include",
    },
  );
  if (response.status !== 200 && response.status !== 201) {
    throw await readApiError(response);
  }
  return (await response.json()) as SalaoLancamentoPedido;
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
      credentials: "include",
    },
  );
  if (response.status !== 200) throw await readApiError(response);
  return (await response.json()) as SalaoComandaMutation;
}
