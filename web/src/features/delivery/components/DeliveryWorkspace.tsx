"use client";

import {
  ArrowLeft,
  Bike,
  MapPin,
  PackagePlus,
  RefreshCw,
  ShieldAlert,
  ShoppingBag,
  Truck,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  addDeliveryItem,
  cancelDeliveryOrder,
  confirmDeliveryOrder,
  DeliveryApiError,
  getDeliveryContext,
  getDeliveryTracking,
  listDeliveryClients,
  openDeliveryCart,
  quoteDelivery,
  type DeliveryCart,
  type DeliveryClient,
  type DeliveryContext,
  type DeliveryTracking,
} from "@/features/delivery/services/delivery-api";

const VIEW_PERMISSIONS = ["cliente.visualizar", "pedido.visualizar"];
const CREATE_PERMISSION = "pedido.criar";
const ALTER_PERMISSION = "pedido.alterar";
const CANCEL_PERMISSION = "pedido.cancelar";
const PAYMENT_PERMISSION = "pagamento.registrar";

const PAYMENT_OPTIONS = [
  ["pix", "Pix"],
  ["cartao_credito", "Cartão de crédito"],
  ["cartao_debito", "Cartão de débito"],
  ["pagamento_na_entrega", "Pagamento na entrega"],
] as const;

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function money(value: string): string {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return value;
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(parsed);
}

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof DeliveryApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

function statusClass(value: string): string {
  if (["confirmado", "entregue"].includes(value)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-700";
  }
  if (["cancelado", "cancelada", "tentativa_falhou"].includes(value)) {
    return "border-red-200 bg-red-50 text-red-700";
  }
  if (["em_rota", "coletada", "aguardando_expedicao"].includes(value)) {
    return "border-blue-200 bg-blue-50 text-blue-700";
  }
  return "border-amber-200 bg-amber-50 text-amber-700";
}

