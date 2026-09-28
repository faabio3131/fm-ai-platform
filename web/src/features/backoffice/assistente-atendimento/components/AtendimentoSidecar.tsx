"use client";

import {
  CircleDollarSign,
  Headphones,
  RefreshCw,
  ShoppingBag,
  Truck,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { WhatsAppChannelMark } from "@/features/backoffice/assistente-atendimento/components/WhatsAppChannelMark";
import {
  ESTADO_COLORS,
  ESTADO_LABELS,
} from "@/features/backoffice/assistente-atendimento/constants";
import {
  listarConversas,
  type ConversaResumo,
} from "@/features/backoffice/assistente-atendimento/services/assistente-atendimento-api";

const ATENCAO = new Set([
  "aguardando_confirmacao_cliente",
  "handoff_humano",
]);

function horario(valor: string): string {
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(data);
}

export function AtendimentoSidecar({
  enabled,
  unitId,
  pathname,
}: {
  enabled: boolean;
  unitId?: string | null;
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled || !unitId) return;
    setLoading(true);
    try {
      const response = await listarConversas();
      setConversas(response.conversas);
      setError(null);
      setLastUpdatedAt(new Date());
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Não foi possível atualizar a fila de atendimento.",
      );
    } finally {
      setLoading(false);
    }
  }, [enabled, unitId]);

  useEffect(() => {
    if (!enabled || !unitId) return;
    const timeout = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [enabled, refresh, unitId]);

  useEffect(() => {
    if (!enabled || !unitId || !open) return;
    const interval = window.setInterval(() => {
      void refresh();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [enabled, open, refresh, unitId]);

  const ordenadas = useMemo(
    () =>
      [...conversas].sort(
        (a, b) =>
          new Date(b.atualizado_em).getTime() - new Date(a.atualizado_em).getTime(),
      ),
    [conversas],
  );

  const metricas = useMemo(
    () => ({
      total: conversas.length,
      atencao: conversas.filter((item) => ATENCAO.has(item.estado)).length,
      handoff: conversas.filter((item) => item.estado === "handoff_humano").length,
      pedidos: conversas.filter((item) => Boolean(item.pedido_id)).length,
    }),
    [conversas],
  );

  const fullPage =
    pathname.startsWith("/atendimento-ia") ||
    pathname.startsWith("/admin/assistente-atendimento");

  if (!enabled || fullPage) return null;

  return (
    <>
      {!open ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-4 z-[55] flex items-center gap-2 rounded-2xl border border-emerald-300/20 bg-[#071523]/95 px-3 py-2.5 text-left shadow-[0_22px_55px_-24px_rgba(0,0,0,0.95)] backdrop-blur-xl transition hover:border-emerald-300/35 hover:bg-[#0a1b2d] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300/60"
          aria-label="Abrir acompanhamento lateral da Central de Atendimento IA"
        >
          <WhatsAppChannelMark className="size-9" />
          <span className="hidden sm:block">
            <span className="block text-[10px] font-black uppercase tracking-[0.14em] text-emerald-300">
              Atendimento ao vivo
            </span>
            <span className="mt-0.5 block text-xs font-bold text-slate-100">
              Central de Atendimento IA
            </span>
          </span>
          {metricas.atencao > 0 ? (
            <span className="ml-1 flex min-w-5 items-center justify-center rounded-full bg-amber-400 px-1.5 py-0.5 text-[10px] font-black text-slate-950">
              {metricas.atencao}
            </span>
          ) : null}
        </button>
      ) : null}

      {open ? (
        <aside
          className="fixed bottom-0 right-0 top-[73px] z-[56] flex w-[min(430px,calc(100vw-0.75rem))] flex-col border-l border-sky-300/[0.1] bg-[linear-gradient(180deg,rgba(5,16,29,0.985),rgba(6,22,38,0.99))] shadow-[-28px_0_70px_-38px_rgba(0,0,0,0.98)] backdrop-blur-2xl max-sm:top-0 max-sm:w-full"
          aria-label="Acompanhamento lateral da Central de Atendimento IA"
        >
          <div className="border-b border-white/[0.07] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <WhatsAppChannelMark className="size-11" />
                <div className="min-w-0">
                  <p className="text-[10px] font-black uppercase tracking-[0.16em] text-emerald-300">
                    Acompanhamento lateral
                  </p>
                  <h2 className="truncate text-base font-black text-white">
                    Central de Atendimento IA
                  </h2>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    Atualiza automaticamente a cada 15 segundos
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => void refresh()}
                  disabled={loading}
                  className="flex size-9 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.035] text-slate-400 transition hover:text-white disabled:opacity-50"
                  aria-label="Atualizar atendimentos"
                >
                  <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="flex size-9 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.035] text-slate-400 transition hover:text-white"
                  aria-label="Fechar acompanhamento lateral"
                >
                  <X className="size-4" />
                </button>
              </div>
            </div>

            <div className="mt-4 grid grid-cols-4 gap-2">
              {[
                ["Fila", metricas.total],
                ["Atenção", metricas.atencao],
                ["Handoff", metricas.handoff],
                ["Pedidos", metricas.pedidos],
              ].map(([label, value]) => (
                <div
                  key={String(label)}
                  className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-2 text-center"
                >
                  <p className="text-lg font-black tabular-nums text-white">{value}</p>
                  <p className="text-[9px] font-bold uppercase tracking-[0.1em] text-slate-500">
                    {label}
                  </p>
                </div>
              ))}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3">
            {error ? (
              <div className="mb-3 rounded-xl border border-red-400/20 bg-red-400/[0.07] p-3 text-xs leading-5 text-red-200">
                {error}
              </div>
            ) : null}

            {loading && conversas.length === 0 ? (
              <div className="flex min-h-48 items-center justify-center">
                <RefreshCw className="size-5 animate-spin text-sky-300" />
              </div>
            ) : ordenadas.length === 0 ? (
              <div className="flex min-h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-white/[0.07] bg-white/[0.02] px-6 text-center">
                <WhatsAppChannelMark className="size-12" />
                <p className="mt-3 text-sm font-bold text-slate-200">
                  Nenhum atendimento na fila
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Novas conversas aparecerão aqui sem tirar você da tela operacional atual.
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {ordenadas.slice(0, 12).map((conversa) => (
                  <div
                    key={conversa.conversa_id}
                    className="rounded-2xl border border-white/[0.06] bg-white/[0.025] p-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[11px] font-bold text-slate-300">
                            {conversa.conversa_id.slice(0, 10)}…
                          </span>
                          <span
                            className={[
                              "rounded-full px-2 py-0.5 text-[9px] font-bold",
                              ESTADO_COLORS[conversa.estado] ??
                                "bg-slate-700/40 text-slate-300",
                            ].join(" ")}
                          >
                            {ESTADO_LABELS[conversa.estado] ?? conversa.estado}
                          </span>
                        </div>
                        <p className="mt-1 text-[10px] text-slate-500">
                          Atualizado às {horario(conversa.atualizado_em)}
                        </p>
                      </div>
                      {conversa.estado === "handoff_humano" ? (
                        <Headphones className="size-4 shrink-0 text-amber-300" />
                      ) : null}
                    </div>

                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {conversa.pedido_id ? (
                        <span className="inline-flex items-center gap-1 rounded-lg bg-sky-400/[0.07] px-2 py-1 text-[10px] font-semibold text-sky-200">
                          <ShoppingBag className="size-3" />
                          Pedido
                        </span>
                      ) : null}
                      {conversa.pagamento_id ? (
                        <span className="inline-flex items-center gap-1 rounded-lg bg-emerald-400/[0.07] px-2 py-1 text-[10px] font-semibold text-emerald-200">
                          <CircleDollarSign className="size-3" />
                          Pagamento
                        </span>
                      ) : null}
                      {conversa.entrega_id ? (
                        <span className="inline-flex items-center gap-1 rounded-lg bg-violet-400/[0.07] px-2 py-1 text-[10px] font-semibold text-violet-200">
                          <Truck className="size-3" />
                          Entrega
                        </span>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="border-t border-white/[0.07] p-3">
            <div className="mb-2 flex items-center justify-between text-[10px] text-slate-500">
              <span>
                {lastUpdatedAt
                  ? `Última atualização ${lastUpdatedAt.toLocaleTimeString("pt-BR", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}`
                  : "Aguardando primeira atualização"}
              </span>
              <span>{Math.min(ordenadas.length, 12)} exibidos</span>
            </div>
            <Link
              href="/atendimento-ia"
              onClick={() => setOpen(false)}
              className="flex h-10 items-center justify-center rounded-xl bg-[linear-gradient(135deg,#2563eb,#0ea5e9)] text-xs font-black text-white shadow-[0_12px_28px_-18px_rgba(14,165,233,0.95)] transition hover:brightness-110"
            >
              Abrir Central completa
            </Link>
          </div>
        </aside>
      ) : null}
    </>
  );
}
