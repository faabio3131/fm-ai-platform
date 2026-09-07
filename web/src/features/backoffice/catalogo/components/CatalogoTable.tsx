"use client";

import {
  Check,
  LoaderCircle,
  PackageOpen,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { CatalogoProduto } from "@/features/backoffice/catalogo/services/catalogo-api";

interface CatalogoTableProps {
  produtos: CatalogoProduto[];
  categorias: string[];
  updatingIds: ReadonlySet<string>;
  onToggleAtivo: (produto: CatalogoProduto, ativo: boolean) => void;
}

const moedaBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function AvailabilitySwitch({
  produto,
  loading,
  onToggle,
}: {
  produto: CatalogoProduto;
  loading: boolean;
  onToggle: (ativo: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={produto.ativo}
      aria-label={`${produto.ativo ? "Desativar" : "Ativar"} ${produto.nome}`}
      disabled={loading}
      onClick={() => onToggle(!produto.ativo)}
      className="group inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-2 py-1.5 text-xs font-medium text-slate-300 shadow-sm transition duration-200 hover:border-white/20 hover:bg-white/[0.07] active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
    >
      <span
        className={`relative h-5 w-9 rounded-full transition-colors duration-200 ${
          produto.ativo ? "bg-emerald-500/80" : "bg-slate-700"
        }`}
      >
        <span
          className={`absolute top-0.5 size-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
            produto.ativo ? "translate-x-[18px]" : "translate-x-0.5"
          }`}
        />
      </span>
      <span className="min-w-[50px] text-left">
        {produto.ativo ? "Ativo" : "Inativo"}
      </span>
      {loading ? (
        <LoaderCircle className="size-3.5 animate-spin text-sky-300" />
      ) : produto.ativo ? (
        <Check className="size-3.5 text-emerald-300" />
      ) : null}
    </button>
  );
}

export function CatalogoTable({
  produtos,
  categorias,
  updatingIds,
  onToggleAtivo,
}: CatalogoTableProps) {
  const [busca, setBusca] = useState("");
  const [categoria, setCategoria] = useState("todas");
  const [somenteAtivos, setSomenteAtivos] = useState(false);

  const produtosFiltrados = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");

    return produtos.filter((produto) => {
      const correspondeBusca =
        !termo || produto.nome.toLocaleLowerCase("pt-BR").includes(termo);
      const correspondeCategoria =
        categoria === "todas" || produto.categoria === categoria;
      const correspondeStatus = !somenteAtivos || produto.ativo;
      return correspondeBusca && correspondeCategoria && correspondeStatus;
    });
  }, [busca, categoria, produtos, somenteAtivos]);

  return (
    <section className="overflow-hidden rounded-3xl border border-white/10 bg-zinc-900/70 shadow-2xl shadow-black/20 backdrop-blur-xl">
      <div className="border-b border-white/10 px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="text-sm font-semibold text-white">Produtos do cardápio</p>
            <p className="mt-1 text-xs text-slate-400">
              {produtosFiltrados.length} de {produtos.length} itens visíveis
            </p>
          </div>

          <div className="grid gap-2 sm:grid-cols-[minmax(220px,1fr)_190px_auto]">
            <label className="relative block">
              <span className="sr-only">Buscar produto</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
              <input
                type="search"
                value={busca}
                onChange={(event) => setBusca(event.target.value)}
                placeholder="Buscar por nome…"
                className="h-10 w-full rounded-xl border border-white/10 bg-slate-950/70 pl-9 pr-3 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-sky-400/50 focus:ring-2 focus:ring-sky-400/10"
              />
            </label>

            <label className="relative block">
              <span className="sr-only">Filtrar por categoria</span>
              <SlidersHorizontal className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
              <select
                value={categoria}
                onChange={(event) => setCategoria(event.target.value)}
                className="h-10 w-full appearance-none rounded-xl border border-white/10 bg-slate-950/70 pl-9 pr-8 text-sm text-slate-200 outline-none transition focus:border-sky-400/50 focus:ring-2 focus:ring-sky-400/10"
              >
                <option value="todas">Todas as categorias</option>
                {categorias.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={() => setSomenteAtivos((valor) => !valor)}
              className={`h-10 rounded-xl border px-3 text-xs font-semibold transition active:scale-[0.98] ${
                somenteAtivos
                  ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
                  : "border-white/10 bg-white/[0.04] text-slate-400 hover:bg-white/[0.07]"
              }`}
            >
              Somente ativos
            </button>
          </div>
        </div>
      </div>

      {produtosFiltrados.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center px-6 text-center">
          <div className="mb-4 rounded-2xl border border-white/10 bg-white/[0.04] p-3">
            <PackageOpen className="size-6 text-slate-400" />
          </div>
          <p className="text-sm font-medium text-slate-200">Nenhum produto encontrado</p>
          <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
            Ajuste os filtros ou cadastre um novo item para esta unidade.
          </p>
        </div>
      ) : (
        <>
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-950/50 text-[11px] uppercase tracking-[0.18em] text-slate-500">
                <tr>
                  <th className="px-6 py-3 font-medium">Produto</th>
                  <th className="px-6 py-3 font-medium">Categoria</th>
                  <th className="px-6 py-3 text-right font-medium">Preço</th>
                  <th className="px-6 py-3 text-right font-medium">Disponibilidade</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.07]">
                {produtosFiltrados.map((produto) => (
                  <tr
                    key={produto.id}
                    className="transition-colors hover:bg-white/[0.025]"
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div
                          className={`size-2 rounded-full shadow-[0_0_12px_currentColor] ${
                            produto.ativo ? "text-emerald-400 bg-emerald-400" : "text-slate-600 bg-slate-600"
                          }`}
                        />
                        <div>
                          <p className="font-medium text-slate-100">{produto.nome}</p>
                          <p className="mt-0.5 font-mono text-[11px] tabular-nums text-slate-600">
                            ID {produto.id}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-slate-400">{produto.categoria}</td>
                    <td className="px-6 py-4 text-right font-mono font-semibold tabular-nums text-slate-100">
                      {moedaBRL.format(produto.preco)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <AvailabilitySwitch
                        produto={produto}
                        loading={updatingIds.has(produto.id)}
                        onToggle={(ativo) => onToggleAtivo(produto, ativo)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="divide-y divide-white/[0.07] md:hidden">
            {produtosFiltrados.map((produto) => (
              <article key={produto.id} className="space-y-4 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium text-slate-100">{produto.nome}</p>
                    <p className="mt-1 text-xs text-slate-500">{produto.categoria}</p>
                  </div>
                  <p className="font-mono text-sm font-semibold tabular-nums text-slate-100">
                    {moedaBRL.format(produto.preco)}
                  </p>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="font-mono text-[11px] tabular-nums text-slate-600">
                    ID {produto.id}
                  </span>
                  <AvailabilitySwitch
                    produto={produto}
                    loading={updatingIds.has(produto.id)}
                    onToggle={(ativo) => onToggleAtivo(produto, ativo)}
                  />
                </div>
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
