"use client";

import {
  Building2,
  CircleDollarSign,
  Layers3,
  LoaderCircle,
  PackageCheck,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { CatalogoTable } from "@/features/backoffice/catalogo/components/CatalogoTable";
import { NovoProdutoModal } from "@/features/backoffice/catalogo/components/NovoProdutoModal";
import {
  CatalogoApiError,
  atualizarProduto,
  listarCategorias,
  listarProdutos,
  type CatalogoProduto,
} from "@/features/backoffice/catalogo/services/catalogo-api";
import { getUnits, type AuthUnit } from "@/features/auth/services/auth-api";
import { useAuthStore } from "@/features/auth/store/auth-store";

function describeError(error: unknown): string {
  if (error instanceof CatalogoApiError) {
    if (error.status === 401) return "Sua sessão não está mais válida.";
    if (error.status === 403) return "Seu perfil não possui acesso ao catálogo desta unidade.";
    if (error.code === "catalogo.escopo_indisponivel") {
      return "A unidade ativa ainda não possui um escopo de catálogo disponível.";
    }
  }
  return "Não foi possível carregar o catálogo agora.";
}

export function CatalogoWorkspace() {
  const auth = useAuthStore();
  const [produtos, setProdutos] = useState<CatalogoProduto[]>([]);
  const [categorias, setCategorias] = useState<string[]>([]);
  const [unidades, setUnidades] = useState<AuthUnit[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [updatingIds, setUpdatingIds] = useState<ReadonlySet<string>>(new Set());

  const carregar = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    setErro(null);

    try {
      const [produtosResult, categoriasResult, unidadesResult] = await Promise.all([
        listarProdutos(undefined, false),
        listarCategorias(),
        getUnits().catch(() => [] as AuthUnit[]),
      ]);
      setProdutos(produtosResult);
      setCategorias(categoriasResult);
      setUnidades(unidadesResult);
    } catch (error: unknown) {
      setErro(describeError(error));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status === "authenticated") {
      void carregar();
    }
  }, [auth.status, auth.unitId, carregar]);

  const unidadeAtiva = useMemo(
    () => unidades.find((unidade) => unidade.id === auth.unitId),
    [auth.unitId, unidades],
  );

  const ativos = useMemo(
    () => produtos.reduce((total, produto) => total + (produto.ativo ? 1 : 0), 0),
    [produtos],
  );

  const precoMedio = useMemo(() => {
    if (!produtos.length) return 0;
    return produtos.reduce((total, produto) => total + produto.preco, 0) / produtos.length;
  }, [produtos]);

  const handleToggleAtivo = async (produto: CatalogoProduto, ativo: boolean) => {
    const anterior = produto.ativo;
    setErro(null);
    setProdutos((current) =>
      current.map((item) => (item.id === produto.id ? { ...item, ativo } : item)),
    );
    setUpdatingIds((current) => new Set(current).add(produto.id));

    try {
      const atualizado = await atualizarProduto(produto.id, { ativo });
      setProdutos((current) =>
        current.map((item) => (item.id === atualizado.id ? atualizado : item)),
      );
    } catch (error: unknown) {
      setProdutos((current) =>
        current.map((item) =>
          item.id === produto.id ? { ...item, ativo: anterior } : item,
        ),
      );
      setErro(describeError(error));
    } finally {
      setUpdatingIds((current) => {
        const next = new Set(current);
        next.delete(produto.id);
        return next;
      });
    }
  };

  const handleCreated = (produto: CatalogoProduto) => {
    setProdutos((current) => [produto, ...current]);
    if (produto.categoria && !categorias.includes(produto.categoria)) {
      setCategorias((current) =>
        [...current, produto.categoria].sort((a, b) => a.localeCompare(b, "pt-BR")),
      );
    }
  };

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="pointer-events-none fixed inset-x-0 top-0 h-80 bg-[radial-gradient(circle_at_top,rgba(14,165,233,0.12),transparent_60%)]" />

      <div className="relative mx-auto w-full max-w-[1500px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <header className="mb-6 flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-sky-400/20 bg-sky-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-sky-200">
                <Sparkles className="size-3" />
                Kordena Backoffice
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/20 bg-emerald-400/[0.08] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                <ShieldCheck className="size-3" />
                Sessão protegida
              </span>
            </div>
            <h1 className="text-2xl font-semibold tracking-[-0.03em] text-white sm:text-3xl">
              Catálogo & Cardápio
            </h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
              Gestão operacional do portfólio da unidade ativa, com disponibilidade em tempo real e contratos canônicos do Kordena V1.
            </p>
          </div>

          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              disabled={refreshing || loading}
              onClick={() => void carregar(true)}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.04] px-4 text-sm font-medium text-slate-300 transition hover:bg-white/[0.07] hover:text-white active:scale-[0.98] disabled:cursor-wait disabled:opacity-60"
            >
              <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} />
              Atualizar
            </button>
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-sky-500 px-4 text-sm font-semibold text-slate-950 shadow-lg shadow-sky-950/30 transition hover:bg-sky-400 active:scale-[0.98]"
            >
              <Plus className="size-4" />
              Novo produto
            </button>
          </div>
        </header>

        <section className="mb-6 grid gap-3 lg:grid-cols-[1.25fr_repeat(3,minmax(0,1fr))]">
          <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4 shadow-xl shadow-black/10 backdrop-blur-xl">
            <div className="flex items-start gap-3">
              <div className="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-sky-300">
                <Building2 className="size-5" />
              </div>
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                  Unidade ativa
                </p>
                <p className="mt-1 truncate text-sm font-semibold text-white">
                  {unidadeAtiva?.nome || unidadeAtiva?.codigo || "Unidade selecionada"}
                </p>
                <p className="mt-1 truncate font-mono text-[11px] tabular-nums text-slate-500">
                  {auth.unitId || "—"}
                </p>
              </div>
            </div>
          </div>

          <MetricCard
            icon={<PackageCheck className="size-5" />}
            label="Produtos"
            value={String(produtos.length)}
            detail={`${ativos} ativos`}
          />
          <MetricCard
            icon={<Layers3 className="size-5" />}
            label="Categorias"
            value={String(categorias.length)}
            detail="nesta unidade"
          />
          <MetricCard
            icon={<CircleDollarSign className="size-5" />}
            label="Preço médio"
            value={new Intl.NumberFormat("pt-BR", {
              style: "currency",
              currency: "BRL",
            }).format(precoMedio)}
            detail="portfólio atual"
            mono
          />
        </section>

        {erro ? (
          <div className="mb-4 flex items-center justify-between gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/[0.08] px-4 py-3 text-sm text-rose-100">
            <span>{erro}</span>
            <button
              type="button"
              onClick={() => void carregar(true)}
              className="shrink-0 rounded-lg border border-rose-300/20 px-3 py-1.5 text-xs font-semibold transition hover:bg-rose-300/10 active:scale-[0.98]"
            >
              Tentar novamente
            </button>
          </div>
        ) : null}

        {loading ? (
          <div className="flex min-h-72 items-center justify-center rounded-3xl border border-white/10 bg-zinc-900/60">
            <div className="flex items-center gap-3 text-sm text-slate-400">
              <LoaderCircle className="size-5 animate-spin text-sky-300" />
              Carregando catálogo da unidade…
            </div>
          </div>
        ) : (
          <CatalogoTable
            produtos={produtos}
            categorias={categorias}
            updatingIds={updatingIds}
            onToggleAtivo={(produto, ativo) => void handleToggleAtivo(produto, ativo)}
          />
        )}
      </div>

      <NovoProdutoModal
        open={modalOpen}
        categorias={categorias}
        onClose={() => setModalOpen(false)}
        onCreated={handleCreated}
      />
    </main>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
  mono = false,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  mono?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-zinc-900/70 p-4 shadow-xl shadow-black/10 backdrop-blur-xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            {label}
          </p>
          <p
            className={`mt-2 text-xl font-semibold tracking-tight text-white ${
              mono ? "font-mono tabular-nums" : "tabular-nums"
            }`}
          >
            {value}
          </p>
          <p className="mt-1 text-[11px] text-slate-500">{detail}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-2.5 text-slate-400">
          {icon}
        </div>
      </div>
    </div>
  );
}
