import { API_BASE_URL } from "@/lib/api";

export interface CatalogoProduto {
  id: string;
  nome: string;
  categoria: string;
  preco: number;
  ativo: boolean;
}

export interface CriarProdutoPayload {
  nome: string;
  categoria: string;
  preco: number;
  ativo: boolean;
}

export interface AtualizarProdutoPayload {
  preco?: number;
  ativo?: boolean;
}

export interface CatalogoInsumoFicha {
  id: string;
  nome: string;
  unidade_medida: string;
  custo_unitario: number;
  data_validade: string | null;
}

export interface CatalogoFichaItem {
  id: string;
  insumo_id: string;
  insumo_nome: string;
  quantidade: number;
  unidade_medida: string;
  custo_unitario: number;
  custo_item: number;
}

export interface CatalogoFicha {
  produto: CatalogoProduto;
  custo_total_cmv: number;
  margem_exibicao: string;
  descricao_bruta: string;
  itens: CatalogoFichaItem[];
}

export interface CriarPratoComFichaPayload {
  nome: string;
  categoria: string;
  preco: number;
  custo_total_cmv: number;
  margem_exibicao: string;
  descricao_bruta: string;
  ativo: boolean;
  itens_ficha: Array<{ insumo_id: number; quantidade: number }>;
}

export class CatalogoApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "CatalogoApiError";
  }
}

async function readApiError(response: Response): Promise<CatalogoApiError> {
  let code: string | undefined;

  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") {
      code = body.erro;
    }
  } catch {
    code = undefined;
  }

  return new CatalogoApiError(
    `Catálogo API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

async function catalogoRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw await readApiError(response);
  }

  return (await response.json()) as T;
}

export async function listarProdutos(
  categoria?: string,
  apenasAtivos?: boolean,
): Promise<CatalogoProduto[]> {
  const searchParams = new URLSearchParams();
  const categoriaNormalizada = categoria?.trim();

  if (categoriaNormalizada) {
    searchParams.set("categoria", categoriaNormalizada);
  }

  if (typeof apenasAtivos === "boolean") {
    searchParams.set("apenas_ativos", String(apenasAtivos));
  }

  const query = searchParams.toString();
  return catalogoRequest<CatalogoProduto[]>(
    `/v1/catalogo/produtos${query ? `?${query}` : ""}`,
    { method: "GET" },
  );
}

export async function listarCategorias(): Promise<string[]> {
  return catalogoRequest<string[]>("/v1/catalogo/categorias", {
    method: "GET",
  });
}

export async function criarProduto(
  payload: CriarProdutoPayload,
): Promise<CatalogoProduto> {
  return catalogoRequest<CatalogoProduto>("/v1/catalogo/produtos", {
    method: "POST",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(payload),
  });
}

export async function atualizarProduto(
  id: string,
  payload: AtualizarProdutoPayload,
): Promise<CatalogoProduto> {
  return catalogoRequest<CatalogoProduto>(
    `/v1/catalogo/produtos/${encodeURIComponent(id)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function listarInsumosFicha(): Promise<CatalogoInsumoFicha[]> {
  return catalogoRequest("/v1/catalogo/insumos-ficha", { method: "GET" });
}

export function obterFichaProduto(produtoId: string): Promise<CatalogoFicha> {
  return catalogoRequest(
    `/v1/catalogo/produtos/${encodeURIComponent(produtoId)}/ficha`,
    { method: "GET" },
  );
}

export function criarPratoComFicha(
  payload: CriarPratoComFichaPayload,
): Promise<CatalogoProduto> {
  return catalogoRequest("/v1/catalogo/pratos-com-ficha", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify(payload),
  });
}
