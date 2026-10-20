import { API_BASE_URL } from "@/lib/api";

export interface TransacaoPagamentoWeb {
  transacao_id: string;
  tipo: string;
  status: string;
  valor: string;
  metodo: string;
  provedor: string | null;
  id_externo: string | null;
  occurred_at: string;
  correlation_id: string;
  erro_normalizado: string | null;
}

export interface PagamentoWeb {
  pagamento_id: string;
  pedido_id: string;
  status: string;
  metodo: string;
  valor_previsto: string;
  valor_pago: string;
  valor_estornado: string;
  saldo: string;
  moeda: string;
  provedor: string | null;
  versao: number;
  atualizado_em: string;
  transacoes: TransacaoPagamentoWeb[];
}

async function request(path: string, init?: RequestInit): Promise<PagamentoWeb> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof body.erro === "string" ? body.erro : "pagamentos.indisponivel");
  }
  return body as PagamentoWeb;
}

export function obterPagamento(pagamentoId: string): Promise<PagamentoWeb> {
  return request(`/v1/pagamentos/${encodeURIComponent(pagamentoId)}`);
}

export function reconciliarPagBank(pagamentoId: string): Promise<PagamentoWeb> {
  return request(`/v1/pagamentos/${encodeURIComponent(pagamentoId)}/reconciliar-pagbank`, {
    method: "POST",
  });
}
