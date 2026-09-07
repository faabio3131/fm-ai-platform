"use client";

import { FormEvent, useMemo, useState } from "react";
import {
  CircleDollarSign,
  LoaderCircle,
  Minus,
  Plus,
  ReceiptText,
  Search,
  Send,
  ShoppingCart,
  Trash2,
  UserRound,
  UsersRound,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  LancamentoPedidoPayload,
  OpenComandaPayload,
  SalaoComandaDetails,
  SalaoComandaMapa,
  SalaoMesa,
  SalaoProduto,
} from "@/features/salao/services/salao-api";

interface TableDetailModalProps {
  open: boolean;
  mesa: SalaoMesa | null;
  comanda: SalaoComandaMapa | null;
  details: SalaoComandaDetails | null;
  produtos: SalaoProduto[];
  loading: boolean;
  productsLoading: boolean;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenComanda: (payload: OpenComandaPayload) => Promise<void>;
  onLaunchOrder: (payload: LancamentoPedidoPayload) => Promise<void>;
  onRequestBill: () => Promise<void>;
}

interface CartItem {
  produto: SalaoProduto;
  quantidade: number;
  observacao: string;
}

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

function formatCurrency(value: string | number): string {
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? currencyFormatter.format(numericValue)
    : "R$ —";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
}

