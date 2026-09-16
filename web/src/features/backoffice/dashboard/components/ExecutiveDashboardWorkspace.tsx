"use client";

import {
  BadgeDollarSign,
  Boxes,
  CircleDollarSign,
  LoaderCircle,
  PackageCheck,
  ReceiptText,
  RefreshCw,
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
    <main className="min-h-screen bg-slate-950 p-4 text-slate-100 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-300">
              Proprietário · Unidade ativa
            </p>
            <h1 className="mt-2 text-3xl font-black tracking-tight">
              Dashboard Financeiro e Indicadores
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              Dados consolidados pelas autoridades existentes de pedidos, pagamentos, estoque e entrega.
            </p>
          </div>
          <Button variant="outline" onClick={() => void carregar()} disabled={loading}>
            <RefreshCw className={loading ? "animate-spin" : ""} /> Atualizar
          </Button>
        </header>

        {erro ? (
          <div role="status" className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {erro}
          </div>
        ) : null}

        {loading ? (
          <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-slate-400">
            <LoaderCircle className="size-5 animate-spin" /> Carregando indicadores…
          </div>
        ) : painel ? (
          <>
            <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Metric icon={CircleDollarSign} label="Vendas reconhecidas" value={moeda(painel.financeiro.vendas_reconhecidas)} />
              <Metric icon={ReceiptText} label="Ticket médio" value={moeda(painel.financeiro.ticket_medio)} />
              <Metric icon={BadgeDollarSign} label="Pagamentos recebidos" value={moeda(painel.financeiro.pagamentos_pagos)} />
              <Metric icon={ReceiptText} label="Saldo pendente" value={moeda(painel.financeiro.pagamentos_pendentes)} />
              <Metric icon={PackageCheck} label="Pedidos" value={String(painel.operacional.pedidos)} />
              <Metric icon={Users} label="Usuários ativos" value={String(painel.operacional.usuarios_ativos)} />
              <Metric icon={BadgeDollarSign} label="Recebido em dinheiro" value={moeda(painel.financeiro.recebido_dinheiro)} />
              <Metric icon={CircleDollarSign} label="Pagamentos estornados" value={moeda(painel.financeiro.pagamentos_estornados)} />
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
                    <div key={item.status} className="rounded-xl bg-slate-950/70 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        {rotuloStatus(item.status)}
                      </p>
                      <p className="mt-2 text-2xl font-black text-white">{item.quantidade}</p>
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

function Metric({ icon: Icon, label, value }: { icon: typeof CircleDollarSign; label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <Icon className="size-5 text-blue-400" />
      <p className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-black tabular-nums text-white">{value}</p>
    </div>
  );
}

function Panel({ title, icon: Icon, children }: { title: string; icon: typeof CircleDollarSign; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="mb-4 flex items-center gap-2">
        <Icon className="size-5 text-blue-400" />
        <h2 className="font-bold">{title}</h2>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl bg-slate-950/70 px-4 py-3">
      <span className="text-sm text-slate-400">{label}</span>
      <strong className="text-right tabular-nums text-white">{value}</strong>
    </div>
  );
}
