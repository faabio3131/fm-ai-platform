"use client";

import {
  ArrowLeft,
  ChefHat,
  CircleDot,
  RefreshCw,
  ShieldAlert,
  Wifi,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { KDSTicketCard } from "@/features/kds/components/KDSTicketCard";
import {
  clearKdsSession,
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
import { useAuthStore } from "@/features/auth/store/auth-store";

const KDS_PERMISSION = "producao.visualizar";

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof KdsApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

export function KDSUnifiedWorkspace() {
  const auth = useAuthStore();
  const kds = useKdsStore();
  const visibleTickets = useVisibleKdsTickets();
  const [ready, setReady] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busyTicket, setBusyTicket] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const allowed = auth.permissions.includes(KDS_PERMISSION);

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
    if (auth.status !== "authenticated" || !allowed || !auth.unitId) return;
    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      if (cancelled) return;
      clearKdsSession();
      kdsActions.reset();
      setReady(false);
      setError(null);

      void Promise.all([fetchKdsSectors(), fetchKdsQueue()])
        .then(([setores, queue]) => {
          if (cancelled) return;
          kdsActions.setSectors(setores);
          kdsActions.setQueue(queue);
          kdsActions.setSector(null);
          setReady(true);
        })
        .catch((caught: unknown) => {
          if (cancelled) return;
          setError(errorMessage(caught, "Falha ao abrir a estação KDS."));
        });
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [auth.status, auth.unitId, allowed]);

  useEffect(() => {
    if (!ready) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refreshQueue(true);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [ready, refreshQueue]);

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

  if (auth.status === "authenticated" && !allowed) {
    return (
      <main className="dark flex min-h-screen items-center justify-center bg-[#0f172a] px-6 text-slate-100">
        <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-[#1e293b] p-6 shadow-2xl">
          <ShieldAlert className="size-8 text-amber-400" />
          <h1 className="mt-4 text-xl font-bold">KDS não liberado para este usuário</h1>
          <p className="mt-2 text-sm text-slate-400">A sessão é válida, mas sua identidade não possui produção.visualizar.</p>
          <Button asChild className="mt-5 w-full">
            <Link href="/"><ArrowLeft />Voltar ao dashboard</Link>
          </Button>
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
              <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-[#2563eb] text-white"><ChefHat className="size-6" /></div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-black tracking-tight text-white sm:text-2xl">KDS · Cozinha</h1>
                  <Badge className={kds.degradado ? "border border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fcd34d]" : "border border-[#10b981]/30 bg-[#10b981]/10 text-[#6ee7b7]"}>
                    {kds.degradado ? <WifiOff /> : <Wifi />}
                    {kds.degradado ? "Degradado" : ready ? "Sessão única" : "Conectando"}
                  </Badge>
                </div>
                <p className="mt-1 truncate text-xs text-slate-400">{auth.tenantId ?? "—"} · {auth.unitId ?? "—"} · {auth.operator?.email ?? "—"}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="outline" className="h-11 rounded-xl border-slate-600 bg-slate-900 text-slate-100 hover:bg-slate-700" onClick={() => void refreshQueue()} disabled={refreshing || !ready}>
                <RefreshCw className={refreshing ? "animate-spin" : ""} /><span className="hidden sm:inline">Atualizar</span>
              </Button>
              <Button asChild variant="ghost" className="h-11 rounded-xl text-slate-300 hover:bg-slate-700 hover:text-white"><Link href="/"><ArrowLeft /><span className="hidden sm:inline">Dashboard</span></Link></Button>
            </div>
          </div>

          <div className="mt-4 flex gap-2 overflow-x-auto pb-1">
            <Button type="button" onClick={() => void selectSector(null)} disabled={!ready} className={`h-12 shrink-0 rounded-xl px-5 font-bold ${kds.setorId === null ? "bg-[#2563eb] text-white" : "bg-slate-900 text-slate-300 hover:bg-slate-700"}`}>
              Todas as estações <Badge className="bg-white/10 text-white hover:bg-white/10">{visibleTickets.length}</Badge>
            </Button>
            {kds.setores.filter((sector) => sector.ativo).map((sector) => (
              <Button key={sector.setor_id} type="button" onClick={() => void selectSector(sector.setor_id)} disabled={!ready} className={`h-12 shrink-0 rounded-xl px-5 font-bold ${kds.setorId === sector.setor_id ? "bg-[#2563eb] text-white" : "bg-slate-900 text-slate-300 hover:bg-slate-700"}`}>
                {sector.nome}
              </Button>
            ))}
          </div>
        </header>

        {kds.somenteLeitura || kds.degradado ? (
          <div className="flex items-center gap-3 rounded-xl border border-[#f59e0b]/40 bg-[#f59e0b]/10 px-4 py-3 text-sm font-semibold text-[#fcd34d]"><WifiOff className="size-5 shrink-0" /><span>{kds.motivoDegradacao ?? "KDS em modo degradado. Comandos permanecem bloqueados enquanto a fila estiver somente leitura."}</span></div>
        ) : null}
        {error ? <div className="rounded-xl border border-[#ef4444]/40 bg-[#ef4444]/10 px-4 py-3 text-sm font-semibold text-[#fca5a5]">{error}</div> : null}

        <div className="grid flex-1 gap-4 [grid-template-columns:repeat(auto-fit,minmax(320px,1fr))]">
          {columns.map(({ sector, tickets }) => (
            <section key={sector.setor_id} className="min-w-0 rounded-2xl border border-slate-800 bg-slate-950/45 p-3">
              <div className="mb-3 flex items-center justify-between gap-2 px-1">
                <div><div className="flex items-center gap-2"><CircleDot className="size-4 text-[#2563eb]" /><h2 className="font-black text-white">{sector.nome}</h2></div><p className="mt-1 text-xs text-slate-500">{sector.codigo} · SLA {sector.sla_segundos ? `${Math.round(sector.sla_segundos / 60)} min` : "operacional"}</p></div>
                <Badge className="bg-slate-800 text-slate-200 hover:bg-slate-800">{tickets.length}</Badge>
              </div>
              <div className="space-y-3">
                {tickets.map((ticket) => <KDSTicketCard key={ticket.producao_id} ticket={ticket} readOnly={kds.somenteLeitura} busy={busyTicket === ticket.producao_id} onTransition={(current, destino) => void handleTransition(current, destino)} />)}
                {tickets.length === 0 ? <div className="flex min-h-40 items-center justify-center rounded-xl border border-dashed border-slate-700 bg-slate-900/30 p-5 text-center text-sm font-medium text-slate-500">{ready ? "Nenhum ticket ativo nesta estação." : "Validando sessão e fila da cozinha…"}</div> : null}
              </div>
            </section>
          ))}
        </div>
      </div>
    </main>
  );
}
