import { apiRequest } from '@/lib/api';

export interface IdentidadeAssistente {
  tenant_id: string;
  unidade_id: string;
  nome_publico: string;
  atributos: Record<string, unknown>;
  versao: number;
  atualizado_em: string | null;
}

export interface IdentidadeAssistentePutRequest {
  nome_publico: string;
  atributos: Record<string, unknown>;
  versao_esperada?: number;
}

export interface ConversaResumo {
  conversa_id: string;
  estado: string;
  pedido_id: string | null;
  pagamento_id: string | null;
  entrega_id: string | null;
  versao: number;
  atualizado_em: string;
}

export interface ConversasListResponse {
  conversas: ConversaResumo[];
}

export interface ConversaDetalhe {
  conversa_id: string;
  estado: string;
  pedido_id: string | null;
  pagamento_id: string | null;
  entrega_id: string | null;
  ultimo_inbound_id: string | null;
  ultimo_outbound_id: string | null;
  versao: number;
  handoff_contexto: Record<string, unknown> | null;
}

export interface HandoffRequest {
  motivo: string;
}

export interface HandoffResponse {
  status: string;
  conversa_id: string;
  motivo: string;
}

export async function obterIdentidade(): Promise<IdentidadeAssistente> {
  return apiRequest<IdentidadeAssistente>('/v1/admin/assistente-atendimento/identidade');
}

export async function configurarIdentidade(
  payload: IdentidadeAssistentePutRequest
): Promise<IdentidadeAssistente> {
  return apiRequest<IdentidadeAssistente>('/v1/admin/assistente-atendimento/identidade', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function listarConversas(): Promise<ConversasListResponse> {
  return apiRequest<ConversasListResponse>('/v1/admin/assistente-atendimento/conversas');
}

export async function obterConversa(conversaId: string): Promise<ConversaDetalhe> {
  return apiRequest<ConversaDetalhe>(`/v1/admin/assistente-atendimento/conversas/${conversaId}`);
}

export async function forcarHandoff(
  conversaId: string,
  motivo: string
): Promise<HandoffResponse> {
  return apiRequest<HandoffResponse>(`/v1/admin/assistente-atendimento/conversas/${conversaId}/handoff`, {
    method: 'POST',
    body: JSON.stringify({ motivo }),
  });
}