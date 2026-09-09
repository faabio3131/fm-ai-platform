"use client";

import {
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  PackageCheck,
  RefreshCw,
  Route,
  ShieldAlert,
  Truck,
  UserRoundCheck,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  assignDriver,
  collectDelivery,
  completeChecklist,
  confirmDelivered,
  EntregaApiError,
  getEntregaDetail,
  listEligibleDrivers,
  listEntregas,
  registerFailedAttempt,
  startRoute,
  type EntregaDetail,
  type EntregaItem,
  type EntregadorElegivel,
} from "@/features/entrega/services/entrega-api";

const DELIVERY_PERMISSION = "expedicao.operar";
const EXPEDITION_ROLES = new Set(["expedicao", "gerente", "administrador"]);

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof EntregaApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

function dateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function statusClass(status: string): string {
  if (status === "entregue") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (["cancelada", "tentativa_falhou"].includes(status)) {
    return "border-red-200 bg-red-50 text-red-700";
  }
  if (["coletada", "em_rota", "atribuida"].includes(status)) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  return "border-amber-200 bg-amber-50 text-amber-700";
}

export function EntregaWorkspace() {
  const auth = useAuthStore();
  const allowed = auth.permissions.includes(DELIVERY_PERMISSION);
  const roles = auth.operator?.papeis ?? [];
  const expeditionProfile = roles.some((role) => EXPEDITION_ROLES.has(role));
  const courierProfile = roles.includes("entregador");

  const [deliveries, setDeliveries] = useState<EntregaItem[]>([]);
  const [drivers, setDrivers] = useState<EntregadorElegivel[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntregaDetail | null>(null);
  const [selectedDriver, setSelectedDriver] = useState("");
  const [checklist, setChecklist] = useState({
    itens: false,
    embalagem: false,
    identificacao: false,
    observacao: "",
  });
  const [proofReference, setProofReference] = useState("");
  const [failedReason, setFailedReason] = useState("cliente ausente");
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshBoard = useCallback(async () => {
    setLoading(true);
    try {
      const [items, eligible] = await Promise.all([
        listEntregas(),
        expeditionProfile ? listEligibleDrivers() : Promise.resolve([]),
      ]);
      setDeliveries(items);
      setDrivers(eligible);
      setError(null);
      return items;
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível carregar a operação logística."));
      return [];
    } finally {
      setLoading(false);
    }
  }, [expeditionProfile]);

  const openDetail = useCallback(async (deliveryId: string) => {
    setSelectedId(deliveryId);
    setDetailLoading(true);
    try {
      const result = await getEntregaDetail(deliveryId);
      setDetail(result);
      setSelectedDriver(result.entrega.entregador_id ?? "");
      setProofReference(result.entrega.prova_entrega_ref ?? `proof://${result.entrega.pedido_id}`);
      setError(null);
    } catch (caught) {
      setDetail(null);
      setError(errorMessage(caught, "Não foi possível abrir a entrega."));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !allowed || !auth.unitId) return;
    const timeoutId = window.setTimeout(() => void refreshBoard(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, allowed, refreshBoard]);

  async function refreshAll() {
    setNotice(null);
    const items = await refreshBoard();
    if (selectedId && items.some((item) => item.entrega_id === selectedId)) {
      await openDetail(selectedId);
    }
  }

  async function runAction(action: () => Promise<EntregaItem>, success: string) {
    if (!detail) return;
    setActionBusy(true);
    setNotice(null);
    try {
      const updated = await action();
      setNotice(success);
      await refreshBoard();
      await openDetail(updated.entrega_id);
    } catch (caught) {
      if (caught instanceof EntregaApiError && caught.status === 409) {
        setError("A entrega mudou em outro terminal. O quadro foi atualizado; revise o estado antes de repetir a ação.");
        await refreshAll();
      } else {
        setError(errorMessage(caught, "Não foi possível concluir a ação logística."));
      }
    } finally {
      setActionBusy(false);
    }
  }

  const selected = detail?.entrega ?? null;
  const canChecklist = expeditionProfile && selected?.status === "aguardando_expedicao";
  const canAssign =
    expeditionProfile &&
    Boolean(selected) &&
    [
      "aguardando_producao",
      "aguardando_expedicao",
      "aguardando_entregador",
      "tentativa_falhou",
    ].includes(selected?.status ?? "");
  const canCollect = courierProfile && selected?.status === "atribuida";
  const canRoute = courierProfile && selected?.status === "coletada";
  const canCloseRoute = courierProfile && selected?.status === "em_rota";

  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const delivery of deliveries) {
      result.set(delivery.status, (result.get(delivery.status) ?? 0) + 1);
    }
    return result;
  }, [deliveries]);

  if (auth.status === "authenticated" && !allowed) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-100 p-6">
        <div className="max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
          <ShieldAlert className="size-9 text-amber-500" />
          <h1 className="mt-4 text-xl font-black text-slate-950">Expedição e Entrega não liberada</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Sua sessão é válida, mas não possui a permissão operacional de expedição.
          </p>
          <Button asChild className="mt-6 w-full"><Link href="/">Voltar ao Dashboard</Link></Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-100 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1700px] space-y-5">
        <header className="flex flex-col gap-4 rounded-3xl bg-slate-950 p-6 text-white shadow-xl shadow-slate-950/10 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-600"><Truck className="size-6" /></div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-300">Logística operacional</p>
              <h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">Expedição e Entrega</h1>
              <p className="mt-1 text-sm text-slate-400">Checklist, atribuição governada, custódia, rota e prova de entrega.</p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" className="border-slate-700 bg-slate-900 text-white hover:bg-slate-800 hover:text-white" onClick={() => void refreshAll()} disabled={loading || actionBusy}>
              <RefreshCw className="size-4" /> Atualizar
            </Button>
            <Button asChild variant="outline" className="border-slate-700 bg-slate-900 text-white hover:bg-slate-800 hover:text-white">
              <Link href="/"><ArrowLeft className="size-4" /> Dashboard</Link>
            </Button>
          </div>
        </header>

        {error ? <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">{error}</div> : null}
        {notice ? <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">{notice}</div> : null}

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Aguardando expedição", counts.get("aguardando_expedicao") ?? 0],
            ["Aguardando entregador", counts.get("aguardando_entregador") ?? 0],
            ["Em rota", counts.get("em_rota") ?? 0],
            ["Entregues", counts.get("entregue") ?? 0],
          ].map(([label, count]) => (
            <div key={String(label)} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
              <p className="mt-2 text-2xl font-black text-slate-950">{count}</p>
            </div>
          ))}
        </div>

        <section className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
          <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-5">
              <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600">Fila logística</p>
              <p className="mt-1 text-sm text-slate-500">{deliveries.length} entrega(s) na sua alçada.</p>
            </div>
            {deliveries.length === 0 ? (
              <div className="p-8 text-center text-sm text-slate-500">{loading ? "Carregando operação…" : "Nenhuma entrega disponível."}</div>
            ) : deliveries.map((delivery) => (
              <button
                key={delivery.entrega_id}
                type="button"
                onClick={() => void openDetail(delivery.entrega_id)}
                className={`grid w-full gap-3 border-b border-slate-200 p-4 text-left transition-colors sm:grid-cols-[1.3fr_0.8fr_0.8fr] sm:items-center ${selectedId === delivery.entrega_id ? "bg-blue-50" : "hover:bg-slate-50"}`}
              >
                <div className="min-w-0"><p className="truncate text-sm font-black text-slate-950">Pedido {delivery.pedido_id}</p><p className="mt-1 text-xs text-slate-500">Tentativa {delivery.tentativa} · v{delivery.versao}</p></div>
                <Badge variant="outline" className={statusClass(delivery.status)}>{humanize(delivery.status)}</Badge>
                <p className="truncate text-sm text-slate-600">{delivery.entregador_id ?? "sem entregador"}</p>
              </button>
            ))}
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            {!selected ? (
              <div className="flex min-h-72 flex-col items-center justify-center text-center"><PackageCheck className="size-9 text-slate-300" /><p className="mt-3 text-sm font-bold text-slate-700">Selecione uma entrega</p><p className="mt-1 text-sm text-slate-500">O detalhe operacional e as ações autorizadas aparecem aqui.</p></div>
            ) : detailLoading ? (
              <div className="min-h-72 p-6 text-sm text-slate-500">Carregando detalhe…</div>
            ) : (
              <div className="space-y-5">
                <div className="flex items-start justify-between gap-3">
                  <div><p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600">Detalhe operacional</p><h2 className="mt-1 text-lg font-black text-slate-950">{selected.pedido_id}</h2><p className="mt-1 text-xs text-slate-500">Entrega {selected.entrega_id} · versão {selected.versao}</p></div>
                  <Badge variant="outline" className={statusClass(selected.status)}>{humanize(selected.status)}</Badge>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Entregador</p><p className="mt-1 text-sm font-bold text-slate-950">{selected.entregador_id ?? "não atribuído"}</p></div>
                  <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Tentativa</p><p className="mt-1 text-sm font-bold text-slate-950">{selected.tentativa}</p></div>
                </div>

                <div className="grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
                  <p>Produção pronta: <strong>{dateTime(selected.producao_pronta_em)}</strong></p>
                  <p>Checklist: <strong>{dateTime(selected.checklist_concluido_em)}</strong></p>
                  <p>Coleta: <strong>{dateTime(selected.coletada_em)}</strong></p>
                  <p>Saída: <strong>{dateTime(selected.saiu_em)}</strong></p>
                </div>

                {canChecklist ? (
                  <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4">
                    <div className="flex items-center gap-2 text-sm font-black text-blue-900"><ClipboardCheck className="size-4" /> Checklist de expedição</div>
                    <div className="mt-3 space-y-2 text-sm text-blue-950">
                      {[
                        ["itens", "Itens conferidos"],
                        ["embalagem", "Embalagem conferida"],
                        ["identificacao", "Identificação conferida"],
                      ].map(([key, label]) => (
                        <label key={key} className="flex items-center gap-2"><input type="checkbox" checked={checklist[key as "itens" | "embalagem" | "identificacao"] as boolean} onChange={(event) => setChecklist((current) => ({ ...current, [key]: event.target.checked }))} /> {label}</label>
                      ))}
                    </div>
                    <Input className="mt-3 bg-white" placeholder="Observação operacional (opcional)" value={checklist.observacao} onChange={(event) => setChecklist((current) => ({ ...current, observacao: event.target.value }))} />
                    <Button className="mt-3 w-full" disabled={!checklist.itens || !checklist.embalagem || !checklist.identificacao || actionBusy} onClick={() => void runAction(() => completeChecklist(selected.entrega_id, selected.versao, { itens_conferidos: checklist.itens, embalagem_conferida: checklist.embalagem, identificacao_conferida: checklist.identificacao, observacao_operacional: checklist.observacao.trim() || undefined }), "Checklist concluído e custódia liberada para a próxima etapa.")}>
                      <CheckCircle2 className="size-4" /> Concluir checklist
                    </Button>
                  </div>
                ) : null}

                {canAssign ? (
                  <div className="rounded-2xl border border-slate-200 p-4">
                    <div className="flex items-center gap-2 text-sm font-black text-slate-950"><UserRoundCheck className="size-4 text-blue-600" /> Atribuição governada</div>
                    <select value={selectedDriver} onChange={(event) => setSelectedDriver(event.target.value)} className="mt-3 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm">
                      <option value="">Selecione um entregador elegível</option>
                      {drivers.map((driver) => <option key={driver.usuario_id} value={driver.usuario_id}>{driver.email}</option>)}
                    </select>
                    <Button variant="outline" className="mt-3 w-full" disabled={!selectedDriver || actionBusy} onClick={() => void runAction(() => assignDriver(selected.entrega_id, selected.versao, selectedDriver), "Entregador atribuído e revalidado no escopo da unidade.")}>
                      Atribuir entregador
                    </Button>
                  </div>
                ) : null}

                {canCollect ? <Button className="w-full" disabled={actionBusy} onClick={() => void runAction(() => collectDelivery(selected.entrega_id, selected.versao), "Coleta confirmada; custódia transferida ao entregador.")}><PackageCheck className="size-4" /> Confirmar coleta</Button> : null}
                {canRoute ? <Button className="w-full" disabled={actionBusy} onClick={() => void runAction(() => startRoute(selected.entrega_id, selected.versao), "Entrega saiu em rota.")}><Route className="size-4" /> Sair em rota</Button> : null}

                {canCloseRoute ? (
                  <div className="space-y-3 rounded-2xl border border-slate-200 p-4">
                    <p className="text-sm font-black text-slate-950">Fechamento de rota</p>
                    <Input placeholder="Referência da prova de entrega" value={proofReference} onChange={(event) => setProofReference(event.target.value)} />
                    <Button className="w-full" disabled={!proofReference.trim() || actionBusy} onClick={() => void runAction(() => confirmDelivered(selected.entrega_id, selected.versao, proofReference.trim()), "Entrega confirmada com prova registrada.")}>
                      <CheckCircle2 className="size-4" /> Confirmar entrega
                    </Button>
                    <Input placeholder="Motivo da tentativa sem sucesso" value={failedReason} onChange={(event) => setFailedReason(event.target.value)} />
                    <Button variant="outline" className="w-full" disabled={!failedReason.trim() || actionBusy} onClick={() => void runAction(() => registerFailedAttempt(selected.entrega_id, selected.versao, failedReason.trim()), "Tentativa sem sucesso registrada para nova tratativa.")}>
                      Registrar tentativa sem sucesso
                    </Button>
                  </div>
                ) : null}

                <div>
                  <p className="text-sm font-black text-slate-950">Timeline</p>
                  <div className="mt-2 max-h-64 space-y-2 overflow-auto">
                    {detail?.eventos.length ? detail.eventos.map((event) => (
                      <div key={event.event_id} className="rounded-xl border border-slate-200 p-3 text-sm"><strong>{humanize(event.tipo)}</strong><p className="mt-1 text-xs text-slate-500">{dateTime(event.ocorrido_em)} · v{event.versao_entrega}</p></div>
                    )) : <p className="text-sm text-slate-500">Nenhum evento registrado.</p>}
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
