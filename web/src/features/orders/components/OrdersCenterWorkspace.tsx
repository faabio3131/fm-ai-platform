"use client";

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  ClipboardList,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  cancelOrder,
  confirmOrder,
  getOrderDetail,
  listOrders,
  OrdersApiError,
  sendOrderToConfirmation,
  type OrderCenterDetail,
  type OrderCenterPage,
  type OrderCenterSummary,
} from "@/features/orders/services/orders-api";

const ORDERS_PERMISSION = "pedido.visualizar";
const ALTER_ORDER_PERMISSION = "pedido.alterar";
const CANCEL_ORDER_PERMISSION = "pedido.cancelar";

const CANCELABLE = new Set([
  "rascunho",
  "aguardando_confirmacao",
  "confirmado",
  "enviado_producao",
  "em_preparo",
  "pronto",
  "em_expedicao",
  "saiu_entrega",
]);

type AppliedFilters = {
  search: string;
  status: string;
  channel: string;
  alertsOnly: boolean;
};

const EMPTY_FILTERS: AppliedFilters = {
  search: "",
  status: "",
  channel: "",
  alertsOnly: false,
};

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof OrdersApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

function money(value: string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return value;
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(number);
}

function dateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function statusClass(status: string): string {
  if (["concluido", "pago", "confirmado"].includes(status)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (["cancelado", "falhou"].includes(status)) {
    return "border-red-200 bg-red-50 text-red-700";
  }
  if (["em_preparo", "em_expedicao", "saiu_entrega"].includes(status)) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function OrderRow({
  order,
  selected,
  onSelect,
}: {
  order: OrderCenterSummary;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        "grid w-full gap-3 border-b border-slate-200 px-4 py-4 text-left transition-colors sm:grid-cols-[minmax(0,1.4fr)_0.8fr_0.8fr_0.8fr] sm:items-center",
        selected ? "bg-blue-50" : "bg-white hover:bg-slate-50",
      ].join(" ")}
    >
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-bold text-slate-950">
            {order.pedido_id}
          </p>
          {order.possui_alerta ? (
            <AlertTriangle className="size-4 shrink-0 text-amber-500" />
          ) : null}
        </div>
        <p className="mt-1 text-xs text-slate-500">
          {dateTime(order.criado_em)} · {order.quantidade_itens} item(ns)
        </p>
      </div>
      <div>
        <Badge variant="outline" className={statusClass(order.status)}>
          {humanize(order.status)}
        </Badge>
      </div>
      <div className="text-sm">
        <p className="font-semibold text-slate-800">{humanize(order.canal)}</p>
        <p className="mt-1 text-xs text-slate-500">
          {humanize(order.financeiro.situacao)}
        </p>
      </div>
      <p className="text-sm font-black text-slate-950 sm:text-right">
        {money(order.total)}
      </p>
    </button>
  );
}

