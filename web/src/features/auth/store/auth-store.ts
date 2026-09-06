"use client";

import { useSyncExternalStore } from "react";

import {
  AuthApiError,
  getMe,
  logout,
  type AuthOperator,
} from "@/features/auth/services/auth-api";

export type AuthStatus =
  | "idle"
  | "loading"
  | "authenticated"
  | "unauthenticated"
  | "error";

export interface AuthState {
  status: AuthStatus;
  operator: AuthOperator | null;
  tenantId: string | null;
  unitId: string | null;
  permissions: string[];
}

const initialState: AuthState = {
  status: "idle",
  operator: null,
  tenantId: null,
  unitId: null,
  permissions: [],
};

let state: AuthState = initialState;
let hydrationPromise: Promise<AuthOperator | null> | null = null;
const listeners = new Set<() => void>();

function emit(nextState: AuthState): void {
  state = nextState;
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): AuthState {
  return state;
}

function getServerSnapshot(): AuthState {
  return initialState;
}

export function setAuthenticated(operator: AuthOperator): void {
  emit({
    status: "authenticated",
    operator,
    tenantId: operator.tenant_id,
    unitId: operator.unidade_ativa_id,
    permissions: [...(operator.permissoes ?? [])],
  });
}

export function clearAuthState(): void {
  emit({ ...initialState, status: "unauthenticated" });
}

export async function refreshAuthSession(): Promise<AuthOperator | null> {
  if (hydrationPromise) {
    return hydrationPromise;
  }

  emit({ ...state, status: "loading" });

  hydrationPromise = getMe()
    .then((operator) => {
      setAuthenticated(operator);
      return operator;
    })
    .catch((error: unknown) => {
      if (error instanceof AuthApiError && error.status === 401) {
        clearAuthState();
        return null;
      }

      emit({ ...initialState, status: "error" });
      throw error;
    })
    .finally(() => {
      hydrationPromise = null;
    });

  return hydrationPromise;
}

export async function endAuthSession(): Promise<void> {
  try {
    await logout();
  } finally {
    clearAuthState();
  }
}

export function useAuthStore(): AuthState {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
