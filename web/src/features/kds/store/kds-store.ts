"use client";

import { useMemo, useSyncExternalStore } from "react";

import type {
  KdsQueueResponse,
  KdsSector,
  KdsTicket,
  KdsTransitionResponse,
} from "@/features/kds/services/kds-api";

export interface KdsState {
  setores: KdsSector[];
  tickets: KdsTicket[];
  setorId: string | null;
  atualizadoEm: string | null;
  degradado: boolean;
  somenteLeitura: boolean;
  motivoDegradacao: string | null;
}

const initialState: KdsState = {
  setores: [],
  tickets: [],
  setorId: null,
  atualizadoEm: null,
  degradado: false,
  somenteLeitura: false,
  motivoDegradacao: null,
};

let state: KdsState = initialState;
const listeners = new Set<() => void>();

function emit(nextState: KdsState): void {
  state = nextState;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): KdsState {
  return state;
}

function sortTickets(tickets: KdsTicket[]): KdsTicket[] {
  return [...tickets].sort((a, b) => {
    if (a.prioridade !== b.prioridade) return b.prioridade - a.prioridade;
    return new Date(a.criado_em).getTime() - new Date(b.criado_em).getTime();
  });
}

export const kdsActions = {
  setSectors(setores: KdsSector[]): void {
    emit({
      ...state,
      setores: [...setores].sort((a, b) => a.ordem - b.ordem),
    });
  },

  setQueue(queue: KdsQueueResponse): void {
    emit({
      ...state,
      tickets: sortTickets(queue.tickets),
      atualizadoEm: queue.atualizado_em,
      degradado: queue.degradado,
      somenteLeitura: queue.somente_leitura,
      motivoDegradacao: queue.motivo_degradacao,
    });
  },

  setSector(setorId: string | null): void {
    emit({ ...state, setorId });
  },

  applyTransition(result: KdsTransitionResponse): void {
    emit({
      ...state,
      tickets: sortTickets(
        state.tickets.map((ticket) =>
          ticket.producao_id === result.producao_id
            ? {
                ...ticket,
                status: result.status,
                versao: result.versao,
                atualizado_em: result.atualizado_em,
              }
            : ticket,
        ),
      ),
    });
  },

  reset(): void {
    emit({ ...initialState });
  },
};

export function useKdsStore(): KdsState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

export function useVisibleKdsTickets(): KdsTicket[] {
  const current = useKdsStore();
  return useMemo(
    () =>
      current.setorId
        ? current.tickets.filter((ticket) => ticket.setor_id === current.setorId)
        : current.tickets,
    [current.setorId, current.tickets],
  );
}
