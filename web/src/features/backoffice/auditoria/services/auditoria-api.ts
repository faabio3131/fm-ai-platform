import { ApiError, apiRequest } from "@/lib/api";

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
  try {
    return await apiRequest<AuditoriaPage>(
      `/v1/admin/auditoria?${params.toString()}`,
      {
        credentials: "include",
        headers: { Accept: "application/json" },
      },
    );
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 403 && error.code === "seguranca.admin_step_up_exigido") {
        throw new Error("Sua confirmação administrativa expirou.");
      }
      if (error.status === 403) {
        throw new Error("Sua conta não possui permissão para visualizar a auditoria.");
      }
      if (error.status === 401) {
        throw new Error("Sua sessão expirou. Entre novamente.");
      }
    }
    throw new Error("Não foi possível carregar a auditoria.");
  }
}
