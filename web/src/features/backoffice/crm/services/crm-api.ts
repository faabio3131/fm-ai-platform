import { API_BASE_URL } from "@/lib/api";

export interface CrmCliente {
  cliente_id: string;
  origem: string;
  canais: string[];
  criado_em: string;
  versao: number;
  saldo_cashback: string;
  legacy_cliente_id: number | null;
  nome: string | null;
  whatsapp: string | null;
  ultima_compra: string | null;
  total_gasto: string | null;
  status: string | null;
}

export interface CrmClientesResumo {
  itens: CrmCliente[];
  saldo_total: string;
}

export interface CashbackMovimento {
  movimento_id: string;
  tipo: "credito" | "debito";
  valor: string;
  origem: string;
  referencia: string;
  ocorrido_em: string;
}

export interface CashbackDetalhe {
  cliente_id: string;
  saldo: string;
  movimentos: CashbackMovimento[];
}

export interface ResgateClienteInativo {
  legacy_cliente_id: number;
  cliente_id: string;
  nome: string;
  whatsapp: string;
  ultima_compra: string | null;
  total_gasto: number;
  status: string;
  mensagem_sugerida: string;
}

export interface ResgatesClientesInativos {
  itens: ResgateClienteInativo[];
}

export interface ResultadoDespachoResgate {
  cliente_id: string;
  enviado: boolean;
  motivo: string;
  mensagem_id: string | null;
}

export class CrmApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "CrmApiError";
  }
}

async function apiError(response: Response): Promise<CrmApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }
  return new CrmApiError(
    `CRM API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as T;
}

export function listarClientesCrm(): Promise<CrmClientesResumo> {
  return request("/v1/crm/clientes");
}

export function consultarCashback(clienteId: string): Promise<CashbackDetalhe> {
  return request(`/v1/crm/clientes/${encodeURIComponent(clienteId)}/cashback`);
}

export function creditarCashback(
  clienteId: string,
  valor: string,
  idempotencyKey: string,
): Promise<{ cliente_id: string; legacy_cliente_id: number; saldo: string }> {
  return request(
    `/v1/crm/clientes/${encodeURIComponent(clienteId)}/cashback/creditos`,
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ valor }),
    },
  );
}

export function listarResgatesInativos(): Promise<ResgatesClientesInativos> {
  return request("/v1/crm/resgates/inativos");
}

export function despacharResgate(
  legacyClienteId: number,
  texto: string,
): Promise<ResultadoDespachoResgate> {
  return request(`/v1/crm/resgates/${legacyClienteId}/despachar`, {
    method: "POST",
    body: JSON.stringify({ texto }),
  });
}
