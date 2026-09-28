"use client";

import { LockKeyhole, RefreshCw, Store } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  listMarketplaceIntegrations,
  syncMarketplace,
  type MarketplaceIntegration,
} from "@/features/orders/services/marketplaces-api";

const MARKETPLACES_OPERACIONAIS = [
  { id: "ifood", label: "iFood" },
  { id: "keeta", label: "Keeta" },
] as const;

export function MarketplaceChannelPanel({
  onOrdersChanged,
}: {
  onOrdersChanged: () => Promise<void>;
}) {
  const auth = useAuthStore();
  const canView = auth.permissions.includes("pedido.visualizar");
  const canManage = auth.permissions.includes("integracao.gerenciar");
  const [integrations, setIntegrations] = useState<MarketplaceIntegration[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!canView || auth.status !== "authenticated" || !auth.unitId) return;
    setLoading(true);
    try {
      setIntegrations(await listMarketplaceIntegrations());
      setMessage(null);
    } catch (caught) {
      setMessage(
        caught instanceof Error
          ? caught.message
          : "Não foi possível consultar os marketplaces.",
      );
    } finally {
      setLoading(false);
    }
  }, [auth.status, auth.unitId, canView]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      void load();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [load]);

  async function sync(item: MarketplaceIntegration) {
    setBusyId(item.configuracao_id);
    setMessage(null);
    try {
      const result = await syncMarketplace(item.configuracao_id);
      setMessage(
        `${item.plataforma}: ${result.processados} processado(s), ${result.duplicados} duplicado(s), ${result.retry} retry, ${result.dlq} DLQ.`,
      );
      await Promise.all([load(), onOrdersChanged()]);
    } catch (caught) {
      setMessage(
        caught instanceof Error
          ? caught.message
          : "A sincronização do marketplace falhou.",
      );
    } finally {
      setBusyId(null);
    }
  }

  const porPlataforma = useMemo(
    () => new Map(integrations.map((item) => [item.plataforma, item])),
    [integrations],
  );

  if (!canView) return null;

  return (
    <section className="rounded-3xl border border-slate-700/60 bg-[linear-gradient(145deg,rgba(15,30,51,0.98),rgba(8,20,36,0.98))] p-4 shadow-[0_22px_56px_-34px_rgba(0,0,0,0.82)] sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-200 ring-1 ring-violet-300/15">
            <Store className="size-5" />
          </div>
          <div>
            <h2 className="text-sm font-black text-slate-100">
              Canais marketplace
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              iFood, Keeta e 99Food convergem para a mesma Central de Pedidos quando homologados.
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void load()}
          disabled={loading || busyId !== null}
        >
          <RefreshCw className={loading ? "animate-spin" : ""} />
          Atualizar canais
        </Button>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {MARKETPLACES_OPERACIONAIS.map((canal) => {
          const item = porPlataforma.get(canal.id);
          return (
            <div
              key={canal.id}
              className="rounded-2xl border border-slate-700/60 bg-slate-950/32 p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-black text-slate-100">{canal.label}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {item
                      ? `${item.conta_externa} · ${item.ambiente} · ${item.pedidos_sincronizados} pedido(s) vinculados`
                      : "Canal ainda não configurado para a unidade ativa."}
                  </p>
                </div>
                <Badge
                  variant="outline"
                  className={
                    item?.pronta_para_sincronizar
                      ? "border-emerald-300/20 bg-emerald-400/[0.08] text-emerald-200"
                      : "border-amber-300/20 bg-amber-400/[0.08] text-amber-200"
                  }
                >
                  {item?.pronta_para_sincronizar
                    ? "homologado"
                    : item
                      ? "bloqueado"
                      : "não configurado"}
                </Badge>
              </div>

              {item && canManage ? (
                <Button
                  type="button"
                  size="sm"
                  className="mt-3 w-full"
                  disabled={!item.pronta_para_sincronizar || busyId !== null || loading}
                  onClick={() => void sync(item)}
                  title="A sincronização manual também exige step-up administrativo no servidor."
                >
                  <RefreshCw className={busyId === item.configuracao_id ? "animate-spin" : ""} />
                  Sincronizar agora
                </Button>
              ) : (
                <div className="mt-3 flex items-center gap-2 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2 text-[11px] text-slate-500">
                  <LockKeyhole className="size-3.5 shrink-0" />
                  Credenciais e sincronização manual permanecem protegidas.
                </div>
              )}
            </div>
          );
        })}

        <div className="rounded-2xl border border-amber-300/15 bg-amber-400/[0.035] p-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-black text-slate-100">99Food</p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Adapter técnico preparado no Core. O runtime Web real permanece fail-closed até contrato,
                credenciais e homologação verificáveis do parceiro.
              </p>
            </div>
            <Badge
              variant="outline"
              className="border-amber-300/20 bg-amber-400/[0.08] text-amber-200"
            >
              homologação pendente
            </Badge>
          </div>
          <div className="mt-3 flex items-center gap-2 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2 text-[11px] text-slate-500">
            <LockKeyhole className="size-3.5 shrink-0" />
            Nenhuma operação real é liberada até a integração parceira ser certificada.
          </div>
        </div>
      </div>

      {message ? (
        <p className="mt-3 text-xs font-medium text-slate-400" role="status">
          {message}
        </p>
      ) : null}
    </section>
  );
}
