"use client";

import { RefreshCw, Store } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  listMarketplaceIntegrations,
  syncMarketplace,
  type MarketplaceIntegration,
} from "@/features/orders/services/marketplaces-api";

export function MarketplaceChannelPanel({
  onOrdersChanged,
}: {
  onOrdersChanged: () => Promise<void>;
}) {
  const auth = useAuthStore();
  const canManage = auth.permissions.includes("integracao.gerenciar");
  const [integrations, setIntegrations] = useState<MarketplaceIntegration[]>([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!canManage || auth.status !== "authenticated" || !auth.unitId) return;
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
  }, [auth.status, auth.unitId, canManage]);

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

  if (!canManage) return null;

  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-xl bg-violet-50 text-violet-700">
            <Store className="size-5" />
          </div>
          <div>
            <h2 className="text-sm font-black text-slate-950">
              Canais marketplace
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              A entrada converge para esta mesma Central de Pedidos.
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

      {integrations.length ? (
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {integrations.map((item) => (
            <div
              key={item.configuracao_id}
              className="rounded-2xl border border-slate-200 bg-slate-50 p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-black capitalize text-slate-900">
                    {item.plataforma}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {item.conta_externa} · {item.ambiente} ·{" "}
                    {item.pedidos_sincronizados} pedido(s) vinculados
                  </p>
                </div>
                <Badge
                  variant="outline"
                  className={
                    item.pronta_para_sincronizar
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-amber-200 bg-amber-50 text-amber-700"
                  }
                >
                  {item.pronta_para_sincronizar ? "homologado" : "bloqueado"}
                </Badge>
              </div>
              <Button
                type="button"
                size="sm"
                className="mt-3 w-full"
                disabled={
                  !item.pronta_para_sincronizar ||
                  busyId !== null ||
                  loading
                }
                onClick={() => void sync(item)}
              >
                <RefreshCw
                  className={
                    busyId === item.configuracao_id ? "animate-spin" : ""
                  }
                />
                Sincronizar agora
              </Button>
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-4 text-xs text-slate-500">
          Nenhum marketplace configurado para a unidade ativa. Configure iFood
          ou Keeta em Integrações e Credenciais.
        </p>
      )}

      {message ? (
        <p className="mt-3 text-xs font-medium text-slate-600" role="status">
          {message}
        </p>
      ) : null}
    </section>
  );
}
