"use client";

import { useMemo, useSyncExternalStore } from "react";

import type { CatalogItem, PaymentMethod } from "@/features/pdv/services/pdv-api";

export interface CartItem {
  produto_id: string;
  nome: string;
  preco: string;
  quantidade: number;
  observacoes: string;
}

export interface CartState {
  itens: CartItem[];
  metodoPagamento: PaymentMethod;
  desconto: string;
  clienteId: string;
}

const initialState: CartState = {
  itens: [],
  metodoPagamento: "dinheiro",
  desconto: "0.00",
  clienteId: "",
};

let state: CartState = initialState;
const listeners = new Set<() => void>();

function emit(nextState: CartState): void {
  state = nextState;
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): CartState {
  return state;
}

function sanitizeMoneyInput(value: string): string {
  const normalized = value.replace(",", ".").replace(/[^0-9.]/g, "");
  const [integer = "0", ...decimalParts] = normalized.split(".");
  const decimals = decimalParts.join("").slice(0, 2);
  return decimals.length > 0 ? `${integer || "0"}.${decimals}` : integer || "0";
}

export function moneyToCents(value: string): number {
  const parsed = Number.parseFloat(value.replace(",", "."));
  if (!Number.isFinite(parsed)) return 0;
  return Math.max(0, Math.round(parsed * 100));
}

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
});

export function formatCurrency(cents: number): string {
  return currencyFormatter.format(cents / 100);
}

function removeItem(produtoId: string): void {
  emit({
    ...state,
    itens: state.itens.filter((item) => item.produto_id !== produtoId),
  });
}

export const cartActions = {
  addItem(product: CatalogItem): void {
    const existing = state.itens.find((item) => item.produto_id === product.id);
    if (existing) {
      emit({
        ...state,
        itens: state.itens.map((item) =>
          item.produto_id === product.id
            ? { ...item, quantidade: item.quantidade + 1 }
            : item,
        ),
      });
      return;
    }

    emit({
      ...state,
      itens: [
        ...state.itens,
        {
          produto_id: product.id,
          nome: product.nome,
          preco: product.preco,
          quantidade: 1,
          observacoes: "",
        },
      ],
    });
  },

  increment(produtoId: string): void {
    emit({
      ...state,
      itens: state.itens.map((item) =>
        item.produto_id === produtoId
          ? { ...item, quantidade: item.quantidade + 1 }
          : item,
      ),
    });
  },

  decrement(produtoId: string): void {
    const target = state.itens.find((item) => item.produto_id === produtoId);
    if (!target) return;

    if (target.quantidade <= 1) {
      removeItem(produtoId);
      return;
    }

    emit({
      ...state,
      itens: state.itens.map((item) =>
        item.produto_id === produtoId
          ? { ...item, quantidade: item.quantidade - 1 }
          : item,
      ),
    });
  },

  removeItem,

  setObservacoes(produtoId: string, observacoes: string): void {
    emit({
      ...state,
      itens: state.itens.map((item) =>
        item.produto_id === produtoId ? { ...item, observacoes } : item,
      ),
    });
  },

  setPaymentMethod(metodoPagamento: PaymentMethod): void {
    emit({ ...state, metodoPagamento });
  },

  setDiscount(desconto: string): void {
    emit({ ...state, desconto: sanitizeMoneyInput(desconto) });
  },

  setClienteId(clienteId: string): void {
    emit({ ...state, clienteId });
  },

  reset(): void {
    emit({ ...initialState });
  },
};

export function useCartStore(): CartState {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

export function useCartTotals() {
  const cart = useCartStore();

  return useMemo(() => {
    const subtotalCents = cart.itens.reduce(
      (total, item) => total + moneyToCents(item.preco) * item.quantidade,
      0,
    );
    const requestedDiscountCents = moneyToCents(cart.desconto);
    const discountCents = Math.min(requestedDiscountCents, subtotalCents);
    const totalCents = Math.max(0, subtotalCents - discountCents);

    return {
      subtotalCents,
      discountCents,
      totalCents,
      subtotalFormatted: formatCurrency(subtotalCents),
      discountFormatted: formatCurrency(discountCents),
      totalFormatted: formatCurrency(totalCents),
    };
  }, [cart.desconto, cart.itens]);
}
