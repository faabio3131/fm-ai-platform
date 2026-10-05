import { API_BASE_URL } from "@/lib/api";

export interface CampanhaWeb {
  campanha_id: string;
  canal: string;
  finalidade: string;
  objetivo: string;
  texto_base: string;
  audiencia_elegivel: number;
  criado_em: string;
  criado_por: string;
  status: "rascunho" | "aguardando_aprovacao" | "aprovada" | "publicavel" | string;
  fingerprint: string;
  campanha_ref: string | null;
  midia_url: string | null;
}

export interface AudienciaCampanha {
  cliente_id: string;
  nome: string;
  canal_disponivel: boolean;
  consentimento: string;
  selecionado: boolean;
  elegivel: boolean;
}

export interface EventoCampanha {
  event_id: string;
  event_type: string;
  ocorrido_em: string;
  payload: Record<string, unknown>;
}

export interface CampanhaConteudo {
  canal: string;
  finalidade: string;
  objetivo: string;
  texto_base: string;
  midia_url?: string | null;
}

export interface DespachoCampanha {
  campanha_id: string;
  canal: string;
  total: number;
  enviados: number;
  resultados: Array<{
    cliente_id: string | null;
    canal: string;
    enviado: boolean;
    motivo: string;
    mensagem_id: string | null;
    publicacao_id: string | null;
  }>;
}

export class CampanhasApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  idempotencyKey?: string,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
      ...(init.headers ?? {}),
    },
  });
  const payload = (await response.json().catch(() => ({}))) as T & {
    erro?: string;
  };
  if (!response.ok) {
    throw new CampanhasApiError(
      response.status,
      payload.erro ?? `http_${response.status}`,
    );
  }
  return payload;
}

export async function listarCampanhas(): Promise<CampanhaWeb[]> {
  const result = await request<{ itens: CampanhaWeb[] }>("/v1/campanhas");
  return result.itens;
}

export function obterCampanha(id: string): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(`/v1/campanhas/${encodeURIComponent(id)}`);
}

export function criarCampanha(
  conteudo: CampanhaConteudo,
  idempotencyKey: string,
): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(
    "/v1/campanhas",
    { method: "POST", body: JSON.stringify(conteudo) },
    idempotencyKey,
  );
}

export function atualizarCampanha(
  id: string,
  conteudo: CampanhaConteudo,
  idempotencyKey: string,
): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(
    `/v1/campanhas/${encodeURIComponent(id)}`,
    { method: "PATCH", body: JSON.stringify(conteudo) },
    idempotencyKey,
  );
}

export async function listarAudiencia(id: string): Promise<AudienciaCampanha[]> {
  const result = await request<{ itens: AudienciaCampanha[] }>(
    `/v1/campanhas/${encodeURIComponent(id)}/audiencia`,
  );
  return result.itens;
}

export function definirAudiencia(
  id: string,
  clienteIds: string[],
  idempotencyKey: string,
): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(
    `/v1/campanhas/${encodeURIComponent(id)}/audiencia`,
    { method: "PUT", body: JSON.stringify({ cliente_ids: clienteIds }) },
    idempotencyKey,
  );
}

export function submeterCampanha(
  id: string,
  idempotencyKey: string,
): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(
    `/v1/campanhas/${encodeURIComponent(id)}/submeter`,
    { method: "POST" },
    idempotencyKey,
  );
}

export function aprovarCampanha(
  id: string,
  fingerprint: string,
  idempotencyKey: string,
): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(
    `/v1/campanhas/${encodeURIComponent(id)}/aprovar`,
    { method: "POST", body: JSON.stringify({ fingerprint }) },
    idempotencyKey,
  );
}

export function publicarCampanha(
  id: string,
  fingerprint: string,
  idempotencyKey: string,
): Promise<CampanhaWeb> {
  return request<CampanhaWeb>(
    `/v1/campanhas/${encodeURIComponent(id)}/publicar`,
    { method: "POST", body: JSON.stringify({ fingerprint }) },
    idempotencyKey,
  );
}

export function despacharCampanha(
  id: string,
  fingerprint: string,
  idempotencyKey: string,
): Promise<DespachoCampanha> {
  return request<DespachoCampanha>(
    `/v1/campanhas/${encodeURIComponent(id)}/despachar`,
    { method: "POST", body: JSON.stringify({ fingerprint }) },
    idempotencyKey,
  );
}

export async function listarHistorico(id: string): Promise<EventoCampanha[]> {
  const result = await request<{ itens: EventoCampanha[] }>(
    `/v1/campanhas/${encodeURIComponent(id)}/historico`,
  );
  return result.itens;
}
