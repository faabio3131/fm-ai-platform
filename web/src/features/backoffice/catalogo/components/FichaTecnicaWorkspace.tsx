"use client";

import { BookOpen, LoaderCircle, Plus, RefreshCw, Sparkles, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  criarPratoComFicha,
  importarCardapioGeminiPorArquivo,
  importarCardapioGeminiPorTexto,
  listarInsumosFicha,
  obterFichaProduto,
  type CatalogoFicha,
  type CatalogoInsumoFicha,
  type CatalogoProduto,
} from "@/features/backoffice/catalogo/services/catalogo-api";

interface ItemReceita {
  insumo: CatalogoInsumoFicha;
  quantidade: number;
  custo: number;
  unidadeExibicao: string;
}

function moeda(valor: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(valor);
}

export function FichaTecnicaWorkspace({
  produtos,
  categorias,
  onCreated,
  onImported,
}: {
  produtos: CatalogoProduto[];
  categorias: string[];
  onCreated: (produto: CatalogoProduto) => void;
  onImported: () => void;
}) {
  const [insumos, setInsumos] = useState<CatalogoInsumoFicha[]>([]);
  const [itens, setItens] = useState<ItemReceita[]>([]);
  const [insumoId, setInsumoId] = useState("");
  const [quantidade, setQuantidade] = useState(100);
  const [margem, setMargem] = useState(60);
  const [preco, setPreco] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [produtoConsultaId, setProdutoConsultaId] = useState("");
  const [fichaConsultada, setFichaConsultada] = useState<CatalogoFicha | null>(null);
  const [fonteImportacao, setFonteImportacao] = useState<"arquivo" | "texto">("arquivo");
  const [textoCardapio, setTextoCardapio] = useState("");
  const [arquivoCardapio, setArquivoCardapio] = useState<File | null>(null);
  const [importando, setImportando] = useState(false);

  const carregarInsumos = useCallback(async () => {
    setLoading(true);
    try {
      const result = await listarInsumosFicha();
      setInsumos(result);
      setInsumoId((current) =>
        result.some((item) => item.id === current) ? current : (result[0]?.id ?? ""),
      );
      setErro(null);
    } catch {
      setErro("Não foi possível carregar os insumos do almoxarifado.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void carregarInsumos(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [carregarInsumos]);

  const cmv = useMemo(() => itens.reduce((total, item) => total + item.custo, 0), [itens]);
  const sugestao = useMemo(
    () => (margem < 100 ? cmv / (1 - margem / 100) : cmv * (1 + margem / 100)),
    [cmv, margem],
  );
  const margemReal = preco > 0 ? ((preco - cmv) / preco) * 100 : 0;

  function adicionarItem() {
    const insumo = insumos.find((item) => item.id === insumoId);
    if (!insumo || quantidade <= 0) return;
    const custo =
      insumo.unidade_medida === "kg"
        ? (quantidade / 1000) * insumo.custo_unitario
        : quantidade * insumo.custo_unitario;
    setItens((current) => [
      ...current,
      {
        insumo,
        quantidade,
        custo,
        unidadeExibicao: insumo.unidade_medida === "kg" ? "g" : insumo.unidade_medida,
      },
    ]);
    if (preco === 0) {
      const novoCmv = cmv + custo;
      setPreco(Number((margem < 100 ? novoCmv / (1 - margem / 100) : novoCmv * (1 + margem / 100)).toFixed(2)));
    }
  }

  async function salvar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (itens.length === 0) {
      setErro("Adicione pelo menos um insumo à ficha técnica.");
      return;
    }
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setErro(null);
    setAviso(null);
    try {
      const criado = await criarPratoComFicha({
        nome: String(form.get("nome") || "").trim(),
        categoria: String(form.get("categoria") || "").trim(),
        preco,
        custo_total_cmv: Number(cmv.toFixed(2)),
        margem_exibicao: `${margemReal.toFixed(1)}%`,
        descricao_bruta: String(form.get("descricao") || "").trim(),
        ativo: true,
        itens_ficha: itens.map((item) => ({
          insumo_id: Number(item.insumo.id),
          quantidade: item.quantidade,
        })),
      });
      onCreated(criado);
      setItens([]);
      setPreco(0);
      event.currentTarget.reset();
      setAviso(`Prato “${criado.nome}” e ficha técnica cadastrados.`);
    } catch {
      setErro("Não foi possível salvar o prato e a ficha técnica.");
    } finally {
      setBusy(false);
    }
  }

  async function consultarFicha() {
    if (!produtoConsultaId) return;
    setBusy(true);
    setErro(null);
    try {
      setFichaConsultada(await obterFichaProduto(produtoConsultaId));
    } catch {
      setErro("Não foi possível consultar a ficha deste produto.");
    } finally {
      setBusy(false);
    }
  }

  async function importarCardapio() {
    if (fonteImportacao === "arquivo" && !arquivoCardapio) {
      setErro("Envie uma imagem ou um PDF do cardápio.");
      return;
    }
    if (fonteImportacao === "texto" && !textoCardapio.trim()) {
      setErro("Cole o texto do cardápio.");
      return;
    }

    setImportando(true);
    setErro(null);
    setAviso(null);
    try {
      const resultado = fonteImportacao === "arquivo"
        ? await importarCardapioGeminiPorArquivo(arquivoCardapio as File)
        : await importarCardapioGeminiPorTexto(textoCardapio);
      setAviso(
        `${resultado.qtd_cadastrados} pratos foram extraídos pelo Gemini e salvos diretamente no cardápio.`,
      );
      onImported();
    } catch {
      setErro("Não foi possível processar o cardápio com IA.");
    } finally {
      setImportando(false);
    }
  }

  return (
    <>
      <section className="mt-6 rounded-2xl border border-white/10 bg-zinc-900/70 p-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-white">
            <Sparkles className="size-5 text-violet-300" /> Importação automática via Gemini
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Carregue o cardápio oficial para extrair e cadastrar os pratos no menu.
          </p>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="button" variant={fonteImportacao === "arquivo" ? "default" : "outline"} onClick={() => setFonteImportacao("arquivo")}>
            <Upload /> Imagem ou PDF
          </Button>
          <Button type="button" variant={fonteImportacao === "texto" ? "default" : "outline"} onClick={() => setFonteImportacao("texto")}>
            <BookOpen /> Colar texto
          </Button>
        </div>

        {fonteImportacao === "arquivo" ? (
          <label className="mt-4 block text-xs font-semibold text-slate-400">
            Arquivo do cardápio
            <input
              type="file"
              accept="image/png,image/jpeg,application/pdf"
              onChange={(event) => setArquivoCardapio(event.target.files?.[0] ?? null)}
              className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-violet-500/20 file:px-3 file:py-1 file:text-violet-200"
            />
          </label>
        ) : (
          <label className="mt-4 block text-xs font-semibold text-slate-400">
            Texto do cardápio
            <textarea
              value={textoCardapio}
              onChange={(event) => setTextoCardapio(event.target.value)}
              rows={5}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            />
          </label>
        )}

        <Button type="button" className="mt-4" onClick={() => void importarCardapio()} disabled={importando}>
          {importando ? <LoaderCircle className="animate-spin" /> : <Sparkles />}
          Processar Cardápio com IA
        </Button>
      </section>

      <section className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(340px,1fr)]">
      <form onSubmit={(event) => void salvar(event)} className="rounded-2xl border border-white/10 bg-zinc-900/70 p-5">
        <div className="mb-5 flex items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-bold text-white">
              <BookOpen className="size-5 text-sky-300" /> Engenharia de Cardápio
            </h2>
            <p className="mt-1 text-sm text-slate-400">
              Monte o prato exclusivamente com insumos da unidade ativa.
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={() => void carregarInsumos()} disabled={loading || busy}>
            <RefreshCw className={loading ? "animate-spin" : ""} />
          </Button>
        </div>

        {erro ? <p className="mb-4 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">{erro}</p> : null}
        {aviso ? <p className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{aviso}</p> : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs font-semibold text-slate-400">
            Nome do prato
            <input name="nome" required className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white" />
          </label>
          <label className="text-xs font-semibold text-slate-400">
            Categoria
            <input name="categoria" required list="categorias-cardapio" className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white" />
            <datalist id="categorias-cardapio">{categorias.map((categoria) => <option key={categoria} value={categoria} />)}</datalist>
          </label>
          <label className="text-xs font-semibold text-slate-400 sm:col-span-2">
            Descrição / ingredientes
            <textarea name="descricao" rows={2} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white" />
          </label>
        </div>

        <div className="mt-5 grid gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-4 md:grid-cols-[minmax(0,1fr)_160px_auto] md:items-end">
          <label className="text-xs font-semibold text-slate-400">
            Insumo do almoxarifado
            <select value={insumoId} onChange={(event) => setInsumoId(event.target.value)} disabled={loading || insumos.length === 0} className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white">
              {insumos.length === 0 ? <option value="">Nenhum insumo disponível</option> : null}
              {insumos.map((insumo) => (
                <option key={insumo.id} value={insumo.id}>
                  {insumo.nome} · {moeda(insumo.custo_unitario)}/{insumo.unidade_medida}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-400">
            Quantidade
            <input type="number" min="0.1" step="0.1" value={quantidade} onChange={(event) => setQuantidade(Number(event.target.value))} className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white" />
          </label>
          <Button type="button" onClick={adicionarItem} disabled={!insumoId || quantidade <= 0}>
            <Plus /> Adicionar
          </Button>
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border border-slate-800">
          {itens.length === 0 ? (
            <p className="p-5 text-center text-sm text-slate-500">A receita ainda não possui insumos.</p>
          ) : (
            <div className="divide-y divide-slate-800">
              {itens.map((item, index) => (
                <div key={`${item.insumo.id}-${index}`} className="flex items-center justify-between gap-3 px-4 py-3 text-sm">
                  <div>
                    <p className="font-semibold text-white">{item.insumo.nome}</p>
                    <p className="text-xs text-slate-500">{item.quantidade} {item.unidadeExibicao} · {moeda(item.custo)}</p>
                  </div>
                  <Button type="button" variant="ghost" size="icon" onClick={() => setItens((current) => current.filter((_, itemIndex) => itemIndex !== index))}>
                    <Trash2 className="size-4 text-red-300" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-4">
          <div className="rounded-xl bg-slate-950/60 p-3"><p className="text-xs text-slate-500">CMV</p><p className="mt-1 font-bold text-white">{moeda(cmv)}</p></div>
          <label className="text-xs font-semibold text-slate-400">Margem desejada (%)<input type="number" min="5" max="300" step="5" value={margem} onChange={(event) => setMargem(Number(event.target.value))} className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white" /></label>
          <label className="text-xs font-semibold text-slate-400">Preço final (R$)<input type="number" min="0" step="0.01" value={preco} onChange={(event) => setPreco(Number(event.target.value))} className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white" /></label>
          <div className="rounded-xl bg-slate-950/60 p-3"><p className="text-xs text-slate-500">Sugestão / margem real</p><p className="mt-1 font-bold text-white">{moeda(sugestao)} · {margemReal.toFixed(1)}%</p></div>
        </div>

        <Button type="submit" className="mt-5 w-full" disabled={busy || itens.length === 0 || preco < 0}>
          {busy ? <LoaderCircle className="animate-spin" /> : <BookOpen />} Salvar prato e ficha técnica
        </Button>
      </form>

      <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-5">
        <h2 className="font-bold text-white">Fichas vinculadas</h2>
        <p className="mt-1 text-sm text-slate-400">Consulte a composição já persistida de um produto.</p>
        <select value={produtoConsultaId} onChange={(event) => setProdutoConsultaId(event.target.value)} className="mt-4 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white">
          <option value="">Selecione um produto</option>
          {produtos.map((produto) => <option key={produto.id} value={produto.id}>{produto.nome}</option>)}
        </select>
        <Button type="button" variant="outline" className="mt-3 w-full" onClick={() => void consultarFicha()} disabled={!produtoConsultaId || busy}>Consultar ficha</Button>

        {fichaConsultada ? (
          <div className="mt-5 space-y-3">
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <p className="font-semibold text-white">{fichaConsultada.produto.nome}</p>
              <p className="mt-1 text-xs text-slate-500">CMV {moeda(fichaConsultada.custo_total_cmv)} · {fichaConsultada.margem_exibicao || "margem não informada"}</p>
            </div>
            {fichaConsultada.itens.length === 0 ? <p className="text-sm text-slate-500">Produto sem ficha técnica vinculada.</p> : fichaConsultada.itens.map((item) => (
              <div key={item.id} className="flex justify-between gap-3 border-b border-slate-800 pb-3 text-sm">
                <span className="text-slate-300">{item.insumo_nome}<span className="block text-xs text-slate-500">{item.quantidade} {item.unidade_medida}</span></span>
                <span className="font-mono text-slate-400">{moeda(item.custo_item)}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      </section>
    </>
  );
}
