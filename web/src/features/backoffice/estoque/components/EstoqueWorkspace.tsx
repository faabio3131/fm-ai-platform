"use client";

import {
  BrainCircuit,
  CalendarClock,
  LoaderCircle,
  PackagePlus,
  RefreshCw,
  Trash2,
  Warehouse,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  aplicarLeituraEstoque,
  criarInsumo,
  executarForecastingAlertas,
  excluirInsumo,
  EstoqueApiError,
  listarEstoque,
  type EstoqueInsumo,
} from "@/features/backoffice/estoque/services/estoque-api";

const UNIDADES = ["kg", "g", "L", "ml", "un", "cx", "fatias"] as const;

function mensagemErro(error: unknown): string {
  if (error instanceof EstoqueApiError) {
    if (error.status === 401) return "Sua sessão não está mais válida.";
    if (error.status === 403) return "Seu perfil não pode operar o estoque desta unidade.";
    if (error.code === "estoque.escopo_indisponivel") {
      return "A unidade ativa ainda não possui almoxarifado legado vinculado.";
    }
    if (error.code === "estoque.integridade_impede_operacao") {
      return "Este insumo possui vínculos que impedem a exclusão.";
    }
  }
  return "Não foi possível concluir a operação de estoque.";
}

function moeda(valor: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(valor);
}

function data(valor: string | null): string {
  if (!valor) return "N/A";
  return new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC" }).format(
    new Date(valor),
  );
}

