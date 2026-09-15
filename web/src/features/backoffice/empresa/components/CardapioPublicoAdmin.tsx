"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  obterPublicacaoCardapio,
  salvarPublicacaoCardapio,
  type PublicacaoCardapio,
} from "@/features/cardapio-publico/services/cardapio-publico-api";

interface UnidadePublicavel {
  unidade_id: string;
  nome_fantasia: string;
  tipo: string;
}

function sugestaoSlug(nome: string): string {
  return nome.trim() || "minha-unidade";
}

export function CardapioPublicoAdmin({ unidades }: { unidades: UnidadePublicavel[] }) {
  const [unidadeId, setUnidadeId] = useState(unidades[0]?.unidade_id ?? "");
  const [publicacao, setPublicacao] = useState<PublicacaoCardapio | null>(null);
  const [slug, setSlug] = useState("");
  const [publicada, setPublicada] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const unidade = useMemo(
    () => unidades.find((item) => item.unidade_id === unidadeId),
    [unidadeId, unidades],
  );

  useEffect(() => {
    if (!unidadeId) {
      setPublicacao(null);
      return;
    }
    let cancelado = false;
    setLoading(true);
    setErro(null);
    setAviso(null);
    void obterPublicacaoCardapio(unidadeId)
      .then((dados) => {
        if (cancelado) return;
        setPublicacao(dados);
        setSlug(dados.slug ?? sugestaoSlug(unidade?.nome_fantasia ?? ""));
        setPublicada(dados.publicada);
      })
      .catch((error) => {
        if (!cancelado) setErro(error instanceof Error ? error.message : "Não foi possível carregar a publicação.");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });
    return () => { cancelado = true; };
  }, [unidade?.nome_fantasia, unidadeId]);

  async function salvar() {
    if (!unidadeId || !publicacao || saving) return;
    setSaving(true);
    setErro(null);
    setAviso(null);
    try {
      const atualizada = await salvarPublicacaoCardapio(unidadeId, {
        slug,
        publicada,
        versao: publicacao.versao,
      });
      setPublicacao(atualizada);
      setSlug(atualizada.slug ?? slug);
      setPublicada(atualizada.publicada);
      setAviso(atualizada.publicada ? "Cardápio público atualizado e publicado." : "Configuração salva. O cardápio está fora do ar.");
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Não foi possível salvar a publicação.");
    } finally {
      setSaving(false);
    }
  }

  async function copiarLink() {
    if (!publicacao?.url_publica) return;
    const url = new URL(publicacao.url_publica, window.location.origin).toString();
    try {
      await navigator.clipboard.writeText(url);
      setAviso("Link copiado.");
    } catch {
      setErro("Não foi possível copiar automaticamente. Selecione o link abaixo.");
    }
  }

  if (unidades.length === 0) return null;

  const linkCompleto = publicacao?.url_publica
    ? (typeof window === "undefined" ? publicacao.url_publica : new URL(publicacao.url_publica, window.location.origin).toString())
    : null;

  return <section className="space-y-4 rounded-xl border border-emerald-500/20 bg-slate-900 p-5">
    <div>
      <h2 className="text-xl font-semibold">Cardápio Digital público</h2>
      <p className="mt-2 text-sm text-slate-400">Configure o endereço público de cada matriz, filial ou unidade. O link é resolvido pelo servidor e não expõe os identificadores internos do cliente.</p>
    </div>

    <label className="block text-sm text-slate-300">Unidade publicada
      <select value={unidadeId} onChange={(event) => setUnidadeId(event.target.value)} disabled={loading || saving} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 p-2 text-white">
        {unidades.map((item) => <option key={item.unidade_id} value={item.unidade_id}>{item.nome_fantasia} · {item.tipo}</option>)}
      </select>
    </label>

    {loading ? <p role="status" className="text-sm text-slate-400">Carregando publicação…</p> : publicacao ? <div className="space-y-4">
      <label className="block text-sm text-slate-300">Nome do endereço público
        <Input value={slug} onChange={(event) => setSlug(event.target.value)} disabled={saving} className="mt-1 border-slate-700 bg-slate-950 text-white" placeholder="ex.: matriz-centro" />
        <span className="mt-1 block text-xs text-slate-500">Pode ser alterado a qualquer momento; a identidade pública segura da unidade permanece estável.</span>
      </label>

      <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={publicada} onChange={(event) => setPublicada(event.target.checked)} disabled={saving} />Cardápio disponível publicamente</label>

      {linkCompleto ? <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Link da unidade</p>
        <p className="mt-2 break-all text-sm text-emerald-300">{linkCompleto}</p>
        <div className="mt-3 flex flex-wrap gap-2"><Button type="button" variant="outline" size="sm" onClick={() => void copiarLink()}>Copiar link</Button><a href={publicacao.url_publica ?? undefined} target="_blank" rel="noreferrer" className="inline-flex items-center rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-800">Abrir cardápio</a></div>
      </div> : <p className="text-sm text-slate-500">O endereço público seguro será criado na primeira vez que esta configuração for salva.</p>}

      {erro ? <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-100">{erro}</p> : null}
      {aviso ? <p role="status" className="text-sm text-emerald-300">{aviso}</p> : null}
      <Button type="button" onClick={() => void salvar()} disabled={saving || slug.trim().length < 3}>{saving ? "Salvando…" : "Salvar publicação"}</Button>
    </div> : null}
  </section>;
}
