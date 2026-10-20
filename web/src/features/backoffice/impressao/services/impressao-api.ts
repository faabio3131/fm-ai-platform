import { API_BASE_URL } from "@/lib/api";

export type StatusImpressao = "pendente" | "falhou" | "impresso" | "contingencia";

export interface JobImpressao {
  job_id: string;
  tenant_id: string;
  unidade_id: string;
  setor_id: string;
  producao_id: string;
  pedido_id: string;
  pedido_item_id: string;
  impressora_id: string;
  dedup_key: string;
  documento_hash: string;
  conteudo: string;
  status: StatusImpressao;
  tentativa: number;
  max_tentativas: number;
  versao: number;
  criado_em: string;
  atualizado_em: string;
  ultimo_erro: string | null;
  reimpressao_de: string | null;
  motivo_reimpressao: string | null;
}

export interface JobsResponse {
  jobs: JobImpressao[];
}

export interface ProcessarResponse {
  job: JobImpressao;
  impresso: boolean;
  contingencia: boolean;
}

export interface ReimprimirPayload {
  motivo: string;
  idempotency_key: string;
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  await fetch(`${API_BASE_URL}/v1/admin/acesso`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
  });
  const response = await fetch(`${API_BASE_URL}/v1/admin${path}`, {
    method,
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ erro: "erro_desconhecido" }));
    throw new Error(error.erro || `HTTP ${response.status}`);
  }
  return await response.json() as T;
}

export async function listarJobs(): Promise<JobImpressao[]> {
  const response = await request<JobsResponse>("/impressao/jobs");
  return response.jobs;
}

export async function processarJob(jobId: string): Promise<ProcessarResponse> {
  return request<ProcessarResponse>(`/impressao/jobs/${encodeURIComponent(jobId)}/processar`, "POST");
}

export async function reimprimirJob(jobId: string, payload: ReimprimirPayload): Promise<JobImpressao> {
  return request<JobImpressao>(`/impressao/jobs/${encodeURIComponent(jobId)}/reimprimir`, "POST", payload);
}