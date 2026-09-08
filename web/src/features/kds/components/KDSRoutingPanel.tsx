"use client";

import { ArrowRight, RefreshCw, Route } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  fetchKdsPendingRouting,
  KdsApiError,
  routeKdsPending,
  type KdsPendingRoutingItem,
  type KdsSector,
} from "@/features/kds/services/kds-api";

const ROUTE_PERMISSION = "producao.atualizar";

function errorMessage(caught: unknown): string {
  if (caught instanceof KdsApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error
    ? caught.message
    : "Não foi possível operar o roteamento da produção.";
}

export function KDSRoutingPanel({
  sectors,
  onRouted,
}: {
  sectors: KdsSector[];
  onRouted: () => Promise<void>;
}) {
  const auth = useAuthStore();
  const allowed = auth.permissions.includes(ROUTE_PERMISSION);
  const [items, setItems] = useState<KdsPendingRoutingItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [selectedSectorId, setSelectedSectorId] = useState("");
  const [priority, setPriority] = useState(0);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const activeSectors = useMemo(
    () => sectors.filter((sector) => sector.ativo),
    [sectors],
  );
  const effectiveSectorId = selectedSectorId || activeSectors[0]?.setor_id || "";
  const selectedItem = useMemo(
    () => items.find((item) => item.pedido_item_id === selectedItemId) ?? null,
    [items, selectedItemId],
  );

  const refreshPending = useCallback(async () => {
    setLoading(true);
    try {
      const result = await fetchKdsPendingRouting();
      setItems(result);
      setSelectedItemId((current) =>
        result.some((item) => item.pedido_item_id === current)
          ? current
          : (result[0]?.pedido_item_id ?? ""),
      );
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId || !allowed) return;
    const timeoutId = window.setTimeout(() => void refreshPending(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, allowed, refreshPending]);

  async function handleRoute() {
    if (!selectedItem || !effectiveSectorId || busy) return;
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const result = await routeKdsPending({
        pedido_item_id: selectedItem.pedido_item_id,
        setor_id: effectiveSectorId,
        prioridade: priority,
      });
      setNotice(
        `Item enviado para produção. Pedido em ${result.pedido_status.replaceAll("_", " ")}.`,
      );
      await Promise.all([refreshPending(), onRouted()]);
    } catch (caught) {
      setError(errorMessage(caught));
      await refreshPending();
    } finally {
      setBusy(false);
    }
  }

  if (!allowed) return null;

  return (
    <section className="rounded-2xl border border-slate-700 bg-[#1e293b] p-4 shadow-xl shadow-black/10">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Route className="size-5 text-blue-400" />
            <div>
              <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-300">
                Pedidos aguardando roteamento
              </p>
              <p className="mt-1 text-sm text-slate-400">
                Confirme o pedido na Central e encaminhe cada item ao setor real de produção.
              </p>
            </div>
          </div>
          {error ? (
            <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm font-semibold text-red-300">
              {error}
            </div>
          ) : null}
          {notice ? (
            <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm font-semibold text-emerald-300">
              {notice}
            </div>
          ) : null}
        </div>

        <div className="grid min-w-0 flex-[1.5] gap-3 md:grid-cols-[minmax(0,1.5fr)_minmax(180px,1fr)_100px_auto]">
          <label className="min-w-0">
            <span className="mb-1 block text-xs font-bold text-slate-400">Item confirmado</span>
            <select
              value={selectedItemId}
              onChange={(event) => setSelectedItemId(event.target.value)}
              disabled={loading || busy || items.length === 0}
              className="h-11 w-full rounded-xl border border-slate-600 bg-slate-900 px-3 text-sm text-slate-100 outline-none focus:border-blue-500"
            >
              {items.length === 0 ? (
                <option value="">{loading ? "Carregando…" : "Nenhum item pendente"}</option>
              ) : null}
              {items.map((item) => (
                <option key={item.pedido_item_id} value={item.pedido_item_id}>
                  {item.nome_produto} · {item.quantidade} · {item.pedido_id}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="mb-1 block text-xs font-bold text-slate-400">Setor de destino</span>
            <select
              value={effectiveSectorId}
              onChange={(event) => setSelectedSectorId(event.target.value)}
              disabled={busy || activeSectors.length === 0}
              className="h-11 w-full rounded-xl border border-slate-600 bg-slate-900 px-3 text-sm text-slate-100 outline-none focus:border-blue-500"
            >
              {activeSectors.length === 0 ? <option value="">Nenhum setor ativo</option> : null}
              {activeSectors.map((sector) => (
                <option key={sector.setor_id} value={sector.setor_id}>{sector.nome}</option>
              ))}
            </select>
          </label>

          <label>
            <span className="mb-1 block text-xs font-bold text-slate-400">Prioridade</span>
            <input
              type="number"
              min={0}
              max={100}
              value={priority}
              onChange={(event) =>
                setPriority(Math.min(100, Math.max(0, Number(event.target.value) || 0)))
              }
              disabled={busy}
              className="h-11 w-full rounded-xl border border-slate-600 bg-slate-900 px-3 text-sm text-slate-100 outline-none focus:border-blue-500"
            />
          </label>

          <div className="flex items-end gap-2">
            <Button
              type="button"
              variant="outline"
              className="h-11 border-slate-600 bg-slate-900 text-slate-100 hover:bg-slate-700"
              onClick={() => void refreshPending()}
              disabled={loading || busy}
              aria-label="Atualizar itens pendentes"
            >
              <RefreshCw className={loading ? "animate-spin" : ""} />
            </Button>
            <Button
              type="button"
              className="h-11 bg-blue-600 text-white hover:bg-blue-500"
              onClick={() => void handleRoute()}
              disabled={busy || loading || !selectedItem || !effectiveSectorId || activeSectors.length === 0}
            >
              <ArrowRight />
              <span className="hidden 2xl:inline">Enviar à produção</span>
            </Button>
          </div>
        </div>
      </div>

      {items.length > 0 && activeSectors.length === 0 ? (
        <p className="mt-3 text-xs font-semibold text-amber-300">
          Há item confirmado aguardando produção, mas nenhuma estação ativa está configurada para esta unidade.
        </p>
      ) : null}
    </section>
  );
}
