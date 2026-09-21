"use client";

import {
  BadgeDollarSign,
  Boxes,
  CircleDollarSign,
  LoaderCircle,
  PackageCheck,
  ReceiptText,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Truck,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  obterPainelExecutivo,
  type PainelExecutivo,
} from "@/features/backoffice/dashboard/services/dashboard-api";

function moeda(valor: string | null): string {
  if (valor === null) return "Não disponível";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(valor));
}

function quantidade(valor: string): string {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: 3,
    maximumFractionDigits: 3,
  }).format(Number(valor));
}

function rotuloStatus(status: string): string {
  return status.replaceAll("_", " ");
}

export function ExecutiveDashboardWorkspace() {
  const auth = useAuthStore();
  const [painel, setPainel] = useState<PainelExecutivo | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      setPainel(await obterPainelExecutivo());
    } catch {
      setPainel(null);
      setErro("Não foi possível carregar os indicadores desta unidade.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId) return;
    const timeoutId = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, carregar]);

  return (
    <main className="kordena-page-dark min-h-screen p-4 text-slate-100 sm:p-6 lg:p-8">
      <div className="kordena-enter mx-auto max-w-[1500px] space-y-6">
        <header className="relative overflow-hidden rounded-[2rem] border border-blue-400/15 bg-[linear-gradient(135deg,rgba(37,99,235,0.15),rgba(14,165,233,0.04)_48%,rgba(8,17,31,0.96))] p-6 shadow-[0_28px_70px_-42px_rgba(37,99,235,0.72)] sm:p-8">
          <div className="kordena-grid pointer-events-none absolute inset-0 opacity-55" />
          <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-amber-400/15 bg-amber-400/[0.07] px-3 py-1.5 text-xs font-bold text-amber-200">
                <ShieldCheck className="size-3.5" />
                Proprietário · Unidade ativa
              </div>
              <p className="mt-5 text-xs font-black uppercase tracking-[0.2em] text-sky-300">Intelligence cockpit</p>
              <h1 className="mt-2 text-3xl font-black tracking-[-0.035em] sm:text-4xl">
                Dashboard Financeiro e Indicadores
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-400">
                Dados consolidados pelas autoridades existentes de pedidos, pagamentos, estoque e entrega.
              </p>
            </div>
            <div className="flex flex-col gap-3 sm:flex-row lg:items-center">
              <div className="hidden items-center gap-2 rounded-2xl border border-blue-400/15 bg-blue-400/[0.06] px-4 py-3 text-xs text-slate-400 xl:flex">
                <Sparkles className="size-4 text-sky-300" />
                Fonte de verdade preservada
              </div>
              <Button
                variant="outline"
                className="border-white/10 bg-white/[0.05] text-white shadow-none hover:border-blue-400/30 hover:bg-white/[0.08] hover:text-white"
                onClick={() => void carregar()}
                disabled={loading}
              >
                <RefreshCw className={loading ? "animate-spin" : ""} /> Atualizar
              </Button>
            </div>
          </div>
        </header>

        {erro ? (
          <div role="status" className="rounded-2xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
            {erro}
          </div>
        ) : null}

        {loading ? (
          <div className="kordena-panel-dark flex min-h-72 items-center justify-center gap-3 rounded-[1.75rem] text-sm text-slate-400">
            <LoaderCircle className="size-5 animate-spin text-blue-400" /> Carregando indicadores…
          </div>
        ) : painel ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric icon={CircleDollarSign} label="Vendas reconhecidas" value={moeda(painel.financeiro.vendas_reconhecidas)} accent="emerald" />
              <Metric icon={ReceiptText} label="Ticket médio" value={moeda(painel.financeiro.ticket_medio)} />
              <Metric icon={BadgeDollarSign} label="Pagamentos recebidos" value={moeda(painel.financeiro.pagamentos_pagos)} accent="sky" />
              <Metric icon={ReceiptText} label="Saldo pendente" value={moeda(painel.financeiro.pagamentos_pendentes)} accent="amber" />
              <Metric icon={PackageCheck} label="Pedidos" value={String(painel.operacional.pedidos)} />
              <Metric icon={Users} label="Usuários ativos" value={String(painel.operacional.usuarios_ativos)} accent="sky" />
              <Metric icon={BadgeDollarSign} label="Recebido em dinheiro" value={moeda(painel.financeiro.recebido_dinheiro)} accent="emerald" />
              <Metric icon={CircleDollarSign} label="Pagamentos estornados" value={moeda(painel.financeiro.pagamentos_estornados)} accent="amber" />
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              <Panel title="CMV e margem atuais" icon={CircleDollarSign}>
                <DataRow label="CMV estimado atual" value={moeda(painel.financeiro.cmv_estimado_atual)} />
                <DataRow label="Margem estimada atual" value={moeda(painel.financeiro.margem_estimada_atual)} />
                <DataRow label="Cobertura do CMV" value={`${Number(painel.financeiro.cobertura_cmv_itens_pct).toFixed(1)}%`} />
              </Panel>

              <Panel title="Estoque e integrações" icon={Boxes}>
                <DataRow label="Saldo físico agregado" value={quantidade(painel.operacional.estoque_fisico_total)} />
                <DataRow label="Saldo reservado agregado" value={quantidade(painel.operacional.estoque_reservado_total)} />
                <DataRow label="Integrações homologadas" value={`${painel.operacional.integracoes_homologadas}/${painel.operacional.integracoes_configuradas}`} />
              </Panel>
            </section>

            <Panel title="Delivery e entrega" icon={Truck}>
              {painel.operacional.entregas_por_status.length === 0 ? (
                <p className="text-sm text-slate-400">Nenhuma entrega registrada no escopo atual.</p>
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  {painel.operacional.entregas_por_status.map((item) => (
                    <div key={item.status} className="rounded-2xl border border-white/[0.06] bg-slate-950/55 p-4">
                      <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-500">
                        {rotuloStatus(item.status)}
                      </p>
                      <p className="mt-2 text-3xl font-black tabular-nums text-white">{item.quantidade}</p>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        ) : null}
      </div>
    </main>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  accent = "blue",
}: {
  icon: typeof CircleDollarSign;
  label: string;
  value: string;
  accent?: "blue" | "sky" | "emerald" | "amber";
}) {
  const accentClass = {
    blue: "bg-blue-400/10 text-blue-300 ring-blue-400/15",
    sky: "bg-sky-400/10 text-sky-300 ring-sky-400/15",
    emerald: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/15",
    amber: "bg-amber-400/10 text-amber-300 ring-amber-400/15",
  }[accent];

  return (
    <div className="kordena-panel-dark group rounded-[1.5rem] p-5 transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-400/20">
      <div className={`flex size-10 items-center justify-center rounded-xl ring-1 ${accentClass}`}>
        <Icon className="size-5" />
      </div>
      <p className="mt-5 text-[10px] font-black uppercase tracking-[0.13em] text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-black tabular-nums tracking-tight text-white">{value}</p>
    </div>
  );
}

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof CircleDollarSign; children: ReactNode }) {
  return (
    <section className="kordena-panel-dark rounded-[1.75rem] p-5 sm:p-6">
      <div className="mb-5 flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-xl bg-blue-400/10 text-blue-300 ring-1 ring-blue-400/15">
          <Icon className="size-4" />
        </span>
        <h2 className="font-bold text-white">{title}</h2>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-2xl border border-white/[0.05] bg-slate-950/50 px-4 py-3.5">
      <span className="text-sm text-slate-400">{label}</span>
      <strong className="text-right tabular-nums text-white">{value}</strong>
    </div>
  );
}
