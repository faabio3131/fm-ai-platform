import { API_BASE_URL } from "@/lib/api";

export type GerenteIAValor = unknown;

export interface GerenteIAResponse {
  tipo: string;
  resultado: GerenteIAValor;
  nome_assistente?: string;
  chamada?: GerenteIAValor;
}

interface ErroApi {
  erro?: string;
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  const payload = (await response.json().catch(() => ({}))) as T & ErroApi;
  if (!response.ok) {
    throw new Error(payload.erro ?? `http_${response.status}`);
  }
  return payload;
}

export function perguntarGerenteIA(pergunta: string): Promise<GerenteIAResponse> {
  return request<GerenteIAResponse>("/v1/gerente-ia/perguntar", {
    method: "POST",
    body: JSON.stringify({ pergunta }),
  });
}

export function executarToolGerenteIA(
  tool: string,
  argumentos: Record<string, string | number | boolean | null>,
): Promise<GerenteIAResponse> {
  return request<GerenteIAResponse>("/v1/gerente-ia/tools", {
    method: "POST",
    body: JSON.stringify({ tool, argumentos }),
  });
}

export function confirmarGerenteIA(input: {
  preview_id: string;
  fingerprint: string;
  idempotency_key: string;
}): Promise<GerenteIAResponse> {
  return request<GerenteIAResponse>("/v1/gerente-ia/confirmar", {
    method: "POST",
    body: JSON.stringify(input),
  });
}


export async function transcreverGerenteIA(audio: Blob): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/v1/gerente-ia/transcrever`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      "Content-Type": audio.type || "audio/webm",
    },
    body: audio,
  });
  const payload = (await response.json().catch(() => ({}))) as {
    transcricao?: string;
    erro?: string;
  };
  if (!response.ok) {
    throw new Error(payload.erro ?? `http_${response.status}`);
  }
  const texto = payload.transcricao?.trim();
  if (!texto) {
    throw new Error("gerente_ia.transcricao_vazia");
  }
  return texto;
}
