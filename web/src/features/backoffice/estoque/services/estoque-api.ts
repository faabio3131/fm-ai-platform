import { API_BASE_URL } from "@/lib/api";

export interface EstoqueInsumo {
  id: string;
  nome: string;
  unidade_medida: string;
  saldo_atual: number;
  estoque_minimo: number;
  custo_unitario: number;
  valor_total: number;
  data_fabricacao: string | null;
  data_validade: string | null;
  dias_alerta_vencimento: number;
  status_estoque: "ok" | "reposicao";
  status_validade: string;
}

export interface EstoqueResumo {
  itens: EstoqueInsumo[];
  valor_total: number;
}

export interface CriarInsumoPayload {
  nome: string;
  unidade_medida: string;
  saldo_atual: number;
  estoque_minimo: number;
  custo_unitario: number;
  data_fabricacao: string | null;
  data_validade: string | null;
  dias_alerta_vencimento: number;
}

export interface LeituraEstoqueItem {
  nome: string;
  quantidade: number;
  unidade: string;
  data_validade: string | null;
}

export class EstoqueApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "EstoqueApiError";
  }
}

async function apiError(response: Response): Promise<EstoqueApiError> {
  let code: string | undefined;
  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") code = body.erro;
  } catch {
    code = undefined;
  }
  return new EstoqueApiError(
    `Estoque API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
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

export function listarEstoque(): Promise<EstoqueResumo> {
  return request("/v1/estoque/insumos", { method: "GET" });
}

export function criarInsumo(payload: CriarInsumoPayload): Promise<EstoqueInsumo> {
  return request("/v1/estoque/insumos", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function excluirInsumo(insumoId: string): Promise<{ ok: boolean }> {
  return request(`/v1/estoque/insumos/${encodeURIComponent(insumoId)}`, {
    method: "DELETE",
  });
}

export function aplicarLeituraEstoque(
  itens: LeituraEstoqueItem[],
): Promise<{ processados: number; itens: EstoqueInsumo[] }> {
  return request("/v1/estoque/leituras", {
    method: "POST",
    body: JSON.stringify({ itens }),
  });
}
