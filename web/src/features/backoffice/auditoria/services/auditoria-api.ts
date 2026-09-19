import { API_BASE_URL } from "@/lib/api";

export interface EventoAuditoria {
  audit_id: string;
  tenant_id: string;
  unidade_id: string;
  usuario_id: string;
  papel_efetivo: string | null;
  acao: string;
  recurso_tipo: string;
  recurso_id: string | null;
  resultado: string;
  motivo: string;
  correlation_id: string;
  timestamp: string;
  origem: string;
  politica: string;
  versao: number;
  causation_id: string | null;
}

export interface AuditoriaPage {
  eventos: EventoAuditoria[];
  pagina: number;
  tamanho: number;
  tem_mais: boolean;
}

export async function listarAuditoria(
  pagina: number,
  filtros: {
    acao?: string;
    resultado?: string;
    usuario_id?: string;
    recurso_tipo?: string;
  } = {},
): Promise<AuditoriaPage> {
  const params = new URLSearchParams({
    pagina: String(pagina),
    tamanho: "50",
  });
  for (const [key, value] of Object.entries(filtros)) {
    if (value?.trim()) {
      params.set(key, value.trim());
    }
  }
  const response = await fetch(
    `${API_BASE_URL}/v1/admin/auditoria?${params.toString()}`,
    {
      credentials: "include",
      cache: "no-store",
      headers: { Accept: "application/json" },
    },
  );
  if (!response.ok) {
    throw new Error(
      response.status === 403
        ? "Confirmação administrativa ou permissão de auditoria necessária."
        : "Não foi possível carregar a auditoria.",
    );
  }
  return await response.json() as AuditoriaPage;
}