export function TableDetailModal({
  open,
  mesa,
  comanda,
  details,
  produtos,
  loading,
  productsLoading,
  busy,
  onOpenChange,
  onOpenComanda,
  onLaunchOrder,
  onRequestBill,
}: TableDetailModalProps) {
  const [responsavelNome, setResponsavelNome] = useState("");
  const [quantidadePessoas, setQuantidadePessoas] = useState("2");
  const [busca, setBusca] = useState("");
  const [cart, setCart] = useState<CartItem[]>([]);

  const produtosFiltrados = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");
    if (!termo) return produtos;
    return produtos.filter((produto) =>
      `${produto.nome} ${produto.categoria ?? ""}`
        .toLocaleLowerCase("pt-BR")
        .includes(termo),
    );
  }, [busca, produtos]);

  const cartTotal = useMemo(
    () =>
      cart.reduce(
        (total, item) => total + Number(item.produto.preco) * item.quantidade,
        0,
      ),
    [cart],
  );

  if (!mesa) return null;

  const contaSolicitada =
    (details?.status_comanda ?? comanda?.status_comanda) === "CONTA_SOLICITADA";
  const statusComanda = details?.status_comanda ?? comanda?.status_comanda;
  const podeConsumir = statusComanda === "ABERTA" || statusComanda === "EM_CONSUMO";
  const livre = mesa.status === "LIVRE" && !comanda;

  async function submitOpen(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!mesa) return;

    const parsedPeople = Number.parseInt(quantidadePessoas, 10);
    await onOpenComanda({
      mesa_id: mesa.id,
      responsavel_nome: responsavelNome.trim() || null,
      quantidade_pessoas:
        Number.isFinite(parsedPeople) && parsedPeople > 0 ? parsedPeople : null,
    });
  }

  function addProduto(produto: SalaoProduto) {
    setCart((atual) => {
      const index = atual.findIndex((item) => item.produto.id === produto.id);
      if (index < 0) return [...atual, { produto, quantidade: 1, observacao: "" }];
      return atual.map((item, itemIndex) =>
        itemIndex === index ? { ...item, quantidade: item.quantidade + 1 } : item,
      );
    });
  }

  function changeQuantidade(produtoId: string, delta: number) {
    setCart((atual) =>
      atual
        .map((item) =>
          item.produto.id === produtoId
            ? { ...item, quantidade: Math.max(0, item.quantidade + delta) }
            : item,
        )
        .filter((item) => item.quantidade > 0),
    );
  }

  function changeObservacao(produtoId: string, observacao: string) {
    setCart((atual) =>
      atual.map((item) =>
        item.produto.id === produtoId ? { ...item, observacao } : item,
      ),
    );
  }

  async function submitOrder() {
    if (!cart.length || busy) return;
    const payload: LancamentoPedidoPayload = {
      itens: cart.map((item) => ({
        produto_id: item.produto.id,
        quantidade: item.quantidade,
        observacao: item.observacao.trim() || null,
      })),
    };
    await onLaunchOrder(payload);
    setCart([]);
    setBusca("");
  }

  const items = details?.pedidos.flatMap((pedido) => pedido.itens) ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="dark max-h-[94vh] overflow-y-auto border-slate-700 bg-[#1e293b] text-slate-100 sm:max-w-4xl">
        <DialogHeader className="border-b border-slate-700 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3 pr-6">
            <div>
              <DialogTitle className="text-2xl font-black text-white">
                Mesa {mesa.numero}
              </DialogTitle>
              <DialogDescription className="mt-1 text-slate-400">
                {mesa.nome ?? `${mesa.capacidade} lugares`} · operação canônica de Salão
              </DialogDescription>
            </div>
            <Badge
              className={
                contaSolicitada
                  ? "border border-[#f59e0b]/40 bg-[#f59e0b]/15 text-amber-200 hover:bg-[#f59e0b]/15"
                  : livre
                    ? "border border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-800"
                    : "border border-[#2563eb]/40 bg-[#2563eb]/15 text-blue-200 hover:bg-[#2563eb]/15"
              }
            >
              {contaSolicitada ? "Conta solicitada" : livre ? "Livre" : "Ocupada"}
            </Badge>
          </div>
        </DialogHeader>

        {livre ? (
          <form className="space-y-5 py-2" onSubmit={(event) => void submitOpen(event)}>
            <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
              <h3 className="font-black text-white">Abrir nova comanda</h3>
              <p className="mt-1 text-sm text-slate-400">
                A mesa será ocupada atomicamente pelo backend. Replays usam a mesma chave de idempotência da tentativa.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm font-semibold text-slate-200">
                <span className="flex items-center gap-2">
                  <UserRound className="size-4 text-[#2563eb]" />
                  Responsável (opcional)
                </span>
                <Input
                  value={responsavelNome}
                  onChange={(event) => setResponsavelNome(event.target.value)}
                  placeholder="Nome de referência"
                  maxLength={120}
                  className="h-12 border-slate-600 bg-slate-950 text-white"
                />
              </label>
              <label className="space-y-1.5 text-sm font-semibold text-slate-200">
                <span className="flex items-center gap-2">
                  <UsersRound className="size-4 text-[#2563eb]" />
                  Pessoas
                </span>
                <Input
                  type="number"
                  min={1}
                  max={1000}
                  value={quantidadePessoas}
                  onChange={(event) => setQuantidadePessoas(event.target.value)}
                  className="h-12 border-slate-600 bg-slate-950 text-white tabular-nums"
                />
              </label>
            </div>

            <Button
              type="submit"
              disabled={busy}
              className="h-12 w-full rounded-xl bg-[#2563eb] text-base font-black transition hover:bg-blue-500 active:scale-[0.98]"
            >
              {busy ? <LoaderCircle className="animate-spin" /> : <ReceiptText />}
              {busy ? "Abrindo comanda..." : "Abrir comanda"}
            </Button>
          </form>
        ) : loading ? (
          <div className="flex min-h-72 items-center justify-center gap-3 text-sm font-semibold text-slate-400">
            <LoaderCircle className="size-5 animate-spin text-[#2563eb]" />
            Carregando extrato da comanda...
          </div>
        ) : details ? (
          <div className="space-y-5 py-2">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-slate-700 bg-slate-950/55 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Comanda</p>
                <p className="mt-2 font-mono text-lg font-black text-white">{details.numero}</p>
              </div>
              <div className="rounded-2xl border border-slate-700 bg-slate-950/55 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Aberta em</p>
                <p className="mt-2 text-sm font-bold text-slate-200">{formatDate(details.aberta_em)}</p>
              </div>
              <div className="rounded-2xl border border-[#2563eb]/35 bg-[#2563eb]/10 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-blue-300">Total acumulado</p>
                <p className="mt-2 text-2xl font-black tabular-nums text-white">{formatCurrency(details.total)}</p>
              </div>
            </div>

            {podeConsumir ? (
              <section className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950/45 shadow-xl shadow-black/10">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-4">
                  <div>
                    <h3 className="flex items-center gap-2 font-black text-white">
                      <ShoppingCart className="size-5 text-[#2563eb]" />
                      Lançar pedido
                    </h3>
                    <p className="mt-1 text-xs text-slate-500">Selecione itens ativos do cardápio e envie para a comanda.</p>
                  </div>
                  <Badge className="border border-white/10 bg-white/[0.05] font-mono tabular-nums text-slate-200 hover:bg-white/[0.05]">
                    {cart.length} item(ns) · {formatCurrency(cartTotal)}
                  </Badge>
                </div>

                <div className="grid gap-4 p-4 lg:grid-cols-[1.05fr_0.95fr]">
                  <div className="space-y-3">
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                      <Input
                        value={busca}
                        onChange={(event) => setBusca(event.target.value)}
                        placeholder="Buscar produto ou categoria..."
                        className="h-11 border-white/10 bg-zinc-950/80 pl-9 text-white"
                      />
                    </div>
                    <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
                      {productsLoading ? (
                        <div className="flex items-center justify-center gap-2 rounded-xl border border-white/10 p-6 text-sm text-slate-400">
                          <LoaderCircle className="size-4 animate-spin" />
                          Carregando cardápio...
                        </div>
                      ) : produtosFiltrados.length ? (
                        produtosFiltrados.map((produto) => (
                          <button
                            key={produto.id}
                            type="button"
                            onClick={() => addProduto(produto)}
                            className="flex w-full items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-3 text-left transition hover:border-[#2563eb]/50 hover:bg-[#2563eb]/10 active:scale-[0.98]"
                          >
                            <span className="min-w-0">
                              <span className="block truncate text-sm font-bold text-slate-100">{produto.nome}</span>
                              <span className="block truncate text-xs text-slate-500">{produto.categoria ?? "Sem categoria"}</span>
                            </span>
                            <span className="shrink-0 font-mono text-sm font-black tabular-nums text-white">{formatCurrency(produto.preco)}</span>
                          </button>
                        ))
                      ) : (
                        <div className="rounded-xl border border-dashed border-white/10 p-6 text-center text-sm text-slate-500">
                          Nenhum produto ativo encontrado.
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="space-y-3 rounded-xl border border-white/10 bg-black/20 p-3">
                    {cart.length ? (
                      <>
                        <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
                          {cart.map((item) => (
                            <div key={item.produto.id} className="rounded-xl border border-white/10 bg-zinc-950/70 p-3">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-bold text-white">{item.produto.nome}</p>
                                  <p className="mt-1 font-mono text-xs tabular-nums text-slate-400">{formatCurrency(Number(item.produto.preco) * item.quantidade)}</p>
                                </div>
                                <div className="flex items-center gap-1">
                                  <Button type="button" size="icon" variant="ghost" onClick={() => changeQuantidade(item.produto.id, -1)} className="size-9 text-slate-300 hover:bg-white/10 hover:text-white active:scale-[0.98]">
                                    {item.quantidade === 1 ? <Trash2 className="size-4" /> : <Minus className="size-4" />}
                                  </Button>
                                  <span className="w-8 text-center font-mono text-sm font-black tabular-nums text-white">{item.quantidade}</span>
                                  <Button type="button" size="icon" variant="ghost" onClick={() => changeQuantidade(item.produto.id, 1)} className="size-9 text-slate-300 hover:bg-white/10 hover:text-white active:scale-[0.98]">
                                    <Plus className="size-4" />
                                  </Button>
                                </div>
                              </div>
                              <Input
                                value={item.observacao}
                                onChange={(event) => changeObservacao(item.produto.id, event.target.value)}
                                maxLength={500}
                                placeholder="Observação (opcional)"
                                className="mt-3 h-9 border-white/10 bg-black/30 text-xs text-white"
                              />
                            </div>
                          ))}
                        </div>
                        <div className="flex items-center justify-between border-t border-white/10 pt-3">
                          <span className="text-sm font-semibold text-slate-400">Total do lançamento</span>
                          <span className="font-mono text-lg font-black tabular-nums text-white">{formatCurrency(cartTotal)}</span>
                        </div>
                        <Button
                          type="button"
                          disabled={busy || !cart.length}
                          onClick={() => void submitOrder()}
                          className="h-12 w-full rounded-xl bg-[#2563eb] font-black transition hover:bg-blue-500 active:scale-[0.98] disabled:opacity-50"
                        >
                          {busy ? <LoaderCircle className="animate-spin" /> : <Send />}
                          {busy ? "Enviando pedido..." : "Enviar pedido"}
                        </Button>
                      </>
                    ) : (
                      <div className="flex min-h-44 flex-col items-center justify-center text-center">
                        <ShoppingCart className="size-7 text-slate-600" />
                        <p className="mt-3 text-sm font-bold text-slate-400">Carrinho vazio</p>
                        <p className="mt-1 max-w-56 text-xs text-slate-600">Toque em um produto para adicioná-lo à comanda.</p>
                      </div>
                    )}
                  </div>
                </div>
              </section>
            ) : null}

            <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/35">
              <div className="flex items-center justify-between gap-3 border-b border-slate-700 px-4 py-3">
                <div>
                  <h3 className="font-black text-white">Extrato de consumo</h3>
                  <p className="text-xs text-slate-500">{details.pedidos.length} pedido(s) · {items.length} item(ns)</p>
                </div>
                <ReceiptText className="size-5 text-[#2563eb]" />
              </div>

              {items.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow className="border-slate-800 hover:bg-transparent">
                      <TableHead className="text-slate-400">Item</TableHead>
                      <TableHead className="w-20 text-right text-slate-400">Qtd.</TableHead>
                      <TableHead className="w-32 text-right text-slate-400">Subtotal</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <TableRow key={item.id} className="border-slate-800 hover:bg-slate-900/60">
                        <TableCell>
                          <p className="font-semibold text-slate-100">{item.nome}</p>
                          {item.observacao ? <p className="mt-1 text-xs text-slate-500">{item.observacao}</p> : null}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-slate-300">{item.quantidade}</TableCell>
                        <TableCell className="text-right font-mono font-bold tabular-nums text-slate-100">{formatCurrency(item.subtotal)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="px-4 py-10 text-center text-sm font-medium text-slate-500">Nenhum item vinculado à comanda até o momento.</div>
              )}
            </div>

            <div className="flex flex-col gap-3 rounded-2xl border border-slate-700 bg-slate-950/50 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Saldo da comanda</p>
                <p className="mt-1 text-2xl font-black tabular-nums text-white">{formatCurrency(details.saldo)}</p>
              </div>
              <Button
                type="button"
                disabled={busy || contaSolicitada}
                onClick={() => void onRequestBill()}
                className={contaSolicitada ? "h-12 rounded-xl bg-[#f59e0b]/20 font-black text-amber-200" : "h-12 rounded-xl bg-[#f59e0b] font-black text-slate-950 transition hover:bg-amber-400 active:scale-[0.98]"}
              >
                {busy ? <LoaderCircle className="animate-spin" /> : <CircleDollarSign />}
                {contaSolicitada ? "Conta já solicitada" : busy ? "Solicitando..." : "Solicitar encerramento"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="py-10 text-center text-sm font-medium text-slate-500">Não foi possível carregar os detalhes desta comanda.</div>
        )}
      </DialogContent>
    </Dialog>
  );
}
