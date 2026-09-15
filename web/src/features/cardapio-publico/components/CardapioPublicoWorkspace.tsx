"use client";

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
    if (!chaveTentativa.current) {
      chaveTentativa.current = `web-${crypto.randomUUID()}`;
    }
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
    return <main className="min-h-screen bg-slate-950 px-6 py-16 text-white"><div className="mx-auto max-w-xl rounded-3xl border border-slate-800 bg-slate-900 p-8"><h1 className="text-xl font-semibold">Cardápio indisponível</h1><p className="mt-3 text-slate-400">{erro}</p></div></main>;
  }
  if (!cardapio) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">Carregando cardápio…</main>;
  }

  return <main className="min-h-screen bg-slate-950 px-4 py-10 text-white sm:px-6">
    <div className="mx-auto max-w-5xl">
      <header className="mb-8 rounded-3xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-400">Kordena · Cardápio Digital</p>
        <h1 className="mt-3 text-3xl font-black">{cardapio.empresa}</h1>
        <p className="mt-1 text-slate-400">{cardapio.unidade}</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <section>
          {cardapio.itens.length === 0 ? <p className="rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-400">Nenhum item disponível neste momento.</p> : <div className="grid gap-4 sm:grid-cols-2">
            {cardapio.itens.map((item) => {
              const quantidade = quantidades[item.produto_id] ?? 0;
              const maximo = Math.max(0, Math.floor(Number(item.estoque_disponivel)));
              return <article key={item.produto_id} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
                <h2 className="text-lg font-semibold">{item.nome}</h2>
                <p className="mt-3 text-2xl font-black text-emerald-400">{moeda(Number(item.preco))}</p>
                <div className="mt-5 flex items-center gap-3">
                  <Button type="button" variant="outline" size="sm" disabled={quantidade === 0 || Boolean(resultado)} onClick={() => alterarQuantidade(item.produto_id, -1, maximo)} aria-label={`Remover ${item.nome}`}>−</Button>
                  <span className="min-w-8 text-center font-semibold">{quantidade}</span>
                  <Button type="button" size="sm" disabled={quantidade >= maximo || Boolean(resultado)} onClick={() => alterarQuantidade(item.produto_id, 1, maximo)} aria-label={`Adicionar ${item.nome}`}>+</Button>
                </div>
                {maximo === 0 ? <p className="mt-3 text-xs text-amber-300">Indisponível no momento.</p> : null}
              </article>;
            })}
          </div>}
        </section>

        <aside className="h-fit rounded-3xl border border-slate-800 bg-slate-900 p-6 lg:sticky lg:top-6">
          <h2 className="text-xl font-bold">Seu pedido</h2>
          {itensSelecionados.length === 0 ? <p className="mt-4 text-sm text-slate-400">Adicione itens do cardápio para continuar.</p> : <div className="mt-4 space-y-3">
            {itensSelecionados.map(({ item, quantidade }) => <div key={item.produto_id} className="flex justify-between gap-4 text-sm"><span className="text-slate-300">{quantidade}× {item.nome}</span><span>{moeda(Number(item.preco) * quantidade)}</span></div>)}
          </div>}
          <div className="mt-5 border-t border-slate-800 pt-4"><div className="flex justify-between text-lg font-bold"><span>Total</span><span className="text-emerald-400">{moeda(totalVisual)}</span></div><p className="mt-1 text-xs text-slate-500">O valor final é validado pelo servidor no momento do pedido.</p></div>

          {!resultado ? <>
            <label className="mt-5 block text-sm font-medium text-slate-300">Forma de pagamento
              <select value={metodo} onChange={(event) => setMetodo(event.target.value)} disabled={enviando} className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-white">
                {METODOS.map((opcao) => <option key={opcao.value} value={opcao.value}>{opcao.label}</option>)}
              </select>
            </label>
            {erro ? <p role="alert" className="mt-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100">{erro}</p> : null}
            <Button className="mt-5 w-full" disabled={itensSelecionados.length === 0 || enviando} onClick={() => void finalizarPedido()}>{enviando ? "Enviando pedido…" : "Confirmar pedido"}</Button>
          </> : <div className="mt-5 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4" role="status">
            <p className="font-semibold text-emerald-300">Pedido recebido</p>
            <p className="mt-2 text-sm text-slate-300">Pedido: {resultado.pedido_id}</p>
            <p className="mt-1 text-sm text-slate-400">Status: {resultado.status.replaceAll("_", " ")}</p>
            <p className="mt-1 text-sm text-slate-400">Total confirmado: {moeda(Number(resultado.total))}</p>
          </div>}
        </aside>
      </div>
    </div>
  </main>;
}
