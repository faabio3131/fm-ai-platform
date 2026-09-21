"use client";

import { CheckCircle2, Minus, Plus, ReceiptText, ShoppingBag, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  carregarCardapioPublico,
  finalizarCheckoutPublico,
  type CardapioPublico,
  type ResultadoCheckoutPublico,
} from "@/features/cardapio-publico/services/cardapio-publico-api";

const METODOS = [
  { value: "pix", label: "Pix" },
  { value: "dinheiro", label: "Dinheiro" },
  { value: "cartao_credito", label: "Cartão de crédito" },
  { value: "cartao_debito", label: "Cartão de débito" },
  { value: "pagamento_na_entrega", label: "Pagamento na entrega" },
] as const;

function moeda(valor: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valor);
}

export function CardapioPublicoWorkspace({ publicId, slug }: { publicId: string; slug: string }) {
  const [cardapio, setCardapio] = useState<CardapioPublico | null>(null);
  const [quantidades, setQuantidades] = useState<Record<string, number>>({});
  const [metodo, setMetodo] = useState("pix");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<ResultadoCheckoutPublico | null>(null);
  const chaveTentativa = useRef<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    void carregarCardapioPublico(publicId)
      .then((dados) => {
        if (cancelado) return;
        if (dados.slug !== slug) {
          setErro("Este link de cardápio não está mais disponível.");
          return;
        }
        setCardapio(dados);
      })
      .catch((error) => {
        if (!cancelado) setErro(error instanceof Error ? error.message : "Cardápio indisponível.");
      });
    return () => { cancelado = true; };
  }, [publicId, slug]);

  const itensSelecionados = useMemo(() => {
    if (!cardapio) return [];
    return cardapio.itens
      .map((item) => ({ item, quantidade: quantidades[item.produto_id] ?? 0 }))
      .filter(({ quantidade }) => quantidade > 0);
  }, [cardapio, quantidades]);

  const totalVisual = useMemo(
    () => itensSelecionados.reduce((soma, { item, quantidade }) => soma + Number(item.preco) * quantidade, 0),
    [itensSelecionados],
  );

  function alterarQuantidade(produtoId: string, delta: number, maximo: number) {
    if (resultado) return;
    setQuantidades((atual) => {
      const proxima = Math.max(0, Math.min(maximo, (atual[produtoId] ?? 0) + delta));
      return { ...atual, [produtoId]: proxima };
    });
  }

  async function finalizarPedido() {
    if (itensSelecionados.length === 0 || enviando || resultado) return;
    setErro(null);
    setEnviando(true);
    if (!chaveTentativa.current) chaveTentativa.current = `web-${crypto.randomUUID()}`;
    try {
      const resposta = await finalizarCheckoutPublico(publicId, {
        itens: itensSelecionados.map(({ item, quantidade }) => ({
          produto_id: item.produto_id,
          quantidade,
        })),
        metodo_pagamento: metodo,
        idempotency_key: chaveTentativa.current,
      });
      setResultado(resposta);
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível enviar o pedido.");
    } finally {
      setEnviando(false);
    }
  }

  if (erro && !cardapio) {
    return (
      <main className="kordena-page-dark min-h-screen px-6 py-16 text-white">
        <div className="kordena-panel-dark mx-auto max-w-xl rounded-[2rem] p-8">
          <h1 className="text-xl font-bold">Cardápio indisponível</h1>
          <p className="mt-3 text-slate-400">{erro}</p>
        </div>
      </main>
    );
  }
  if (!cardapio) {
    return <main className="kordena-page-dark flex min-h-screen items-center justify-center text-slate-300">Carregando cardápio…</main>;
  }

  return (
    <main className="kordena-page-dark min-h-screen px-4 py-8 text-white sm:px-6 sm:py-10">
      <div className="kordena-enter mx-auto max-w-6xl">
        <header className="relative mb-7 overflow-hidden rounded-[2rem] border border-emerald-400/15 bg-[linear-gradient(135deg,rgba(16,185,129,0.12),rgba(14,165,233,0.06)_50%,rgba(8,17,31,0.96))] p-6 shadow-[0_30px_80px_-44px_rgba(16,185,129,0.45)] sm:p-8">
          <div className="kordena-grid pointer-events-none absolute inset-0 opacity-50" />
          <div className="relative flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/[0.07] px-3 py-1.5 text-xs font-bold text-emerald-200">
                <Sparkles className="size-3.5" />
                Kordena · Cardápio Digital
              </div>
              <h1 className="mt-5 text-3xl font-black tracking-[-0.035em] sm:text-4xl">{cardapio.empresa}</h1>
              <p className="mt-2 text-sm text-slate-400">{cardapio.unidade}</p>
            </div>
            <div className="flex items-center gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.04] px-4 py-3">
              <ShoppingBag className="size-5 text-emerald-300" />
              <div>
                <p className="text-xs font-bold text-white">{itensSelecionados.length} itens selecionados</p>
                <p className="mt-0.5 text-xs text-slate-500">{moeda(totalVisual)}</p>
              </div>
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_370px]">
          <section>
            {cardapio.itens.length === 0 ? (
              <p className="kordena-panel-dark rounded-3xl p-6 text-slate-400">Nenhum item disponível neste momento.</p>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                {cardapio.itens.map((item) => {
                  const quantidade = quantidades[item.produto_id] ?? 0;
                  const maximo = Math.max(0, Math.floor(Number(item.estoque_disponivel)));
                  return (
                    <article
                      key={item.produto_id}
                      className="kordena-panel-dark group rounded-[1.5rem] p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-emerald-400/20"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h2 className="text-lg font-bold tracking-tight">{item.nome}</h2>
                          <p className="mt-3 text-2xl font-black tabular-nums text-emerald-300">{moeda(Number(item.preco))}</p>
                        </div>
                        <span className="flex size-10 items-center justify-center rounded-xl bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/15">
                          <ReceiptText className="size-5" />
                        </span>
                      </div>
                      <div className="mt-6 flex items-center gap-3">
                        <Button type="button" variant="outline" size="icon" className="border-white/10 bg-white/[0.04] text-white" disabled={quantidade === 0 || Boolean(resultado)} onClick={() => alterarQuantidade(item.produto_id, -1, maximo)} aria-label={`Remover ${item.nome}`}>
                          <Minus />
                        </Button>
                        <span className="min-w-10 text-center text-lg font-black tabular-nums">{quantidade}</span>
                        <Button type="button" size="icon" disabled={quantidade >= maximo || Boolean(resultado)} onClick={() => alterarQuantidade(item.produto_id, 1, maximo)} aria-label={`Adicionar ${item.nome}`}>
                          <Plus />
                        </Button>
                      </div>
                      {maximo === 0 ? <p className="mt-3 text-xs font-semibold text-amber-300">Indisponível no momento.</p> : null}
                    </article>
                  );
                })}
              </div>
            )}
          </section>

          <aside className="kordena-panel-dark h-fit rounded-[1.75rem] p-6 lg:sticky lg:top-6">
            <div className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center rounded-xl bg-blue-400/10 text-blue-300 ring-1 ring-blue-400/15">
                <ShoppingBag className="size-5" />
              </span>
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.15em] text-slate-500">Checkout</p>
                <h2 className="text-xl font-bold">Seu pedido</h2>
              </div>
            </div>

            {itensSelecionados.length === 0 ? (
              <p className="mt-5 text-sm leading-6 text-slate-400">Adicione itens do cardápio para continuar.</p>
            ) : (
              <div className="mt-5 space-y-3">
                {itensSelecionados.map(({ item, quantidade }) => (
                  <div key={item.produto_id} className="flex justify-between gap-4 rounded-xl bg-slate-950/45 px-3 py-2.5 text-sm">
                    <span className="text-slate-300">{quantidade}× {item.nome}</span>
                    <span className="font-semibold tabular-nums">{moeda(Number(item.preco) * quantidade)}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="mt-5 border-t border-white/[0.07] pt-5">
              <div className="flex justify-between text-lg font-bold">
                <span>Total</span>
                <span className="tabular-nums text-emerald-300">{moeda(totalVisual)}</span>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate-500">O valor final é validado pelo servidor no momento do pedido.</p>
            </div>

            {!resultado ? (
              <>
                <label className="mt-5 block text-sm font-semibold text-slate-300">
                  Forma de pagamento
                  <select
                    value={metodo}
                    onChange={(event) => setMetodo(event.target.value)}
                    disabled={enviando}
                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/75 p-3 text-white outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10"
                  >
                    {METODOS.map((opcao) => <option key={opcao.value} value={opcao.value}>{opcao.label}</option>)}
                  </select>
                </label>
                {erro ? <p role="alert" className="mt-4 rounded-xl border border-red-500/25 bg-red-500/10 p-3 text-sm text-red-100">{erro}</p> : null}
                <Button className="mt-5 h-12 w-full" disabled={itensSelecionados.length === 0 || enviando} onClick={() => void finalizarPedido()}>
                  {enviando ? "Enviando pedido…" : "Confirmar pedido"}
                </Button>
              </>
            ) : (
              <div className="mt-5 rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.07] p-4" role="status">
                <div className="flex items-center gap-2 font-bold text-emerald-200">
                  <CheckCircle2 className="size-5" />
                  Pedido recebido
                </div>
                <p className="mt-3 text-sm text-slate-300">Pedido: {resultado.pedido_id}</p>
                <p className="mt-1 text-sm text-slate-400">Status: {resultado.status.replaceAll("_", " ")}</p>
                <p className="mt-1 text-sm text-slate-400">Total confirmado: {moeda(Number(resultado.total))}</p>
              </div>
            )}
          </aside>
        </div>
      </div>
    </main>
  );
}