export function EstoqueWorkspace() {
  const auth = useAuthStore();
  const [itens, setItens] = useState<EstoqueInsumo[]>([]);
  const [valorTotal, setValorTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [resultadoForecasting, setResultadoForecasting] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const resumo = await listarEstoque();
      setItens(resumo.itens);
      setValorTotal(resumo.valor_total);
    } catch (error) {
      setErro(mensagemErro(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId) return;
    const timeoutId = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, carregar]);

  const reposicao = useMemo(
    () => itens.filter((item) => item.status_estoque === "reposicao").length,
    [itens],
  );
  const validadeAtencao = useMemo(
    () =>
      itens.filter(
        (item) =>
          !item.status_validade.toLocaleLowerCase("pt-BR").includes("segura") &&
          !item.status_validade.toLocaleLowerCase("pt-BR").includes("sem validade"),
      ).length,
    [itens],
  );

  async function operar(acao: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setErro(null);
    setAviso(null);
    try {
      await acao();
      await carregar();
    } catch (error) {
      setErro(mensagemErro(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 p-4 text-slate-100 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-300">
              Retaguarda · Unidade ativa
            </p>
            <h1 className="mt-2 text-3xl font-black tracking-tight">Estoque e Validades</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              Almoxarifado, saldo, custo, mínimo e validade conforme a operação original do Kordena.
            </p>
          </div>
          <Button variant="outline" onClick={() => void carregar()} disabled={loading || busy}>
            <RefreshCw className={loading ? "animate-spin" : ""} />
            Atualizar
          </Button>
        </header>

        <section className="grid gap-3 md:grid-cols-4">
          <Metric label="Insumos" value={String(itens.length)} />
          <Metric label="Valor em estoque" value={moeda(valorTotal)} />
          <Metric label="Reposição" value={String(reposicao)} attention={reposicao > 0} />
          <Metric
            label="Validade em atenção"
            value={String(validadeAtencao)}
            attention={validadeAtencao > 0}
          />
        </section>

        {erro ? (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {erro}
          </div>
        ) : null}
        {aviso ? (
          <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
            {aviso}
          </div>
        ) : null}

        <section className="rounded-2xl border border-violet-400/20 bg-violet-500/5 p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="flex items-center gap-2 font-bold text-white">
                <BrainCircuit className="size-5 text-violet-300" /> Forecasting preditivo e alertas
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                Analise estoque e validades e dispare os alertas configurados da unidade.
              </p>
            </div>
            <Button
              type="button"
              disabled={busy}
              onClick={() => void operar(async () => {
                const resultado = await executarForecastingAlertas();
                setResultadoForecasting(resultado.mensagem);
              })}
            >
              {busy ? <LoaderCircle className="animate-spin" /> : <BrainCircuit />}
              Executar varredura agora
            </Button>
          </div>
          {resultadoForecasting ? (
            <p className="mt-4 rounded-xl border border-violet-300/20 bg-slate-950/50 p-3 text-sm text-slate-200">
              {resultadoForecasting}
            </p>
          ) : null}
        </section>

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(340px,1fr)]">
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
            <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3">
              <Warehouse className="size-5 text-blue-400" />
              <h2 className="font-bold">Status do almoxarifado</h2>
            </div>
            {loading ? (
              <div className="flex min-h-64 items-center justify-center gap-2 text-sm text-slate-400">
                <LoaderCircle className="size-5 animate-spin" /> Carregando estoque…
              </div>
            ) : itens.length === 0 ? (
              <div className="flex min-h-64 items-center justify-center text-sm text-slate-400">
                Nenhum insumo cadastrado nesta unidade.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[920px] text-left text-sm">
                  <thead className="bg-slate-950/70 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3">Insumo</th>
                      <th className="px-4 py-3">Saldo / mínimo</th>
                      <th className="px-4 py-3">Custo / total</th>
                      <th className="px-4 py-3">Validade</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-right">Ação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {itens.map((item) => (
                      <tr key={item.id} className="text-slate-300">
                        <td className="px-4 py-3 font-semibold text-white">{item.nome}</td>
                        <td className="px-4 py-3 tabular-nums">
                          {item.saldo_atual} {item.unidade_medida}
                          <span className="block text-xs text-slate-500">
                            mínimo {item.estoque_minimo} {item.unidade_medida}
                          </span>
                        </td>
                        <td className="px-4 py-3 tabular-nums">
                          {moeda(item.custo_unitario)}
                          <span className="block text-xs text-slate-500">
                            {moeda(item.valor_total)} total
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {data(item.data_validade)}
                          <span className="block text-xs text-slate-500">
                            {item.status_validade}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`rounded-full px-2 py-1 text-xs font-bold ${
                              item.status_estoque === "ok"
                                ? "bg-emerald-500/10 text-emerald-300"
                                : "bg-red-500/10 text-red-300"
                            }`}
                          >
                            {item.status_estoque === "ok" ? "OK" : "Reposição"}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            aria-label={`Excluir ${item.nome}`}
                            disabled={busy}
                            onClick={() => {
                              if (!window.confirm(`Excluir o insumo “${item.nome}”?`)) return;
                              void operar(async () => {
                                await excluirInsumo(item.id);
                                setAviso(`Insumo “${item.nome}” excluído.`);
                              });
                            }}
                          >
                            <Trash2 className="size-4 text-red-300" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="space-y-6">
            <NovoInsumoForm
              busy={busy}
              onSubmit={(payload) =>
                operar(async () => {
                  const criado = await criarInsumo(payload);
                  setAviso(`Insumo “${criado.nome}” cadastrado no almoxarifado.`);
                })
              }
            />
            <LeituraForm
              busy={busy}
              onSubmit={(item) =>
                operar(async () => {
                  const resultado = await aplicarLeituraEstoque([item]);
                  setAviso(`${resultado.processados} item(ns) da leitura aplicado(s).`);
                })
              }
            />
          </div>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value, attention = false }: { label: string; value: string; attention?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-2 text-2xl font-black tabular-nums ${attention ? "text-amber-300" : "text-white"}`}>
        {value}
      </p>
    </div>
  );
}

function NovoInsumoForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (payload: Parameters<typeof criarInsumo>[0]) => Promise<void>;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSubmit({
      nome: String(form.get("nome") || "").trim(),
      unidade_medida: String(form.get("unidade_medida") || "un"),
      saldo_atual: Number(form.get("saldo_atual") || 0),
      estoque_minimo: Number(form.get("estoque_minimo") || 0),
      custo_unitario: Number(form.get("custo_unitario") || 0),
      data_fabricacao: String(form.get("data_fabricacao") || "") || null,
      data_validade: String(form.get("data_validade") || "") || null,
      dias_alerta_vencimento: Number(form.get("dias_alerta_vencimento") || 15),
    });
    event.currentTarget.reset();
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-4 flex items-center gap-2">
        <PackagePlus className="size-5 text-blue-400" />
        <h2 className="font-bold">Cadastrar insumo</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field name="nome" label="Nome" required className="sm:col-span-2" />
        <label className="text-xs font-semibold text-slate-400">
          Unidade
          <select name="unidade_medida" className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white">
            {UNIDADES.map((unidade) => <option key={unidade}>{unidade}</option>)}
          </select>
        </label>
        <Field name="saldo_atual" label="Quantidade inicial" type="number" min="0" step="0.001" required />
        <Field name="estoque_minimo" label="Estoque mínimo" type="number" min="0" step="0.001" defaultValue="10" required />
        <Field name="custo_unitario" label="Custo unitário (R$)" type="number" min="0" step="0.01" required />
        <Field name="dias_alerta_vencimento" label="Alerta (dias)" type="number" min="1" defaultValue="15" required />
        <Field name="data_fabricacao" label="Fabricação" type="date" />
        <Field name="data_validade" label="Validade" type="date" />
      </div>
      <Button type="submit" className="mt-4 w-full" disabled={busy}>Salvar no almoxarifado</Button>
    </form>
  );
}

function LeituraForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (item: Parameters<typeof aplicarLeituraEstoque>[0][number]) => Promise<void>;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await onSubmit({
      nome: String(form.get("nome") || "").trim(),
      quantidade: Number(form.get("quantidade") || 0),
      unidade: String(form.get("unidade") || "un"),
      data_validade: String(form.get("data_validade") || "") || null,
    });
    event.currentTarget.reset();
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-2 flex items-center gap-2">
        <CalendarClock className="size-5 text-violet-400" />
        <h2 className="font-bold">Aplicar leitura de entrada</h2>
      </div>
      <p className="mb-4 text-xs leading-5 text-slate-500">
        Registra a leitura já conferida: soma ao insumo existente ou cria um novo item, como no fluxo original.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field name="nome" label="Insumo" required className="sm:col-span-2" />
        <Field name="quantidade" label="Quantidade" type="number" min="0.001" step="0.001" required />
        <label className="text-xs font-semibold text-slate-400">
          Unidade
          <select name="unidade" className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white">
            {UNIDADES.map((unidade) => <option key={unidade}>{unidade}</option>)}
          </select>
        </label>
        <Field name="data_validade" label="Validade" type="date" className="sm:col-span-2" />
      </div>
      <Button type="submit" variant="outline" className="mt-4 w-full" disabled={busy}>
        Aplicar leitura
      </Button>
    </form>
  );
}

function Field({ label, className = "", ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className={`text-xs font-semibold text-slate-400 ${className}`}>
      {label}
      <input {...props} className="mt-1 h-10 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white outline-none focus:border-blue-500" />
    </label>
  );
}