export function DeliveryWorkspace() {
  const auth = useAuthStore();
  const allowed = VIEW_PERMISSIONS.every((permission) =>
    auth.permissions.includes(permission),
  );
  const canCreate = auth.permissions.includes(CREATE_PERMISSION);
  const canConfirm =
    canCreate &&
    auth.permissions.includes(ALTER_PERMISSION) &&
    auth.permissions.includes(PAYMENT_PERMISSION);
  const canCancel =
    auth.permissions.includes(CANCEL_PERMISSION) &&
    auth.permissions.includes(ALTER_PERMISSION) &&
    auth.permissions.includes(PAYMENT_PERMISSION);

  const [clients, setClients] = useState<DeliveryClient[]>([]);
  const [clientId, setClientId] = useState("");
  const [context, setContext] = useState<DeliveryContext | null>(null);
  const [cart, setCart] = useState<DeliveryCart | null>(null);
  const [tracking, setTracking] = useState<DeliveryTracking | null>(null);
  const [paymentMethod, setPaymentMethod] = useState("pix");
  const [cancelReason, setCancelReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadClients = useCallback(async () => {
    setLoading(true);
    try {
      setClients(await listDeliveryClients());
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível carregar os clientes do Delivery."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth.status !== "authenticated" || !allowed || !auth.unitId) return;
    const timeoutId = window.setTimeout(() => void loadClients(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, allowed, loadClients]);

  async function selectClient(value: string) {
    setClientId(value);
    setContext(null);
    setCart(null);
    setTracking(null);
    setNotice(null);
    setError(null);
    if (!value) return;

    setLoading(true);
    try {
      setContext(await getDeliveryContext(value));
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível resolver o contexto do cliente."));
    } finally {
      setLoading(false);
    }
  }

  async function startCart() {
    if (!clientId || !canCreate) return;
    setActionBusy(true);
    setNotice(null);
    setTracking(null);
    try {
      const result = await openDeliveryCart(clientId, `web-${crypto.randomUUID()}`);
      setCart(result);
      setError(null);
      setNotice("Novo pedido Delivery iniciado.");
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível iniciar o pedido Delivery."));
    } finally {
      setActionBusy(false);
    }
  }

  async function addProduct(productId: string) {
    if (!cart || !clientId || !canCreate) return;
    setActionBusy(true);
    setNotice(null);
    try {
      setCart(
        await addDeliveryItem(clientId, cart.carrinho_id, productId, cart.versao),
      );
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível adicionar o produto."));
    } finally {
      setActionBusy(false);
    }
  }

  async function calculateQuote() {
    if (!cart || !clientId || !canCreate) return;
    setActionBusy(true);
    setNotice(null);
    try {
      const result = await quoteDelivery(clientId, cart.carrinho_id, cart.versao);
      setCart(result);
      setError(null);
      setNotice("Taxa e SLA calculados pela política da unidade.");
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível calcular a entrega."));
    } finally {
      setActionBusy(false);
    }
  }

  async function confirmOrder() {
    if (!cart || !clientId || !canConfirm) return;
    setActionBusy(true);
    setNotice(null);
    try {
      const result = await confirmDeliveryOrder(
        clientId,
        cart.carrinho_id,
        paymentMethod,
      );
      const currentTracking = await getDeliveryTracking(clientId, result.pedido_id);
      setTracking(currentTracking);
      setError(null);
      setNotice("Pedido confirmado no fluxo canônico e vinculado à logística.");
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível confirmar o pedido."));
    } finally {
      setActionBusy(false);
    }
  }

  async function refreshTracking() {
    if (!tracking || !clientId) return;
    setActionBusy(true);
    try {
      setTracking(await getDeliveryTracking(clientId, tracking.pedido_id));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível atualizar o acompanhamento."));
    } finally {
      setActionBusy(false);
    }
  }

  async function cancelOrder() {
    if (!tracking || !clientId || !canCancel || !cancelReason.trim()) return;
    setActionBusy(true);
    setNotice(null);
    try {
      setTracking(
        await cancelDeliveryOrder(clientId, tracking.pedido_id, cancelReason.trim()),
      );
      setCancelReason("");
      setError(null);
      setNotice("Cancelamento reconciliado entre pedido, financeiro, estoque e logística.");
    } catch (caught) {
      setError(errorMessage(caught, "Não foi possível cancelar o pedido Delivery."));
    } finally {
      setActionBusy(false);
    }
  }

  const activeProducts = useMemo(
    () => context?.catalogo.filter((product) => product.ativo) ?? [],
    [context],
  );

  if (auth.status === "authenticated" && !allowed) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-100 p-6">
        <div className="max-w-md rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
          <ShieldAlert className="size-9 text-amber-500" />
          <h1 className="mt-4 text-xl font-black text-slate-950">Delivery não liberado</h1>
          <p className="mt-2 text-sm leading-6 text-slate-500">
            Sua sessão não possui as permissões necessárias para visualizar clientes e pedidos.
          </p>
          <Button asChild className="mt-6 w-full">
            <Link href="/">Voltar ao Dashboard</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-100 p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1600px] space-y-5">
        <header className="flex flex-col gap-4 rounded-3xl bg-slate-950 p-6 text-white shadow-xl shadow-slate-950/10 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-600">
              <Bike className="size-6" />
            </div>
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-blue-300">
                Canal próprio
              </p>
              <h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">
                Delivery Próprio
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                Cliente, endereço validado, cardápio, checkout e logística no mesmo fluxo.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="border-slate-700 bg-slate-900 text-white hover:bg-slate-800 hover:text-white"
              onClick={() => void loadClients()}
              disabled={loading}
            >
              <RefreshCw className="size-4" /> Atualizar
            </Button>
            <Button asChild variant="outline" className="border-slate-700 bg-slate-900 text-white hover:bg-slate-800 hover:text-white">
              <Link href="/"><ArrowLeft className="size-4" /> Dashboard</Link>
            </Button>
          </div>
        </header>

        {error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
            {notice}
          </div>
        ) : null}

        <section className="grid gap-5 xl:grid-cols-[0.95fr_1.35fr]">
          <div className="space-y-5">
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600">Cliente e endereço</p>
              <label className="mt-4 block text-sm font-bold text-slate-700" htmlFor="delivery-client">
                Cliente CRM
              </label>
              <select
                id="delivery-client"
                value={clientId}
                onChange={(event) => void selectClient(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-blue-500"
              >
                <option value="">Selecione um cliente</option>
                {clients.map((client) => (
                  <option key={client.cliente_id} value={client.cliente_id}>
                    {client.cliente_id}
                  </option>
                ))}
              </select>

              {context ? (
                <div className="mt-4 rounded-2xl bg-slate-50 p-4">
                  <div className="flex items-start gap-3">
                    <MapPin className="mt-0.5 size-5 text-blue-600" />
                    <div>
                      <p className="text-sm font-bold text-slate-950">Endereço validado</p>
                      <p className="mt-1 text-sm text-slate-600">{context.endereco.endereco_formatado}</p>
                      <p className="mt-1 text-xs text-slate-500">CEP {context.endereco.cep}</p>
                    </div>
                  </div>
                </div>
              ) : null}

              <Button
                className="mt-4 w-full"
                onClick={() => void startCart()}
                disabled={!context || !canCreate || actionBusy}
              >
                <ShoppingBag className="size-4" /> Iniciar novo pedido
              </Button>
            </div>

            {cart ? (
              <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600">Carrinho</p>
                    <p className="mt-1 text-sm text-slate-500">versão {cart.versao}</p>
                  </div>
                  <Badge variant="outline">{humanize(cart.status)}</Badge>
                </div>
                <div className="mt-4 space-y-2">
                  {cart.itens.length ? cart.itens.map((item) => (
                    <div key={`${item.produto_id}-${item.produto_versao}`} className="flex justify-between gap-3 rounded-xl bg-slate-50 p-3 text-sm">
                      <span><strong>{item.quantidade}×</strong> {item.nome}</span>
                      <strong>{money(item.subtotal)}</strong>
                    </div>
                  )) : <p className="text-sm text-slate-500">Nenhum item adicionado.</p>}
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
                  <div className="rounded-xl bg-slate-50 p-3"><span className="text-slate-500">Subtotal</span><p className="font-black">{money(cart.subtotal)}</p></div>
                  <div className="rounded-xl bg-slate-50 p-3"><span className="text-slate-500">Entrega</span><p className="font-black">{money(cart.taxa_entrega)}</p></div>
                </div>
                {cart.cotacao ? (
                  <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-800">
                    {cart.cotacao.nome_area} · {money(cart.cotacao.taxa)} · SLA {cart.cotacao.sla_minutos}–{cart.cotacao.sla_maxutos} min
                  </div>
                ) : null}
                <p className="mt-4 text-right text-xl font-black text-slate-950">{money(cart.total)}</p>
                <Button
                  variant="outline"
                  className="mt-4 w-full"
                  onClick={() => void calculateQuote()}
                  disabled={!cart.itens.length || actionBusy}
                >
                  <Truck className="size-4" /> Calcular taxa e SLA
                </Button>
                <label className="mt-4 block text-sm font-bold text-slate-700" htmlFor="delivery-payment">Forma de pagamento</label>
                <select
                  id="delivery-payment"
                  value={paymentMethod}
                  onChange={(event) => setPaymentMethod(event.target.value)}
                  className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm"
                >
                  {PAYMENT_OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                </select>
                <Button
                  className="mt-4 w-full"
                  onClick={() => void confirmOrder()}
                  disabled={!cart.cotacao || !cart.itens.length || !canConfirm || actionBusy || Boolean(tracking)}
                >
                  Confirmar pedido
                </Button>
              </div>
            ) : null}
          </div>

          <div className="space-y-5">
            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center gap-3">
                <PackagePlus className="size-5 text-blue-600" />
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600">Cardápio da unidade</p>
                  <p className="mt-1 text-sm text-slate-500">Produtos autorizados para o contexto selecionado.</p>
                </div>
              </div>
              {!context ? (
                <p className="mt-5 text-sm text-slate-500">Selecione um cliente para resolver o cardápio e a política de entrega.</p>
              ) : activeProducts.length === 0 ? (
                <p className="mt-5 text-sm text-slate-500">Nenhum produto disponível neste escopo.</p>
              ) : (
                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {activeProducts.map((product) => (
                    <div key={product.produto_id} className="rounded-2xl border border-slate-200 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div><p className="font-bold text-slate-950">{product.nome}</p><p className="mt-1 text-xs text-slate-500">Estoque {product.estoque_disponivel}</p></div>
                        <strong>{money(product.preco)}</strong>
                      </div>
                      <Button
                        variant="outline"
                        className="mt-4 w-full"
                        onClick={() => void addProduct(product.produto_id)}
                        disabled={!cart || actionBusy || !canCreate}
                      >
                        Adicionar
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.16em] text-blue-600">Acompanhamento</p>
                  <h2 className="mt-1 text-lg font-black text-slate-950">Pedido e logística</h2>
                </div>
                {tracking ? (
                  <Button variant="outline" size="sm" onClick={() => void refreshTracking()} disabled={actionBusy}>
                    <RefreshCw className="size-4" /> Atualizar
                  </Button>
                ) : null}
              </div>
              {!tracking ? (
                <p className="mt-5 text-sm text-slate-500">O acompanhamento aparecerá após a confirmação do pedido.</p>
              ) : (
                <div className="mt-5 space-y-4">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Pedido</p><Badge variant="outline" className={`mt-2 ${statusClass(tracking.status_pedido)}`}>{humanize(tracking.status_pedido)}</Badge></div>
                    <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Entrega</p><Badge variant="outline" className={`mt-2 ${statusClass(tracking.status_entrega)}`}>{humanize(tracking.status_entrega)}</Badge></div>
                    <div className="rounded-2xl bg-slate-50 p-4"><p className="text-xs text-slate-500">Total canônico</p><p className="mt-2 font-black">{money(tracking.total)}</p></div>
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-950">Timeline logística</p>
                    <div className="mt-2 space-y-2">
                      {tracking.eventos.length ? tracking.eventos.map((event, index) => (
                        <div key={`${event.tipo}-${event.ocorrido_em}-${index}`} className="rounded-xl border border-slate-200 px-3 py-2 text-sm">
                          <strong>{humanize(event.tipo)}</strong><span className="ml-2 text-slate-500">{humanize(event.status_entrega)}</span>
                        </div>
                      )) : <p className="text-sm text-slate-500">Sem novos eventos.</p>}
                    </div>
                  </div>
                  {canCancel && tracking.status_pedido !== "cancelado" && tracking.status_entrega !== "entregue" ? (
                    <div className="rounded-2xl border border-red-200 bg-red-50 p-4">
                      <p className="text-sm font-bold text-red-800">Cancelar pedido</p>
                      <Input className="mt-3 bg-white" placeholder="Informe o motivo" value={cancelReason} onChange={(event) => setCancelReason(event.target.value)} />
                      <Button variant="destructive" className="mt-3 w-full" disabled={!cancelReason.trim() || actionBusy} onClick={() => void cancelOrder()}>
                        Cancelar no fluxo canônico
                      </Button>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
