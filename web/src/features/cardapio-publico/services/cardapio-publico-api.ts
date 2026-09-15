import { API_BASE_URL } from "@/lib/api";

export interface ItemCardapioPublico {
  produto_id: string;
  nome: string;
  preco: string;
  estoque_disponivel: string;
  versao: number;
}

export interface CardapioPublico {
  public_id: string;
  slug: string;
  empresa: string;
  unidade: string;
  tipo_unidade: string;
  itens: ItemCardapioPublico[];
}

export interface PublicacaoCardapio {
  unidade_id: string;
  public_id: string | null;
  slug: string | null;
  publicada: boolean;
  url_publica: string | null;
  versao: number;
}

async function lerErro(response: Response, fallback: string): Promise<never> {
  let mensagem = fallback;
  try {
    const data = await response.json() as { erro?: string };
    if (data.erro) mensagem = data.erro;
  } catch {
    // resposta sem JSON: mantém mensagem segura de fallback
  }
  throw new Error(mensagem);
}

export async function carregarCardapioPublico(publicId: string): Promise<CardapioPublico> {
  const response = await fetch(`${API_BASE_URL}/v1/publico/cardapio/${encodeURIComponent(publicId)}`, {
    method: "GET",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) return lerErro(response, "Cardápio indisponível no momento.");
  return await response.json() as CardapioPublico;
}

export async function obterPublicacaoCardapio(unidadeId: string): Promise<PublicacaoCardapio> {
  const response = await fetch(`${API_BASE_URL}/v1/admin/cardapio-publico/${encodeURIComponent(unidadeId)}`, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) return lerErro(response, "Não foi possível carregar o link público.");
  return await response.json() as PublicacaoCardapio;
}

export async function salvarPublicacaoCardapio(
  unidadeId: string,
  payload: { slug: string; publicada: boolean; versao: number },
): Promise<PublicacaoCardapio> {
  const response = await fetch(`${API_BASE_URL}/v1/admin/cardapio-publico/${encodeURIComponent(unidadeId)}`, {
    method: "PUT",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) return lerErro(response, "Não foi possível atualizar a publicação do cardápio.");
  return await response.json() as PublicacaoCardapio;
}