export function OrdersCenterWorkspace() {
  const auth = useAuthStore();
  const allowed = auth.permissions.includes(ORDERS_PERMISSION);
  const canAlterOrder = auth.permissions.includes(ALTER_ORDER_PERMISSION);
  const canCancelOrder = auth.permissions.includes(CANCEL_ORDER_PERMISSION);

  const [orders, setOrders] = useState<OrderCenterPage | null>(null);
  const [detail, setDetail] = useState<OrderCenterDetail | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [searchValue, setSearchValue] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [alertsOnly, setAlertsOnly] = useState(false);
  const [appliedFilters, setAppliedFilters] =
    useState<AppliedFilters>(EMPTY_FILTERS);

  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [cancelReason, setCancelReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshOrders = useCallback(
    async (targetPage: number, filters: AppliedFilters) => {
      setLoading(true);
      try {
        const result = await listOrders({
          busca: filters.search,
          status: filters.status,
          canal: filters.channel,
          somenteComAlertas: filters.alertsOnly,
          pagina: targetPage,
          tamanhoPagina: 25,
        });
        setOrders(result);
        setPage(result.pagina);
        setError(null);
        return result;
      } catch (caught) {
        setError(
          errorMessage(
            caught,
            "Não foi possível carregar a Central de Pedidos.",
          ),
        );
        return null;
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const openDetail = useCallback(async (orderId: string) => {
    setSelectedId(orderId);
    setDetailLoading(true);
    setCancelReason("");
    try {
      const result = await getOrderDetail(orderId);
      setDetail(result);
      setError(null);
    } catch (caught) {
      setDetail(null);
      setError(errorMessage(caught, "Não foi possível abrir o pedido."));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !allowed || !auth.unitId) return;

    let cancelled = false;
    const timeoutId = window.setTimeout(() => {
      if (cancelled) return;
      void refreshOrders(1, appliedFilters);
    }, 0);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [auth.status, auth.unitId, allowed, appliedFilters, refreshOrders]);

  const totalPages = useMemo(() => {
    if (!orders || orders.total === 0) return 1;
    return Math.ceil(orders.total / orders.tamanho_pagina);
  }, [orders]);

  function applyFilters() {
    setNotice(null);
    setSelectedId(null);
    setDetail(null);
    setAppliedFilters({
      search: searchValue.trim(),
      status: statusFilter.trim(),
      channel: channelFilter.trim(),
      alertsOnly,
    });
  }

  async function refreshAll() {
    setNotice(null);
    await refreshOrders(page, appliedFilters);
    if (selectedId) await openDetail(selectedId);
  }

  async function handleSendConfirmation() {
    if (!detail || !canAlterOrder) return;
    setActionBusy(true);
    setNotice(null);
    try {
      const result = await sendOrderToConfirmation(
        detail.resumo.pedido_id,
        detail.resumo.versao,
      );
      setNotice(`Pedido avançado para ${humanize(result.status)}.`);
      await refreshOrders(page, appliedFilters);
      await openDetail(result.pedido_id);
    } catch (caught) {
      if (caught instanceof OrdersApiError && caught.status === 409) {
        setError(
          "O pedido mudou em outro terminal. A Central foi atualizada; revise o estado antes de repetir a ação.",
        );
        await refreshAll();
      } else {
        setError(errorMessage(caught, "Não foi possível avançar o pedido."));
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function handleConfirmOrder() {
    if (!detail || !canAlterOrder) return;
    setActionBusy(true);
    setNotice(null);
    try {
      const result = await confirmOrder(
        detail.resumo.pedido_id,
        detail.resumo.versao,
      );
      setNotice("Pedido confirmado. Agora ele pode ser roteado para a produção.");
      await refreshOrders(page, appliedFilters);
      await openDetail(result.pedido_id);
    } catch (caught) {
      if (caught instanceof OrdersApiError && caught.status === 409) {
        setError(
          "O pedido mudou em outro terminal. A Central foi atualizada; revise o estado antes de repetir a ação.",
        );
        await refreshAll();
      } else {
        setError(errorMessage(caught, "Não foi possível confirmar o pedido."));
      }
    } finally {
      setActionBusy(false);
    }
  }

  async function handleCancel() {
    if (!detail || !canCancelOrder || !cancelReason.trim()) return;
    setActionBusy(true);
    setNotice(null);
    try {
      const result = await cancelOrder(
        detail.resumo.pedido_id,
        detail.resumo.versao,
        cancelReason.trim(),
      );
      setNotice("Pedido cancelado com trilha de auditoria.");
      setCancelReason("");
      await refreshOrders(page, appliedFilters);
      await openDetail(result.pedido_id);
    } catch (caught) {
      if (caught instanceof OrdersApiError && caught.status === 409) {
        setError(
          "O pedido mudou em outro terminal. A Central foi atualizada; revise o estado antes de repetir a ação.",
        );
        await refreshAll();
      } else {
        setError(errorMessage(caught, "Não foi possível cancelar o pedido."));
      }
    } finally {
      setActionBusy(false);
    }
  }

  if (auth.status === "authenticated" && !allowed) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-100 px-6 py-12">
        <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
          <ShieldAlert className="size-9 text-amber-500" />
          <h1 className="mt-4 text-xl font-black text-slate-950">
            Central de Pedidos não liberada
          </h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Sua sessão é válida, mas sua função não possui permissão para
            visualizar pedidos.
          </p>
          <Button asChild className="mt-6 w-full">
            <Link href="/">Voltar à visão geral</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-100 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1700px] space-y-5">
        <header className="flex flex-col gap-4 rounded-3xl bg-slate-950 p-6 text-white shadow-xl shadow-slate-950/10 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-blue-600">
              <ClipboardList className="size-6" />
            </div>
            <div className="min-w-0">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-300">
                Operação omnichannel
              </p>
              <h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">
                Central de Pedidos
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                Uma única visão para pedidos de balcão, salão e canais
                integrados.
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Button
              type="button"
              variant="outline"
              className="border-slate-700 bg-slate-900 text-white hover:bg-slate-800 hover:text-white"
              onClick={() => void refreshAll()}
              disabled={loading || detailLoading}
            >
              <RefreshCw className={loading ? "animate-spin" : ""} />
              Atualizar
            </Button>
            <Button
              asChild
              variant="ghost"
              className="text-slate-300 hover:bg-slate-800 hover:text-white"
            >
              <Link href="/">
                <ChevronLeft />
                Dashboard
              </Link>
            </Button>
          </div>
        </header>

        <section className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
          <div className="grid gap-3 lg:grid-cols-[minmax(220px,1.5fr)_minmax(160px,0.8fr)_minmax(160px,0.8fr)_auto_auto]">
            <label className="relative block">
              <Search className="pointer-events-none absolute left-3 top-3.5 size-4 text-slate-400" />
              <input
                value={searchValue}
                onChange={(event) => setSearchValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") applyFilters();
                }}
                placeholder="Buscar pedido ou cliente"
                className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50 pl-9 pr-3 text-sm outline-none transition focus:border-blue-500 focus:bg-white"
              />
            </label>
            <input
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              placeholder="Status"
              className="h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-blue-500 focus:bg-white"
            />
            <input
              value={channelFilter}
              onChange={(event) => setChannelFilter(event.target.value)}
              placeholder="Canal"
              className="h-11 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm outline-none focus:border-blue-500 focus:bg-white"
            />
            <label className="flex h-11 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 text-sm font-medium text-slate-600">
              <input
                type="checkbox"
                checked={alertsOnly}
                onChange={(event) => setAlertsOnly(event.target.checked)}
                className="size-4 accent-blue-600"
              />
              Só alertas
            </label>
            <Button type="button" onClick={applyFilters} disabled={loading}>
              Filtrar
            </Button>
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-700">
            {notice}
          </div>
        ) : null}

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(380px,0.8fr)]">
          <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
            <div className="flex items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
              <div>
                <h2 className="font-black text-slate-950">Fila unificada</h2>
                <p className="mt-1 text-xs text-slate-500">
                  {orders
                    ? `${orders.total} pedido(s) no conjunto atual`
                    : "Carregando pedidos"}
                </p>
              </div>
              {loading ? (
                <RefreshCw className="size-4 animate-spin text-blue-600" />
              ) : null}
            </div>

            <div className="min-h-80">
              {orders?.itens.length ? (
                orders.itens.map((order) => (
                  <OrderRow
                    key={order.pedido_id}
                    order={order}
                    selected={selectedId === order.pedido_id}
                    onSelect={() => void openDetail(order.pedido_id)}
                  />
                ))
              ) : !loading ? (
                <div className="flex min-h-80 items-center justify-center px-6 text-center text-sm text-slate-500">
                  Nenhum pedido encontrado para os filtros atuais.
                </div>
              ) : null}
            </div>

            <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={loading || page <= 1}
                onClick={() => void refreshOrders(page - 1, appliedFilters)}
              >
                <ChevronLeft />
                Anterior
              </Button>
              <span className="text-xs font-semibold text-slate-500">
                Página {page} de {totalPages}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={loading || page >= totalPages}
                onClick={() => void refreshOrders(page + 1, appliedFilters)}
              >
                Próxima
                <ChevronRight />
              </Button>
            </div>
          </section>

          <aside className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm xl:sticky xl:top-4 xl:self-start">
            {detailLoading ? (
              <div className="flex min-h-96 items-center justify-center">
                <RefreshCw className="size-6 animate-spin text-blue-600" />
              </div>
            ) : detail ? (
              <div className="space-y-5">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-600">
                      Detalhe operacional
                    </p>
                    <h2 className="mt-1 truncate text-lg font-black text-slate-950">
                      {detail.resumo.pedido_id}
                    </h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {dateTime(detail.resumo.criado_em)} · versão{" "}
                      {detail.resumo.versao}
                    </p>
                  </div>
                  <Badge
                    variant="outline"
                    className={statusClass(detail.resumo.status)}
                  >
                    {humanize(detail.resumo.status)}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl bg-slate-50 p-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Total
                    </p>
                    <p className="mt-1 text-lg font-black text-slate-950">
                      {money(detail.resumo.total)}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-slate-50 p-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                      Financeiro
                    </p>
                    <p className="mt-1 text-sm font-bold capitalize text-slate-800">
                      {humanize(detail.financeiro.situacao)}
                    </p>
                  </div>
                </div>

                {detail.alertas.length ? (
                  <div className="space-y-2">
                    {detail.alertas.map((alert, index) => (
                      <div
                        key={`${alert.tipo}-${index}`}
                        className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
                      >
                        <span className="font-bold">
                          {humanize(alert.tipo)}:
                        </span>{" "}
                        {alert.mensagem}
                      </div>
                    ))}
                  </div>
                ) : null}

                <div>
                  <h3 className="text-sm font-black text-slate-900">Itens</h3>
                  <div className="mt-2 divide-y divide-slate-100 rounded-2xl border border-slate-200">
                    {detail.itens.map((item) => (
                      <div key={item.item_id} className="px-3 py-3">
                        <div className="flex justify-between gap-3 text-sm">
                          <span className="font-semibold text-slate-800">
                            {item.quantidade}× {item.nome}
                          </span>
                          <span className="font-bold text-slate-950">
                            {money(item.subtotal)}
                          </span>
                        </div>
                        {item.observacao ? (
                          <p className="mt-1 text-xs text-slate-500">
                            {item.observacao}
                          </p>
                        ) : null}
                        {item.adicionais.map(
                          ([name, quantity, , subtotal], index) => (
                            <p
                              key={`${name}-${index}`}
                              className="mt-1 text-xs text-slate-500"
                            >
                              + {quantity}× {name} · {money(subtotal)}
                            </p>
                          ),
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="flex items-center gap-2">
                    <CircleDollarSign className="size-4 text-emerald-600" />
                    <h3 className="text-sm font-black text-slate-900">
                      Pagamento
                    </h3>
                  </div>
                  <div className="mt-2 rounded-2xl bg-slate-50 p-3 text-xs text-slate-600">
                    <p>
                      Previsto:{" "}
                      <strong>{money(detail.financeiro.valor_previsto)}</strong>
                    </p>
                    <p className="mt-1">
                      Pago: <strong>{money(detail.financeiro.valor_pago)}</strong>
                    </p>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-black text-slate-900">
                    Timeline
                  </h3>
                  <div className="mt-2 max-h-44 space-y-2 overflow-auto pr-1">
                    {detail.timeline.map((event) => (
                      <div
                        key={event.evento_id}
                        className="border-l-2 border-blue-200 pl-3 text-xs"
                      >
                        <p className="font-semibold text-slate-700">
                          {humanize(event.tipo)}
                        </p>
                        <p className="mt-0.5 text-slate-400">
                          {dateTime(event.ocorrido_em)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>

                {detail.resumo.status === "rascunho" && canAlterOrder ? (
                  <Button
                    className="w-full"
                    disabled={actionBusy}
                    onClick={() => void handleSendConfirmation()}
                  >
                    <Send />
                    Enviar para confirmação
                  </Button>
                ) : null}

                {detail.resumo.status === "aguardando_confirmacao" &&
                canAlterOrder ? (
                  <Button
                    className="w-full"
                    disabled={actionBusy}
                    onClick={() => void handleConfirmOrder()}
                  >
                    <CheckCircle2 />
                    Confirmar pedido
                  </Button>
                ) : null}

                {CANCELABLE.has(detail.resumo.status) && canCancelOrder ? (
                  <div className="rounded-2xl border border-red-100 bg-red-50/50 p-3">
                    <label
                      className="text-xs font-bold text-red-800"
                      htmlFor="cancel-reason"
                    >
                      Cancelar pedido
                    </label>
                    <textarea
                      id="cancel-reason"
                      value={cancelReason}
                      onChange={(event) => setCancelReason(event.target.value)}
                      placeholder="Informe o motivo do cancelamento"
                      className="mt-2 min-h-20 w-full resize-none rounded-xl border border-red-200 bg-white p-3 text-sm outline-none focus:border-red-400"
                    />
                    <Button
                      type="button"
                      variant="destructive"
                      className="mt-2 w-full"
                      disabled={actionBusy || !cancelReason.trim()}
                      onClick={() => void handleCancel()}
                    >
                      <Ban />
                      Confirmar cancelamento
                    </Button>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex min-h-96 flex-col items-center justify-center px-5 text-center">
                <ClipboardList className="size-9 text-slate-300" />
                <p className="mt-3 text-sm font-semibold text-slate-700">
                  Selecione um pedido
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  Itens, financeiro, alertas, timeline e ações aparecerão aqui.
                </p>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
