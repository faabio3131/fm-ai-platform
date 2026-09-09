import { API_BASE_URL } from "@/lib/api";

export interface Empresa {
  tenant_id: string;
  nome_exibicao: string;
  moeda: string;
  timezone: string;
  ativa: boolean;
  versao: number;
}

export interface Unidade {
  unidade_id: string;
  codigo: string;
  nome_fantasia: string;
  tipo: string;
  documento_fiscal: string;
  telefone: string;
  email: string;
  endereco: string;
  horarios: string;
  ativa: boolean;
  versao: number;
}

export interface CadastroEmpresa {
  empresa: Empresa;
  unidades: Unidade[];
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/v1/admin${path}`, {
    method, credentials: "include", cache: "no-store",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const messages: Record<number, string> = {
      400: "Cadastro inválido ou unidade já cadastrada. Confira os campos.",
      401: "Sua sessão expirou. Entre novamente.",
      403: "Acesso não autorizado ou confirmação administrativa expirada. Reabra a área administrativa.",
      409: "O cadastro foi alterado por outra operação. Recarregue antes de salvar.",
      422: "Confira os campos do cadastro.",
    };
    throw new Error(messages[response.status] ?? "Não foi possível concluir a operação administrativa.");
  }
  return await response.json() as T;
}

export async function abrirCadastroEmpresa(): Promise<CadastroEmpresa> {
  await request("/acesso", "POST");
  return request<CadastroEmpresa>("/empresa");
}

export function salvarEmpresa(empresa: Omit<Empresa, "tenant_id">): Promise<Empresa> {
  return request("/empresa", "PUT", empresa);
}

export function salvarUnidade(unidadeId: string, unidade: Omit<Unidade, "unidade_id">): Promise<Unidade> {
  return request(`/unidades/${encodeURIComponent(unidadeId)}`, "PUT", unidade);
}

export function criarUnidade(unidade: Pick<Unidade, "unidade_id" | "codigo" | "nome_fantasia" | "tipo" | "endereco" | "horarios">): Promise<Unidade> {
  return request("/unidades", "POST", unidade);
}
