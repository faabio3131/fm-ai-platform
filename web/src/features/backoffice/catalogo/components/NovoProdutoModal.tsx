"use client";

import { Check, LoaderCircle, PackagePlus, X } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";

import {
  CatalogoApiError,
  criarProduto,
  type CatalogoProduto,
} from "@/features/backoffice/catalogo/services/catalogo-api";

interface NovoProdutoModalProps {
  open: boolean;
  categorias: string[];
  onClose: () => void;
  onCreated: (produto: CatalogoProduto) => void;
}

function parsePrecoBRL(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;

  const normalized = trimmed.includes(",")
    ? trimmed.replace(/\./g, "").replace(",", ".")
    : trimmed;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function mensagemErro(error: unknown): string {
  if (error instanceof CatalogoApiError) {
    if (error.status === 403) {
      return "Seu perfil não possui permissão para alterar o catálogo.";
    }
    if (error.status === 401) {
      return "Sua sessão expirou. Entre novamente para continuar.";
    }
    return error.code
      ? `Não foi possível cadastrar o produto (${error.code}).`
      : "Não foi possível cadastrar o produto.";
  }
  return "Não foi possível cadastrar o produto.";
}

export function NovoProdutoModal({
  open,
  categorias,
  onClose,
  onCreated,
}: NovoProdutoModalProps) {
  const titleId = useId();
  const categoryListId = useId();
  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState("");
  const [preco, setPreco] = useState("");
  const [ativo, setAtivo] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open, submitting]);

  useEffect(() => {
    if (open) {
      setErro(null);
    }
  }, [open]);

  if (!open) return null;

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setErro(null);

    const nomeNormalizado = nome.trim();
    const categoriaNormalizada = categoria.trim();
    const precoNumerico = parsePrecoBRL(preco);

    if (!nomeNormalizado || !categoriaNormalizada || precoNumerico === null) {
      setErro("Preencha nome, categoria e preço com valores válidos.");
      return;
    }

    setSubmitting(true);
    try {
      const produto = await criarProduto({
        nome: nomeNormalizado,
        categoria: categoriaNormalizada,
        preco: precoNumerico,
        ativo,
      });
      onCreated(produto);
      setNome("");
      setCategoria("");
      setPreco("");
      setAtivo(true);
      onClose();
    } catch (error: unknown) {
      setErro(mensagemErro(error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-md"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target && !submitting) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="w-full max-w-xl overflow-hidden rounded-3xl border border-white/10 bg-zinc-900/95 shadow-2xl shadow-black/60"
      >
        <div className="flex items-start justify-between border-b border-white/10 px-5 py-5 sm:px-6">
          <div className="flex gap-3">
            <div className="rounded-2xl border border-sky-400/20 bg-sky-400/10 p-2.5 text-sky-300">
              <PackagePlus className="size-5" />
            </div>
            <div>
              <h2 id={titleId} className="text-lg font-semibold tracking-tight text-white">
                Novo produto
              </h2>
              <p className="mt-1 text-xs leading-5 text-slate-400">
                O item será criado somente na unidade ativa e protegido por idempotência.
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Fechar cadastro"
            disabled={submitting}
            onClick={onClose}
            className="rounded-xl border border-white/10 p-2 text-slate-400 transition hover:bg-white/[0.06] hover:text-white active:scale-[0.98] disabled:opacity-50"
          >
            <X className="size-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5 p-5 sm:p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="sm:col-span-2">
              <span className="mb-2 block text-xs font-medium text-slate-300">Nome</span>
              <input
                autoFocus
                value={nome}
                onChange={(event) => setNome(event.target.value)}
                maxLength={240}
                placeholder="Ex.: Smash Bacon"
                className="h-11 w-full rounded-xl border border-white/10 bg-slate-950/70 px-3.5 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-sky-400/50 focus:ring-2 focus:ring-sky-400/10"
              />
            </label>

            <label>
              <span className="mb-2 block text-xs font-medium text-slate-300">Categoria</span>
              <input
                list={categoryListId}
                value={categoria}
                onChange={(event) => setCategoria(event.target.value)}
                maxLength={160}
                placeholder="Ex.: Lanches"
                className="h-11 w-full rounded-xl border border-white/10 bg-slate-950/70 px-3.5 text-sm text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-sky-400/50 focus:ring-2 focus:ring-sky-400/10"
              />
              <datalist id={categoryListId}>
                {categorias.map((item) => (
                  <option key={item} value={item} />
                ))}
              </datalist>
            </label>

            <label>
              <span className="mb-2 block text-xs font-medium text-slate-300">Preço</span>
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-xs tabular-nums text-slate-500">
                  R$
                </span>
                <input
                  inputMode="decimal"
                  value={preco}
                  onChange={(event) => setPreco(event.target.value)}
                  placeholder="0,00"
                  className="h-11 w-full rounded-xl border border-white/10 bg-slate-950/70 pl-9 pr-3.5 font-mono text-sm tabular-nums text-slate-100 outline-none transition placeholder:text-slate-600 focus:border-sky-400/50 focus:ring-2 focus:ring-sky-400/10"
                />
              </div>
            </label>
          </div>

          <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/50 p-4">
            <div>
              <p className="text-sm font-medium text-slate-200">Disponível ao criar</p>
              <p className="mt-1 text-xs text-slate-500">
                Você poderá alterar este status diretamente na tabela.
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={ativo}
              onClick={() => setAtivo((valor) => !valor)}
              className={`relative h-7 w-12 rounded-full border transition active:scale-[0.98] ${
                ativo
                  ? "border-emerald-300/30 bg-emerald-500/80"
                  : "border-white/10 bg-slate-700"
              }`}
            >
              <span
                className={`absolute top-0.5 size-6 rounded-full bg-white shadow-md transition-transform ${
                  ativo ? "translate-x-[22px]" : "translate-x-0.5"
                }`}
              />
            </button>
          </div>

          {erro ? (
            <div className="rounded-2xl border border-rose-400/20 bg-rose-400/10 px-4 py-3 text-xs leading-5 text-rose-200">
              {erro}
            </div>
          ) : null}

          <div className="flex flex-col-reverse gap-2 border-t border-white/10 pt-5 sm:flex-row sm:justify-end">
            <button
              type="button"
              disabled={submitting}
              onClick={onClose}
              className="h-10 rounded-xl border border-white/10 bg-white/[0.03] px-4 text-sm font-medium text-slate-300 transition hover:bg-white/[0.07] active:scale-[0.98] disabled:opacity-50"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-xl bg-sky-500 px-4 text-sm font-semibold text-slate-950 shadow-lg shadow-sky-950/40 transition hover:bg-sky-400 active:scale-[0.98] disabled:cursor-wait disabled:opacity-70"
            >
              {submitting ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <Check className="size-4" />
              )}
              {submitting ? "Salvando…" : "Criar produto"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
