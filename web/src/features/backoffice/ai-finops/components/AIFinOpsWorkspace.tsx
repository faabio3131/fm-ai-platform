"use client";

import { BrainCircuit, Coins, Gauge, LoaderCircle, RefreshCw, Timer, Workflow } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  obterResumoAIFinOps,
  type AIFinOpsPainel,
} from "@/features/backoffice/ai-finops/services/ai-finops-api";

function dataIso(data: Date): string {
  return data.toISOString().slice(0, 10);
}

function periodoPadrao(): { inicio: string; fim: string } {
  const fim = new Date();
  const inicio = new Date(fim);
  inicio.setUTCDate(inicio.getUTCDate() - 29);
  return { inicio: dataIso(inicio), fim: dataIso(fim) };
}

function percentual(valor: string): string {
  return `${Number(valor).toFixed(1)}%`;
}

export function AIFinOpsWorkspace() {
  const auth = useAuthStore();
  const [periodo, setPeriodo] = useState(periodoPadrao);
  const [painel, setPainel] = useState<AIFinOpsPainel | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async (inicio: string, fim: string) => {
    setLoading(true);
    setErro(null);
    try {
      setPainel(await obterResumoAIFinOps(inicio, fim));
    } catch {
      setPainel(null);
      setErro("Não foi possível consultar os agregados AI FinOps desta unidade.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId) return;
    const timeoutId = window.setTimeout(
      () => void carregar(periodo.inicio, periodo.fim),
      0,
    );
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, carregar, periodo.fim, periodo.inicio]);

  function consultar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void carregar(periodo.inicio, periodo.fim);
  }

  const resumo = painel?.resumo;
  return (
    <main className="min-h-screen bg-slate-950 p-4 text-slate-100 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <header>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-300">
            Proprietário · Unidade ativa
          </p>
          <h1 className="mt-2 flex items-center gap-3 text-3xl font-black tracking-tight">
            <BrainCircuit className="size-8 text-violet-400" /> AI FinOps
          </h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-400">
            Uso, custo e eficiência calculados somente sobre agregados existentes. Esta tela não executa IA nem processa eventos brutos.
          </p>
        </header>

        <form onSubmit={consultar} className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 sm:flex-row sm:items-end">
          <label className="flex-1 text-xs font-semibold text-slate-400">
            Período inicial
            <Input type="date" value={periodo.inicio} onChange={(event) => setPeriodo((atual) => ({ ...atual, inicio: event.target.value }))} className="mt-1 border-slate-700 bg-slate-950 text-white" required />
          </label>
          <label className="flex-1 text-xs font-semibold text-slate-400">
            Período final
            <Input type="date" value={periodo.fim} onChange={(event) => setPeriodo((atual) => ({ ...atual, fim: event.target.value }))} className="mt-1 border-slate-700 bg-slate-950 text-white" required />
          </label>
          <Button type="submit" disabled={loading}>
            <RefreshCw className={loading ? "animate-spin" : ""} /> Consultar
          </Button>
        </form>

        {erro ? <div role="status" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{erro}</div> : null}

        {loading ? (
          <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-slate-400"><LoaderCircle className="size-5 animate-spin" /> Carregando agregados…</div>
        ) : resumo ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric icon={Workflow} label="Tentativas de IA" value={resumo.attempts.toLocaleString("pt-BR")} />
              <Metric icon={Gauge} label="Taxa de sucesso" value={percentual(resumo.success_rate_pct)} />
              <Metric icon={RefreshCw} label="Taxa de fallback" value={percentual(resumo.fallback_rate_pct)} />
              <Metric icon={Timer} label="Latência média" value={`${Number(resumo.latency_ms_average).toFixed(1)} ms`} />
              <Metric icon={BrainCircuit} label="Tokens de entrada" value={resumo.input_tokens.toLocaleString("pt-BR")} />
              <Metric icon={BrainCircuit} label="Tokens de saída" value={resumo.output_tokens.toLocaleString("pt-BR")} />
              <Metric icon={BrainCircuit} label="Tokens em cache" value={resumo.cached_tokens.toLocaleString("pt-BR")} />
              <Metric icon={Coins} label="Cobertura de custo" value={percentual(resumo.cost_coverage_pct)} />
            </section>

            {resumo.attempts === 0 ? (
              <p className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 text-sm text-slate-400">Ainda não existem agregados AI FinOps para este período e unidade.</p>
            ) : (
              <section className="grid gap-6 xl:grid-cols-2">
                <TablePanel title="Custo conhecido por moeda">
                  {resumo.custos.length === 0 ? (
                    <p className="text-sm text-amber-200">Nenhum evento do período possui custo conhecido.</p>
                  ) : resumo.custos.map((custo) => (
                    <DataRow key={custo.moeda} label={`${custo.moeda} · ${custo.eventos} evento(s)`} value={Number(custo.valor).toFixed(6)} />
                  ))}
                  {resumo.cost_unknown_events > 0 ? <p className="text-xs text-amber-200">{resumo.cost_unknown_events} tentativa(s) permanecem sem custo conhecido.</p> : null}
                </TablePanel>

                <TablePanel title="Mix de provider e modelo">
                  {resumo.mix.map((item) => (
                    <DataRow key={`${item.provider}-${item.model}`} label={`${item.provider} · ${item.model}`} value={item.attempts.toLocaleString("pt-BR")} />
                  ))}
                  <p className="text-xs text-slate-500">Falhas: {resumo.failure_attempts.toLocaleString("pt-BR")} · Fallbacks: {resumo.fallback_attempts.toLocaleString("pt-BR")} · Latência máxima: {resumo.latency_ms_max.toLocaleString("pt-BR")} ms</p>
                </TablePanel>
              </section>
            )}
          </>
        ) : null}
      </div>
    </main>
  );
}

function Metric({ icon: Icon, label, value }: { icon: typeof BrainCircuit; label: string; value: string }) {
  return <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4"><Icon className="size-5 text-violet-400" /><p className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p><p className="mt-2 text-2xl font-black tabular-nums text-white">{value}</p></div>;
}

function TablePanel({ title, children }: { title: string; children: ReactNode }) {
  return <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5"><h2 className="mb-4 font-bold">{title}</h2><div className="space-y-3">{children}</div></section>;
}

function DataRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-950/70 px-4 py-3"><span className="min-w-0 truncate text-sm text-slate-400">{label}</span><strong className="shrink-0 tabular-nums text-white">{value}</strong></div>;
}
