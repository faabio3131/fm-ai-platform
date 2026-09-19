import { API_BASE_URL } from "@/lib/api";

export interface DestinatarioNotificacao {
  destinatario_id: string;
  tenant_id: string;
  unidade_id: string;
  nome_exibicao: string;
  cargo: string | null;
  canal: "whatsapp";
  contato_mascara: string;
  receber_alertas_estoque: boolean;
  ativo: boolean;
  versao: number;
}

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/v1/admin/notificacoes${path}`, {
    method,
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(
      response.status === 403
        ? "Confirmação administrativa ou permissão necessária."
        : "Não foi possível atualizar as notificações internas.",
    );
  }
  return await response.json() as T;
}

export async function listarDestinatarios(): Promise<DestinatarioNotificacao[]> {
  const result = await request<{ destinatarios: DestinatarioNotificacao[] }>("");
  return result.destinatarios;
}

export function configurarDestinatario(input: {
  destinatario_id: string;
  nome_exibicao: string;
  cargo: string | null;
  contato: string;
  receber_alertas_estoque: boolean;
  ativo: boolean;
}): Promise<DestinatarioNotificacao> {
  return request(`/${encodeURIComponent(input.destinatario_id)}`, "PUT", input);
}

export function atualizarPreferencias(
  destinatarioId: string,
  input: { receber_alertas_estoque: boolean; ativo: boolean },
): Promise<DestinatarioNotificacao> {
  return request(
    `/${encodeURIComponent(destinatarioId)}/preferencias`,
    "PATCH",
    input,
  );
}
