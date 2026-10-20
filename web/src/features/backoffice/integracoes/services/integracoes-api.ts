import { apiRequest } from '@/lib/api';

export interface CatalogoItem {
  servico: string;
  provedor: string;
  label: string;
  parametros_obrigatorios: string[];
  credenciais_obrigatorias: string[];
  healthcheck_supported: boolean;
}

export interface CredencialEstado {
  [papel: string]: boolean;
}

export interface Prontidao {
  estado: 'desativado' | 'bloqueado' | 'configurado' | 'pronto';
  pronto: boolean;
  faltam_parametros: string[];
  faltam_finalidades: string[];
  faltam_credenciais: string[];
}

export interface ConfiguracaoSalva {
  configuracao_id: string;
  servico: string;
  provedor: string;
  conta_externa: string;
  ambiente: 'sandbox' | 'homologacao' | 'producao';
  parametros: Record<string, string | number | boolean | null>;
  credenciais_estado: CredencialEstado;
  habilitada: boolean;
  homologada: boolean;
  evidencia_homologacao_ref: string | null;
  versao: number;
  prontidao: Prontidao;
}

export interface Integracao {
  catalogo: CatalogoItem;
  configuracao: ConfiguracaoSalva | null;
}

export interface IntegracoesListResponse {
  integracoes: Integracao[];
}

export interface ParametroIn {
  nome: string;
  valor: string | number | boolean | null;
}

export interface CredencialIn {
  papel: string;
  valor: string;
}

export interface IntegracoesPutRequest {
  servico: string;
  provedor: string;
  conta_externa?: string;
  ambiente: 'sandbox' | 'homologacao' | 'producao';
  parametros: ParametroIn[];
  credenciais: CredencialIn[];
  habilitada: boolean;
  versao: number;
}

export interface HealthcheckResponse {
  executado: boolean;
  suportado: boolean;
  provedor: string;
  evidencia_ref: string | null;
  detalhes: Record<string, unknown> | null;
  erro: string | null;
}

export interface HomologarRequest {
  evidencia_ref: string;
}

export async function listarIntegracoes(): Promise<IntegracoesListResponse> {
  return apiRequest<IntegracoesListResponse>('/v1/admin/integracoes');
}

export async function salvarIntegracao(
  configId: string,
  payload: IntegracoesPutRequest
): Promise<ConfiguracaoSalva> {
  return apiRequest<ConfiguracaoSalva>(`/v1/admin/integracoes/${configId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function executarHealthcheck(configId: string): Promise<HealthcheckResponse> {
  return apiRequest<HealthcheckResponse>(`/v1/admin/integracoes/${configId}/healthcheck`, {
    method: 'POST',
  });
}

export async function homologarIntegracao(
  configId: string,
  evidenciaRef: string
): Promise<ConfiguracaoSalva> {
  return apiRequest<ConfiguracaoSalva>(`/v1/admin/integracoes/${configId}/homologar`, {
    method: 'POST',
    body: JSON.stringify({ evidencia_ref: evidenciaRef }),
  });
}