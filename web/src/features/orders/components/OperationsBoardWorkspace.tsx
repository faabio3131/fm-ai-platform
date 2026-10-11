"use client";

import { AlertTriangle, ArrowUpRight, BrainCircuit, ClipboardList, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuthStore } from "@/features/auth/store/auth-store";
import { listOrders, type OrderCenterSummary } from "@/features/orders/services/orders-api";

const GROUPS = [
  { key: "novos", label: "Novos", statuses: ["rascunho", "aguardando_confirmacao"], color: "border-blue-400" },
  { key: "preparo", label: "Em preparo", statuses: ["confirmado", "enviado_producao", "em_preparo"], color: "border-amber-400" },
  { key: "prontos", label: "Prontos", statuses: ["pronto"], color: "border-emerald-400" },
] as const;

const REFRESH_MS = 15000;
const PAGE_SIZE = 100;

function readable(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

export function OperationsBoardWorkspace() {
  const auth = useAuthStore();
  const allowed = auth.permissions.includes("pedido.visualizar");
  const [orders, setOrders] = useState<OrderCenterSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [truncated, setTruncated] = useState(false);

  const refresh = useCallback(async () => {
    if (!allowed || auth.status !== "authenticated" || !auth.unitId) return;
    setLoading(true);
    try {
      const first = await listOrders({ pagina: 1, tamanhoPagina: PAGE_SIZE });
      // The V1 board is deliberately capped. Never claim global totals from a partial page.
      setOrders(first.itens);
      setTruncated(first.total > first.itens.length);
      setUpdatedAt(new Date());
      setError(null);
    } catch {
      setError("Não foi possível atualizar os pedidos. Os dados anteriores podem estar desatualizados.");
    } finally {
      setLoading(false);
    }
  }, [allowed, auth.status, auth.unitId]);

  useEffect(() => {
    if (!allowed || auth.status !== "authenticated" || !auth.unitId) return;
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, REFRESH_MS);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); };
  }, [allowed, auth.status, auth.unitId, refresh]);

  const groups = useMemo(() => GROUPS.map((group) => ({
    ...group,
    items: orders.filter((order) => (group.statuses as readonly string[]).includes(order.status)),
  })), [orders]);

  if (auth.status !== "authenticated") {
    return <main className="p-8 text-slate-300">Aguardando autenticação...</main>;
  }
  if (!allowed) {
    return <main className="p-8 text-slate-300">Você não tem permissão para visualizar pedidos.</main>;
  }

  return (
    <main className="min-h-full bg-[#071321] px-4 py-7 text-slate-100 sm:px-8">
      <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">Kordena · Operação</p>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Central de Operações</h1>
          <p className="mt-2 text-sm text-slate-400">Visão de acompanhamento dos pedidos. Nenhuma ação altera o estado operacional.</p>
        </div>
        <button type="button" onClick={() => void refresh()} disabled={loading} className="inline-flex items-center gap-2 rounded-xl border border-slate-600 px-4 py-2 text-sm hover:bg-slate-800 disabled:opacity-50">
          <RefreshCw className="h-4 w-4" /> {loading ? "Atualizando..." : "Atualizar"}
        </button>
      </header>

      {error && <div role="alert" className="mb-4 rounded-xl border border-amber-500/50 bg-amber-500/10 p-3 text-sm text-amber-200">{error}</div>}
      {truncated && <div className="mb-4 rounded-xl border border-slate-600 p-3 text-sm text-slate-300">Exibindo somente os {orders.length} pedidos mais recentes retornados pela API. Consulte a Central de Pedidos para a lista completa.</div>}
      <div className="mb-5 flex flex-wrap gap-3 text-xs text-slate-400">
        <span>Atualização automática a cada 15 segundos enquanto a aba estiver visível.</span>
        <span>{updatedAt ? `Última atualização: ${updatedAt.toLocaleTimeString("pt-BR")}` : "Aguardando dados"}</span>
      </div>

      <section aria-label="Quadro de pedidos" className="grid gap-4 lg:grid-cols-3">
        {groups.map((group) => (
          <div key={group.key} className={`min-h-72 rounded-2xl border-t-4 ${group.color} bg-[#102235] p-4 shadow-lg`}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-semibold">{group.label}</h2>
              <span className="rounded-full bg-slate-700 px-3 py-1 text-xs font-bold">{group.items.length}{truncated ? "+" : ""}</span>
            </div>
            <div className="space-y-3">
              {group.items.length === 0 && <p className="rounded-xl border border-dashed border-slate-600 p-5 text-center text-sm text-slate-400">Nenhum pedido nesta etapa.</p>}
              {group.items.map((order) => (
                <Link key={order.pedido_id} href="/pedidos" className="block rounded-xl border border-slate-700 bg-[#172d43] p-4 transition hover:border-cyan-400 hover:bg-[#1b3751]">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-semibold">Pedido #{order.pedido_id.slice(0, 8)}</span>
                    <ArrowUpRight className="h-4 w-4 text-cyan-300" />
                  </div>
                  <p className="mt-2 text-xs text-slate-300">{readable(order.canal)} · {order.quantidade_itens} item(ns)</p>
                  <p className="mt-1 text-xs text-slate-400">Estado: {readable(order.status)}</p>
                  {order.possui_alerta && <p className="mt-2 flex items-center gap-1 text-xs text-amber-300"><AlertTriangle className="h-3 w-3" /> Requer atenção</p>}
                </Link>
              ))}
            </div>
          </div>
        ))}
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-2">
        <Link href="/pedidos" className="rounded-2xl border border-slate-700 bg-[#102235] p-5 hover:border-cyan-400">
          <ClipboardList className="mb-3 h-6 w-6 text-cyan-400" />
          <h2 className="font-semibold">Central de Pedidos completa</h2>
          <p className="mt-1 text-sm text-slate-400">Filtros, detalhes, histórico e ações operacionais autorizadas.</p>
        </Link>
        {auth.permissions.includes("gerente_ia.consultar") && (
          <Link href="/gerente-ia" className="rounded-2xl border border-slate-700 bg-[#102235] p-5 hover:border-cyan-400">
            <BrainCircuit className="mb-3 h-6 w-6 text-cyan-400" />
            <h2 className="font-semibold">Gerente IA</h2>
            <p className="mt-1 text-sm text-slate-400">Consulte a inteligência operacional e confirme ações conforme as políticas existentes.</p>
          </Link>
        )}
      </section>
      <p className="mt-5 text-xs text-slate-500">A coluna Prontos usa o status comercial do pedido; a integração detalhada por item/setor do KDS permanece planejada para evolução posterior.</p>
    </main>
  );
}
