"use client";

import {
  ArrowLeft,
  ChefHat,
  CircleDot,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Wifi,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { KDSTicketCard } from "@/features/kds/components/KDSTicketCard";
import {
  clearKdsSession,
  configureKdsSession,
  fetchKdsQueue,
  fetchKdsSectors,
  KdsApiError,
  transitionKds,
  type KdsDestination,
  type KdsTicket,
} from "@/features/kds/services/kds-api";
import {
  kdsActions,
  useKdsStore,
  useVisibleKdsTickets,
} from "@/features/kds/store/kds-store";

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof KdsApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

export function KDSWorkspace() {
  const kds = useKdsStore();
  const visibleTickets = useVisibleKdsTickets();
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busyTicket, setBusyTicket] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [unitId, setUnitId] = useState("");

  const refreshQueue = useCallback(
    async (silent = false) => {
      if (!silent) setRefreshing(true);
      try {
        const queue = await fetchKdsQueue(kds.setorId ?? undefined);
        kdsActions.setQueue(queue);
        if (!silent) setError(null);
      } catch (caught) {
        setError(errorMessage(caught, "Falha ao atualizar a fila da cozinha."));
      } finally {
        if (!silent) setRefreshing(false);
      }
    },
    [kds.setorId],
  );

  useEffect(() => {
    if (!connected) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshQueue(true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [connected, refreshQueue]);

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      configureKdsSession({ email, password, tenantId, unitId });
      const [setores, queue] = await Promise.all([
        fetchKdsSectors(),
        fetchKdsQueue(),
      ]);
      kdsActions.setSectors(setores);
      kdsActions.setQueue(queue);
      kdsActions.setSector(null);
      setConnected(true);
      setPassword("");
    } catch (caught) {
      clearKdsSession();
      kdsActions.reset();
      setError(errorMessage(caught, "Falha ao abrir a sessão operacional do KDS."));
    } finally {
      setLoading(false);
    }
  }

  function disconnect() {
    clearKdsSession();
    kdsActions.reset();
    setConnected(false);
    setError(null);
    setPassword("");
  }

  async function selectSector(setorId: string | null) {
    kdsActions.setSector(setorId);
    setRefreshing(true);
    setError(null);
    try {
      const queue = await fetchKdsQueue(setorId ?? undefined);
      kdsActions.setQueue(queue);
    } catch (caught) {
      setError(errorMessage(caught, "Falha ao filtrar a estação de preparo."));
    } finally {
      setRefreshing(false);
    }
  }

  async function handleTransition(ticket: KdsTicket, destino: KdsDestination) {
    setBusyTicket(ticket.producao_id);
    setError(null);
    try {
      const result = await transitionKds({
        producao_id: ticket.producao_id,
        destino,
        versao_esperada: ticket.versao,
        motivo: null,
      });
      kdsActions.applyTransition(result);
      await refreshQueue(true);
    } catch (caught) {
      if (caught instanceof KdsApiError && caught.status === 409) {
        await refreshQueue(true);
        setError("O ticket mudou em outro terminal. A fila foi atualizada; revise o estado antes de tentar novamente.");
      } else {
        setError(errorMessage(caught, "Falha ao avançar o status de produção."));
      }
    } finally {
      setBusyTicket(null);
    }
  }

  const columns = useMemo(() => {
    const sectors = kds.setorId
      ? kds.setores.filter((sector) => sector.setor_id === kds.setorId)
      : kds.setores.filter((sector) => sector.ativo);
    return sectors.map((sector) => ({
      sector,
      tickets: visibleTickets.filter((ticket) => ticket.setor_id === sector.setor_id),
    }));
  }, [kds.setorId, kds.setores, visibleTickets]);

  if (!connected) {
    return (
      <main className="dark min-h-screen bg-[#0f172a] px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
        <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl items-center justify-center">
          <Card className="w-full max-w-xl border-slate-700 bg-[#1e293b] text-slate-100 shadow-2xl shadow-black/30">
            <CardHeader className="space-y-4 border-b border-slate-700 bg-slate-950 text-white">
              <div className="flex items-center justify-between gap-3">
                <div className="flex size-12 items-center justify-center rounded-2xl bg-[#2563eb] text-white">
                  <ChefHat className="size-6" />
                </div>
                <Badge className="border border-white/10 bg-white/10 text-white hover:bg-white/10">
                  KDS Enterprise V1
                </Badge>
              </div>
              <div>
                <CardTitle className="text-2xl text-white">Abrir estação de cozinha</CardTitle>
                <CardDescription className="mt-2 text-slate-400">
                  Tema escuro permanente, fila canônica por tenant/unidade e comandos protegidos por versão e idempotência.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-6">
              <form className="space-y-4" onSubmit={(event) => void connect(event)}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-1.5 text-sm font-medium text-slate-200">
                    Tenant
                    <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} placeholder="tenant-id" required className="h-12 border-slate-600 bg-slate-950 text-white" />
                  </label>
                  <label className="space-y-1.5 text-sm font-medium text-slate-200">
                    Unidade
                    <Input value={unitId} onChange={(event) => setUnitId(event.target.value)} placeholder="unidade-id" required className="h-12 border-slate-600 bg-slate-950 text-white" />
                  </label>
                </div>
                <label className="block space-y-1.5 text-sm font-medium text-slate-200">
                  Operador da cozinha
                  <Input autoComplete="username" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="cozinha@empresa.com" required className="h-12 border-slate-600 bg-slate-950 text-white" />
                </label>
                <label className="block space-y-1.5 text-sm font-medium text-slate-200">
                  Senha
                  <Input autoComplete="current-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} required className="h-12 border-slate-600 bg-slate-950 text-white" />
                </label>

                {error ? (
                  <div className="rounded-xl border border-[#ef4444]/40 bg-[#ef4444]/10 px-4 py-3 text-sm font-semibold text-[#fca5a5]">
                    {error}
                  </div>
                ) : null}

                <Button type="submit" className="h-13 w-full rounded-xl bg-[#2563eb] text-base font-black hover:bg-blue-500" disabled={loading}>
                  {loading ? <RefreshCw className="animate-spin" /> : <ShieldCheck />}
                  {loading ? "Validando estação..." : "Entrar no KDS"}
                </Button>
                <Button asChild type="button" variant="ghost" className="h-11 w-full text-slate-300 hover:bg-slate-700 hover:text-white">
                  <Link href="/">
                    <ArrowLeft />
                    Voltar ao dashboard
                  </Link>
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    );
  }

  return (
    <main className="dark min-h-screen bg-[#0f172a] p-3 text-slate-100 sm:p-4 lg:p-5">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-[1900px] flex-col gap-4">
        <header className="rounded-2xl border border-slate-700 bg-[#1e293b] p-4 shadow-xl shadow-black/10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-[#2563eb] text-white">
                <ChefHat className="size-6" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-black tracking-tight text-white sm:text-2xl">KDS · Cozinha</h1>
                  <Badge className={kds.degradado ? "border border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fcd34d]" : "border border-[#10b981]/30 bg-[#10b981]/10 text-[#6ee7b7]"}>
                    {kds.degradado ? <WifiOff /> : <Wifi />}
                    {kds.degradado ? "Degradado" : "Online"}
                  </Badge>
                </div>
                <p className="mt-1 truncate text-xs text-slate-400">
                  {tenantId} · {unitId} · polling gracioso 5s · /v1/kds
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" className="h-11 rounded-xl border-slate-600 bg-slate-900 text-slate-100 hover:bg-slate-700" onClick={() => void refreshQueue()} disabled={refreshing}>
                <RefreshCw className={refreshing ? "animate-spin" : ""} />
                <span className="hidden sm:inline">Atualizar</span>
              </Button>
              <Button type="button" variant="ghost" className="h-11 rounded-xl text-slate-300 hover:bg-slate-700 hover:text-white" onClick={disconnect}>
                <LogOut />
                <span className="hidden sm:inline">Encerrar</span>
              </Button>
            </div>
          </div>

          <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
            <Button type="button" onClick={() => void selectSector(null)} className={`h-12 shrink-0 rounded-xl px-5 font-bold ${kds.setorId === null ? "bg-[#2563eb] text-white" : "bg-slate-900 text-slate-300 hover:bg-slate-700"}`}>
              Todas as estações
              <Badge className="bg-white/10 text-white hover:bg-white/10">{visibleTickets.length}</Badge>
            </Button>
            {kds.setores.filter((sector) => sector.ativo).map((sector) => (
              <Button key={sector.setor_id} type="button" onClick={() => void selectSector(sector.setor_id)} className={`h-12 shrink-0 rounded-xl px-5 font-bold ${kds.setorId === sector.setor_id ? "bg-[#2563eb] text-white" : "bg-slate-900 text-slate-300 hover:bg-slate-700"}`}>
                {sector.nome}
              </Button>
            ))}
          </div>
        </header>

        {kds.somenteLeitura || kds.degradado ? (
          <div className="flex items-center gap-3 rounded-xl border border-[#f59e0b]/40 bg-[#f59e0b]/10 px-4 py-3 text-sm font-semibold text-[#fcd34d]">
            <WifiOff className="size-5 shrink-0" />
            <span>{kds.motivoDegradacao ?? "KDS em modo degradado. Comandos permanecem bloqueados enquanto a fila estiver somente leitura."}</span>
          </div>
        ) : null}

        {error ? (
          <div className="rounded-xl border border-[#ef4444]/40 bg-[#ef4444]/10 px-4 py-3 text-sm font-semibold text-[#fca5a5]">
            {error}
          </div>
        ) : null}

        <div className="grid flex-1 gap-4 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]">
          {columns.map(({ sector, tickets }) => (
            <section key={sector.setor_id} className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/45 p-3">
              <div className="mb-3 flex items-center justify-between gap-2 px-1">
                <div>
                  <div className="flex items-center gap-2">
                    <CircleDot className="size-4 text-[#2563eb]" />
                    <h2 className="font-black text-white">{sector.nome}</h2>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{sector.codigo} · SLA {sector.sla_segundos ? `${Math.round(sector.sla_segundos / 60)} min` : "operacional"}</p>
                </div>
                <Badge className="bg-slate-800 text-slate-200 hover:bg-slate-800">{tickets.length}</Badge>
              </div>

              <div className="space-y-3">
                {tickets.map((ticket) => (
                  <KDSTicketCard
                    key={ticket.producao_id}
                    ticket={ticket}
                    readOnly={kds.somenteLeitura}
                    busy={busyTicket === ticket.producao_id}
                    onTransition={(current, destino) => void handleTransition(current, destino)}
                  />
                ))}
                {tickets.length === 0 ? (
                  <div className="flex min-h-40 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/30 p-5 text-center text-sm font-medium text-slate-500">
                    Nenhum ticket ativo nesta estação.
                  </div>
                ) : null}
              </div>
            </section>
          ))}
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-2 text-xs text-slate-500">
          <span className="font-mono tabular-nums">Última fila: {kds.atualizadoEm ? new Date(kds.atualizadoEm).toLocaleTimeString("pt-BR") : "—"}</span>
          <span>{visibleTickets.length} ticket(s) ativo(s)</span>
        </footer>
      </div>
    </main>
  );
}
