"use client";

import { useEffect, useState } from "react";

import {
  carregarCardapioPublico,
  type CardapioPublico,
} from "@/features/cardapio-publico/services/cardapio-publico-api";

export function CardapioPublicoWorkspace({ publicId, slug }: { publicId: string; slug: string }) {
  const [cardapio, setCardapio] = useState<CardapioPublico | null>(null);
  const [erro, setErro] = useState<string | null>(null);

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

  if (erro) {
    return <main className="min-h-screen bg-slate-950 px-6 py-16 text-white"><div className="mx-auto max-w-xl rounded-3xl border border-slate-800 bg-slate-900 p-8"><h1 className="text-xl font-semibold">Cardápio indisponível</h1><p className="mt-3 text-slate-400">{erro}</p></div></main>;
  }
  if (!cardapio) {
    return <main className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-300">Carregando cardápio…</main>;
  }

  return <main className="min-h-screen bg-slate-950 px-4 py-10 text-white sm:px-6">
    <div className="mx-auto max-w-4xl">
      <header className="mb-8 rounded-3xl border border-slate-800 bg-slate-900 p-6 shadow-2xl">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-400">Kordena · Cardápio Digital</p>
        <h1 className="mt-3 text-3xl font-black">{cardapio.empresa}</h1>
        <p className="mt-1 text-slate-400">{cardapio.unidade}</p>
      </header>
      {cardapio.itens.length === 0 ? <p className="rounded-2xl border border-slate-800 bg-slate-900 p-6 text-slate-400">Nenhum item disponível neste momento.</p> : <section className="grid gap-4 sm:grid-cols-2">
        {cardapio.itens.map((item) => <article key={item.produto_id} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="text-lg font-semibold">{item.nome}</h2>
          <p className="mt-3 text-2xl font-black text-emerald-400">R$ {Number(item.preco).toFixed(2).replace(".", ",")}</p>
        </article>)}
      </section>}
    </div>
  </main>;
}
