"use client";

import {
  Banknote,
  CheckCircle2,
  CreditCard,
  Delete,
  Loader2,
  QrCode,
} from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  PdvApiError,
  submitCheckout,
  type CheckoutResponse,
  type PaymentMethod,
} from "@/features/pdv/services/pdv-api";
import {
  cartActions,
  formatCurrency,
  useCartStore,
  useCartTotals,
} from "@/features/pdv/store/cart-store";
import { cn } from "@/lib/utils";

interface CheckoutModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const paymentOptions: Array<{
  value: PaymentMethod;
  label: string;
  description: string;
  icon: typeof Banknote;
}> = [
  { value: "dinheiro", label: "Dinheiro", description: "Troco em tela", icon: Banknote },
  { value: "pix", label: "PIX", description: "Pagamento instantâneo", icon: QrCode },
  { value: "cartao_debito", label: "Débito", description: "Cartão de débito", icon: CreditCard },
  { value: "cartao_credito", label: "Crédito", description: "Cartão de crédito", icon: CreditCard },
];

const keypadKeys = ["7", "8", "9", "4", "5", "6", "1", "2", "3", "C", "0", "00", "backspace"] as const;

export function CheckoutModal({ open, onOpenChange }: CheckoutModalProps) {
  const cart = useCartStore();
  const totals = useCartTotals();
  const [receivedCents, setReceivedCents] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CheckoutResponse | null>(null);

  const changeCents = Math.max(0, receivedCents - totals.totalCents);
  const cashIsEnough = cart.metodoPagamento !== "dinheiro" || receivedCents >= totals.totalCents;

  function selectPaymentMethod(method: PaymentMethod) {
    cartActions.setPaymentMethod(method);
    setError(null);
    if (method !== "dinheiro") {
      setReceivedCents(0);
    }
  }

  function pressKey(key: (typeof keypadKeys)[number]) {
    setError(null);
    if (key === "C") {
      setReceivedCents(0);
      return;
    }
    if (key === "backspace") {
      setReceivedCents((current) => Math.floor(current / 10));
      return;
    }
    if (key === "00") {
      setReceivedCents((current) => Math.min(current * 100, 99_999_999));
      return;
    }
    const digit = Number.parseInt(key, 10);
    setReceivedCents((current) => Math.min(current * 10 + digit, 99_999_999));
  }

  async function finalizeCheckout() {
    if (cart.itens.length === 0 || !cashIsEnough) return;

    setSubmitting(true);
    setError(null);

    try {
      const response = await submitCheckout({
        itens: cart.itens.map((item) => ({
          produto_id: item.produto_id,
          quantidade: item.quantidade,
          observacoes: item.observacoes.trim() || null,
        })),
        metodo_pagamento: cart.metodoPagamento,
        desconto: (totals.discountCents / 100).toFixed(2),
        cliente_id: cart.clienteId.trim() || null,
      });
      setResult(response);
      cartActions.reset();
    } catch (caught) {
      if (caught instanceof PdvApiError) {
        setError(caught.code ? `${caught.message} · ${caught.code}` : caught.message);
      } else {
        setError(caught instanceof Error ? caught.message : "Falha inesperada no checkout.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen && submitting) return;
    if (!nextOpen) {
      setError(null);
      setResult(null);
      setReceivedCents(0);
    }
    onOpenChange(nextOpen);
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[94vh] max-w-4xl overflow-y-auto p-0">
        {result ? (
          <div className="p-6 sm:p-8">
            <div className="mx-auto flex max-w-xl flex-col items-center text-center">
              <div className="flex size-16 items-center justify-center rounded-full bg-[#10b981]/10 text-[#10b981]">
                <CheckCircle2 className="size-9" />
              </div>
              <DialogTitle className="mt-4 text-2xl">Venda registrada com sucesso</DialogTitle>
              <DialogDescription className="mt-2">
                O backend canônico confirmou o pedido e retornou o estado financeiro da operação.
              </DialogDescription>

              <div className="mt-6 grid w-full gap-3 rounded-2xl border bg-muted/30 p-4 text-left sm:grid-cols-2">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pedido</p>
                  <p className="mt-1 break-all font-mono text-sm">{result.comanda.pedido_id}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Status</p>
                  <p className="mt-1 font-semibold">{result.comanda.status}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Pagamento</p>
                  <p className="mt-1 font-semibold">{result.pagamento?.status ?? "sem pagamento"}</p>
                </div>
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Total</p>
                  <p className="mt-1 text-xl font-black tabular-nums">R$ {result.comanda.total}</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap justify-center gap-2">
                <Badge variant="outline">
                  {result.idempotente ? "Replay idempotente · HTTP 200" : "Venda criada · HTTP 201"}
                </Badge>
                <Badge variant="outline" className="max-w-full truncate font-mono">
                  correlation {result.correlation_id}
                </Badge>
              </div>

              <Button className="mt-6 h-12 w-full rounded-xl" onClick={() => handleOpenChange(false)}>
                Nova venda
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="border-b p-6">
              <DialogHeader>
                <DialogTitle className="text-2xl">Finalizar pagamento</DialogTitle>
                <DialogDescription>
                  Selecione o meio de pagamento e confirme o checkout canônico do PDV.
                </DialogDescription>
              </DialogHeader>
            </div>

            <div className="grid gap-6 p-6 md:grid-cols-[1fr_0.9fr]">
              <section>
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                  Forma de pagamento
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  {paymentOptions.map((option) => {
                    const Icon = option.icon;
                    const active = cart.metodoPagamento === option.value;
                    return (
                      <button
                        key={option.value}
                        type="button"
                        onClick={() => selectPaymentMethod(option.value)}
                        className={cn(
                          "flex min-h-24 items-center gap-3 rounded-2xl border p-4 text-left transition active:scale-[0.985]",
                          active
                            ? "border-primary bg-primary/10 ring-2 ring-primary/20"
                            : "bg-card hover:bg-muted/50",
                        )}
                      >
                        <span className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl", active ? "bg-primary text-white" : "bg-muted text-foreground")}>
                          <Icon className="size-5" />
                        </span>
                        <span>
                          <strong className="block">{option.label}</strong>
                          <span className="text-xs text-muted-foreground">{option.description}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>

                <div className="mt-6 rounded-2xl border bg-slate-950 p-5 text-white">
                  <div className="flex items-center justify-between text-sm text-slate-400">
                    <span>Total do pedido</span>
                    <span className="tabular-nums">{totals.subtotalFormatted}</span>
                  </div>
                  {totals.discountCents > 0 ? (
                    <div className="mt-2 flex items-center justify-between text-sm text-slate-400">
                      <span>Desconto</span>
                      <span className="tabular-nums">- {totals.discountFormatted}</span>
                    </div>
                  ) : null}
                  <div className="mt-4 flex items-end justify-between border-t border-white/10 pt-4">
                    <span className="font-semibold">A pagar</span>
                    <span className="text-3xl font-black tabular-nums">{totals.totalFormatted}</span>
                  </div>
                </div>
              </section>

              <section className={cn(cart.metodoPagamento !== "dinheiro" && "opacity-50")}>
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    Valor recebido
                  </p>
                  <Banknote className="size-5 text-muted-foreground" />
                </div>

                <div className="rounded-2xl border bg-card p-4">
                  <p className="text-center text-3xl font-black tabular-nums">
                    {formatCurrency(receivedCents)}
                  </p>
                  <div className="mt-4 grid grid-cols-3 gap-2">
                    {keypadKeys.map((key) => (
                      <Button
                        key={key}
                        type="button"
                        variant="outline"
                        disabled={cart.metodoPagamento !== "dinheiro"}
                        onClick={() => pressKey(key)}
                        className="h-14 rounded-xl text-lg font-bold"
                        aria-label={key === "backspace" ? "Apagar último dígito" : `Tecla ${key}`}
                      >
                        {key === "backspace" ? <Delete className="size-5" /> : key}
                      </Button>
                    ))}
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-[#10b981]/30 bg-[#10b981]/10 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#10b981]">
                    Troco
                  </p>
                  <p className="mt-1 text-3xl font-black tabular-nums text-[#10b981]">
                    {formatCurrency(changeCents)}
                  </p>
                  {cart.metodoPagamento === "dinheiro" && !cashIsEnough ? (
                    <p className="mt-2 text-xs font-medium text-critical">
                      O valor recebido ainda é inferior ao total.
                    </p>
                  ) : null}
                </div>
              </section>
            </div>

            {error ? (
              <div className="mx-6 rounded-xl border border-critical/30 bg-critical/10 px-4 py-3 text-sm font-medium text-critical">
                {error}
              </div>
            ) : null}

            <DialogFooter className="border-t p-6">
              <Button type="button" variant="outline" className="h-12 rounded-xl" onClick={() => handleOpenChange(false)}>
                Voltar
              </Button>
              <Button
                type="button"
                className="h-12 rounded-xl px-8 font-bold"
                disabled={submitting || cart.itens.length === 0 || !cashIsEnough}
                onClick={() => void finalizeCheckout()}
              >
                {submitting ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                {submitting ? "Processando..." : "Confirmar venda"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
