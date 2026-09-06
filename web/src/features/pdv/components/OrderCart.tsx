"use client";

import { Minus, Plus, ReceiptText, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  cartActions,
  formatCurrency,
  moneyToCents,
  useCartStore,
  useCartTotals,
} from "@/features/pdv/store/cart-store";

interface OrderCartProps {
  onCheckout: () => void;
}

export function OrderCart({ onCheckout }: OrderCartProps) {
  const cart = useCartStore();
  const totals = useCartTotals();

  return (
    <Card className="flex min-h-0 flex-col overflow-hidden border-slate-300 shadow-lg lg:h-[calc(100vh-8.5rem)]">
      <CardHeader className="border-b bg-slate-950 text-white">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
              Pedido balcão
            </p>
            <CardTitle className="mt-1 flex items-center gap-2 text-xl text-white">
              <ReceiptText className="size-5" />
              Carrinho
            </CardTitle>
          </div>
          <Badge className="bg-white/10 text-white hover:bg-white/10">
            {cart.itens.reduce((sum, item) => sum + item.quantidade, 0)} itens
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col p-0">
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {cart.itens.length === 0 ? (
            <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed bg-muted/40 p-6 text-center">
              <ReceiptText className="mb-3 size-8 text-muted-foreground" />
              <p className="font-medium">Carrinho vazio</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Toque em um produto para iniciar o pedido.
              </p>
            </div>
          ) : (
            cart.itens.map((item) => (
              <article key={item.produto_id} className="rounded-2xl border bg-card p-3 shadow-sm">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold leading-tight">{item.nome}</h3>
                    <p className="mt-1 text-sm font-semibold tabular-nums text-primary">
                      {formatCurrency(moneyToCents(item.preco) * item.quantidade)}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-11 shrink-0 text-destructive hover:bg-destructive/10 hover:text-destructive"
                    onClick={() => cartActions.removeItem(item.produto_id)}
                    aria-label={`Remover ${item.nome}`}
                  >
                    <Trash2 />
                  </Button>
                </div>

                <div className="mt-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="size-11 rounded-xl"
                      onClick={() => cartActions.decrement(item.produto_id)}
                      aria-label={`Diminuir quantidade de ${item.nome}`}
                    >
                      <Minus />
                    </Button>
                    <span className="min-w-10 text-center text-lg font-bold tabular-nums">
                      {item.quantidade}
                    </span>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      className="size-11 rounded-xl"
                      onClick={() => cartActions.increment(item.produto_id)}
                      aria-label={`Aumentar quantidade de ${item.nome}`}
                    >
                      <Plus />
                    </Button>
                  </div>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {formatCurrency(moneyToCents(item.preco))} un.
                  </span>
                </div>

                <textarea
                  value={item.observacoes}
                  onChange={(event) => cartActions.setObservacoes(item.produto_id, event.target.value)}
                  maxLength={500}
                  rows={2}
                  placeholder="Observações do item"
                  className="mt-3 w-full resize-none rounded-xl border bg-background px-3 py-2 text-sm outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/20"
                />
              </article>
            ))
          )}
        </div>

        <div className="border-t bg-card p-4">
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Desconto
              <Input
                inputMode="decimal"
                value={cart.desconto}
                onChange={(event) => cartActions.setDiscount(event.target.value)}
                className="mt-1 h-11 font-semibold tabular-nums text-foreground"
                aria-label="Desconto do pedido"
              />
            </label>
            <label className="space-y-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Cliente ID
              <Input
                value={cart.clienteId}
                onChange={(event) => cartActions.setClienteId(event.target.value)}
                className="mt-1 h-11 text-foreground"
                placeholder="Opcional"
                aria-label="Identificador do cliente"
              />
            </label>
          </div>

          <div className="mt-4 space-y-2 text-sm tabular-nums">
            <div className="flex justify-between text-muted-foreground">
              <span>Subtotal</span>
              <span>{totals.subtotalFormatted}</span>
            </div>
            <div className="flex justify-between text-muted-foreground">
              <span>Desconto</span>
              <span>- {totals.discountFormatted}</span>
            </div>
            <div className="flex items-end justify-between border-t pt-3">
              <span className="font-semibold">Total</span>
              <span className="text-2xl font-black tracking-tight text-slate-950 dark:text-white">
                {totals.totalFormatted}
              </span>
            </div>
          </div>

          <Button
            type="button"
            size="lg"
            className="mt-4 h-14 w-full rounded-xl text-base font-bold"
            disabled={cart.itens.length === 0 || totals.totalCents < 0}
            onClick={onCheckout}
          >
            Ir para pagamento
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
