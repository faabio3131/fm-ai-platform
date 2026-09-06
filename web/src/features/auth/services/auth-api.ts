"use client";

import { API_BASE_URL } from "@/lib/api";

export interface AuthOperator {
  usuario_id: string;
  nome: string | null;
  email: string;
  tenant_id: string;
  unidade_ativa_id: string;
  papeis: string[];
  permissoes?: string[];
}

export interface AuthUnit {
  id: string;
  codigo: string | null;
  nome: string | null;
}

export interface LogoutResult {
  ok: boolean;
}

export class AuthApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "AuthApiError";
  }
}

async function readApiError(response: Response): Promise<AuthApiError> {
  let code: string | undefined;

  try {
    const body = (await response.json()) as { erro?: unknown };
    if (typeof body.erro === "string") {
      code = body.erro;
    }
  } catch {
    code = undefined;
  }

  return new AuthApiError(
    `Auth API respondeu HTTP ${response.status}${code ? ` (${code})` : ""}`,
    response.status,
    code,
  );
}

async function authRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");

  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw await readApiError(response);
  }

  return (await response.json()) as T;
}

export async function login(email: string, senha: string): Promise<AuthOperator> {
  return authRequest<AuthOperator>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, senha }),
  });
}

export async function getMe(): Promise<AuthOperator> {
  return authRequest<AuthOperator>("/v1/auth/me", { method: "GET" });
}

export async function getUnits(): Promise<AuthUnit[]> {
  return authRequest<AuthUnit[]>("/v1/auth/unidades", { method: "GET" });
}

export async function selectUnit(unidadeId: string): Promise<{ unidade_ativa_id: string }> {
  return authRequest<{ unidade_ativa_id: string }>("/v1/auth/select-unit", {
    method: "POST",
    body: JSON.stringify({ unidade_id: unidadeId }),
  });
}

export async function logout(): Promise<LogoutResult> {
  return authRequest<LogoutResult>("/v1/auth/logout", { method: "POST" });
}
