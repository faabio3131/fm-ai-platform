"use client";

import { FormEvent, useRef, useState } from "react";
import {
  ArrowLeft,
  LayoutGrid,
  LogOut,
  RefreshCw,
  ShieldCheck,
  UsersRound,
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FloorMap } from "@/features/salao/components/FloorMap";
import { TableDetailModal } from "@/features/salao/components/TableDetailModal";
import {
  clearSalaoSession,
  configureSalaoSession,
  fetchComandaDetails,
  fetchFloorMap,
  fetchProdutosSalao,
  launchOrder,
  openComanda,
  requestBill,
  SalaoApiError,
  type LancamentoPedidoPayload,
  type OpenComandaPayload,
  type SalaoComandaDetails,
  type SalaoComandaMapa,
  type SalaoFloorMap,
  type SalaoMesa,
  type SalaoProduto,
} from "@/features/salao/services/salao-api";

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof SalaoApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

const EMPTY_MAP: SalaoFloorMap = { mesas: [], comandas: [] };

export function SalaoWorkspace() {
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [mutationBusy, setMutationBusy] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [productsLoading, setProductsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [floorMap, setFloorMap] = useState<SalaoFloorMap>(EMPTY_MAP);
  const [produtos, setProdutos] = useState<SalaoProduto[]>([]);
  const [selectedMesa, setSelectedMesa] = useState<SalaoMesa | null>(null);
  const [selectedComanda, setSelectedComanda] =
    useState<SalaoComandaMapa | null>(null);
  const [details, setDetails] = useState<SalaoComandaDetails | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const openKeyRef = useRef<string | null>(null);
  const orderKeyRef = useRef<string | null>(null);
  const billKeyRef = useRef<string | null>(null);

  async function refreshMap(silent = false): Promise<SalaoFloorMap> {
    if (!silent) setRefreshing(true);
    try {
      const nextMap = await fetchFloorMap();
      setFloorMap(nextMap);
      if (!silent) setError(null);
      return nextMap;
    } catch (caught) {
      setError(errorMessage(caught, "Falha ao atualizar o mapa de Salão."));
      throw caught;
    } finally {
      if (!silent) setRefreshing(false);
    }
  }

  async function refreshProducts(): Promise<SalaoProduto[]> {
    setProductsLoading(true);
    try {
      const nextProducts = await fetchProdutosSalao();
      setProdutos(nextProducts);
      return nextProducts;
    } catch (caught) {
      setError(errorMessage(caught, "Falha ao carregar o cardápio operacional."));
      throw caught;
    } finally {
      setProductsLoading(false);
    }
  }

  async function connect(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      configureSalaoSession({ email, password, tenantId, unitId });
      const [nextMap, nextProducts] = await Promise.all([
        fetchFloorMap(),
        fetchProdutosSalao(),
      ]);
      setFloorMap(nextMap);
      setProdutos(nextProducts);
      setConnected(true);
      setPassword("");
    } catch (caught) {
      clearSalaoSession();
      setFloorMap(EMPTY_MAP);
      setProdutos([]);
      setError(errorMessage(caught, "Falha ao abrir a sessão operacional do Salão."));
    } finally {
      setLoading(false);
    }
  }

  function disconnect() {
    clearSalaoSession();
    setConnected(false);
    setFloorMap(EMPTY_MAP);
    setProdutos([]);
    setSelectedMesa(null);
    setSelectedComanda(null);
    setDetails(null);
    setModalOpen(false);
    setError(null);
    setPassword("");
    openKeyRef.current = null;
    orderKeyRef.current = null;
    billKeyRef.current = null;
  }

  async function selectTable(mesa: SalaoMesa, comanda: SalaoComandaMapa | null) {
    setSelectedMesa(mesa);
    setSelectedComanda(comanda);
    setDetails(null);
    setModalOpen(true);
    setError(null);
    openKeyRef.current = null;
    orderKeyRef.current = null;
    billKeyRef.current = null;

    if (!comanda) return;

    setDetailLoading(true);
    try {
      const [nextDetails] = await Promise.all([
        fetchComandaDetails(comanda.id),
        produtos.length ? Promise.resolve(produtos) : refreshProducts(),
      ]);
      setDetails(nextDetails);
    } catch (caught) {
      setError(errorMessage(caught, "Falha ao carregar a comanda selecionada."));
      if (caught instanceof SalaoApiError && caught.status === 404) {
        await refreshMap(true).catch(() => undefined);
      }
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleOpenComanda(payload: OpenComandaPayload) {
    setMutationBusy(true);
    setError(null);
    const idempotencyKey = openKeyRef.current ?? crypto.randomUUID();
    openKeyRef.current = idempotencyKey;

    try {
      const result = await openComanda(payload, idempotencyKey);
      openKeyRef.current = null;
      const [nextMap, nextDetails, nextProducts] = await Promise.all([
        fetchFloorMap(),
        fetchComandaDetails(result.comanda.id),
        fetchProdutosSalao(),
      ]);
      setFloorMap(nextMap);
      setDetails(nextDetails);
      setProdutos(nextProducts);
      setSelectedComanda(
        nextMap.comandas.find((item) => item.id === result.comanda.id) ?? null,
      );
    } catch (caught) {
      if (caught instanceof SalaoApiError && caught.status === 409) {
        await refreshMap(true).catch(() => undefined);
        setError(
          "A mesa mudou em outro terminal. O mapa foi atualizado; revise o estado antes de tentar novamente.",
        );
      } else {
        setError(errorMessage(caught, "Falha ao abrir a comanda."));
      }
    } finally {
      setMutationBusy(false);
    }
  }

  async function handleLaunchOrder(payload: LancamentoPedidoPayload) {
    const comandaId = details?.id ?? selectedComanda?.id;
    if (!comandaId) return;

    setMutationBusy(true);
    setError(null);
    const idempotencyKey = orderKeyRef.current ?? crypto.randomUUID();
    orderKeyRef.current = idempotencyKey;

    try {
      await launchOrder(comandaId, payload, idempotencyKey);
      orderKeyRef.current = null;
      const [nextMap, nextDetails, nextProducts] = await Promise.all([
        fetchFloorMap(),
        fetchComandaDetails(comandaId),
        fetchProdutosSalao(),
      ]);
      setFloorMap(nextMap);
      setDetails(nextDetails);
      setProdutos(nextProducts);
      setSelectedComanda(
        nextMap.comandas.find((item) => item.id === comandaId) ?? selectedComanda,
      );
    } catch (caught) {
      if (caught instanceof SalaoApiError && caught.status === 409) {
        await refreshMap(true).catch(() => undefined);
        setError(
          "A comanda mudou em outro terminal ou a tentativa conflitou. O estado foi atualizado antes de uma nova tentativa.",
        );
      } else {
        setError(errorMessage(caught, "Falha ao lançar o pedido na comanda."));
      }
      throw caught;
    } finally {
      setMutationBusy(false);
    }
  }

  async function handleRequestBill() {
    const comandaId = details?.id ?? selectedComanda?.id;
    if (!comandaId) return;

    setMutationBusy(true);
    setError(null);
    const idempotencyKey = billKeyRef.current ?? crypto.randomUUID();
    billKeyRef.current = idempotencyKey;

    try {
      await requestBill(comandaId, idempotencyKey);
      billKeyRef.current = null;
      const [nextMap, nextDetails] = await Promise.all([
        fetchFloorMap(),
        fetchComandaDetails(comandaId),
      ]);
      setFloorMap(nextMap);
      setDetails(nextDetails);
      setSelectedComanda(
        nextMap.comandas.find((item) => item.id === comandaId) ?? selectedComanda,
      );
    } catch (caught) {
      if (caught instanceof SalaoApiError && caught.status === 409) {
        await refreshMap(true).catch(() => undefined);
        setError(
          "A comanda mudou em outro terminal. O mapa foi atualizado antes de uma nova tentativa.",
        );
      } else {
        setError(errorMessage(caught, "Falha ao solicitar o encerramento da conta."));
      }
    } finally {
      setMutationBusy(false);
    }
  }

  function handleModalOpenChange(open: boolean) {
    setModalOpen(open);
    if (!open) {
      setSelectedMesa(null);
      setSelectedComanda(null);
      setDetails(null);
      openKeyRef.current = null;
      orderKeyRef.current = null;
      billKeyRef.current = null;
    }
  }

  if (!connected) {
    return (
      <main className="dark min-h-screen bg-[#0f172a] px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
        <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl items-center justify-center">
          <Card className="w-full max-w-xl border-slate-700 bg-[#1e293b] text-slate-100 shadow-2xl shadow-black/30">
            <CardHeader className="space-y-4 border-b border-slate-700 bg-slate-950 text-white">
              <div className="flex items-center justify-between gap-3">
                <div className="flex size-12 items-center justify-center rounded-2xl bg-[#2563eb] text-white">
                  <LayoutGrid className="size-6" />
                </div>
                <Badge className="border border-white/10 bg-white/10 text-white hover:bg-white/10">
                  Salão Enterprise V1
                </Badge>
              </div>
              <div>
                <CardTitle className="text-2xl text-white">
                  Abrir mapa operacional do Salão
                </CardTitle>
                <CardDescription className="mt-2 text-slate-400">
                  Mesas e comandas canônicas isoladas por tenant e unidade, com mutações protegidas por idempotência.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-6">
              <form className="space-y-4" onSubmit={(event) => void connect(event)}>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="space-y-1.5 text-sm font-medium text-slate-200">
                    Tenant
                    <Input
                      value={tenantId}
                      onChange={(event) => setTenantId(event.target.value)}
                      placeholder="tenant-id"
                      required
                      className="h-12 border-slate-600 bg-slate-950 text-white"
                    />
                  </label>
                  <label className="space-y-1.5 text-sm font-medium text-slate-200">
                    Unidade
                    <Input
                      value={unitId}
                      onChange={(event) => setUnitId(event.target.value)}
                      placeholder="unidade-id"
                      required
                      className="h-12 border-slate-600 bg-slate-950 text-white"
                    />
                  </label>
                </div>
                <label className="block space-y-1.5 text-sm font-medium text-slate-200">
                  Operador do Salão
                  <Input
                    autoComplete="username"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="garcom@empresa.com"
                    required
                    className="h-12 border-slate-600 bg-slate-950 text-white"
                  />
                </label>
                <label className="block space-y-1.5 text-sm font-medium text-slate-200">
                  Senha
                  <Input
                    autoComplete="current-password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                    className="h-12 border-slate-600 bg-slate-950 text-white"
                  />
                </label>

                {error ? (
                  <div className="rounded-xl border border-[#ef4444]/40 bg-[#ef4444]/10 px-4 py-3 text-sm font-semibold text-[#fca5a5]">
                    {error}
                  </div>
                ) : null}

                <Button
                  type="submit"
                  className="h-12 w-full rounded-xl bg-[#2563eb] text-base font-black hover:bg-blue-500"
                  disabled={loading}
                >
                  {loading ? <RefreshCw className="animate-spin" /> : <ShieldCheck />}
                  {loading ? "Validando Salão..." : "Entrar no mapa de Salão"}
                </Button>
                <Button
                  asChild
                  type="button"
                  variant="ghost"
                  className="h-11 w-full text-slate-300 hover:bg-slate-700 hover:text-white"
                >
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

  const freeCount = floorMap.mesas.filter((mesa) => mesa.status === "LIVRE").length;
  const billCount = floorMap.comandas.filter(
    (comanda) => comanda.status_comanda === "CONTA_SOLICITADA",
  ).length;
  const occupiedCount = floorMap.mesas.filter(
    (mesa) => mesa.status === "OCUPADA",
  ).length;

  return (
    <main className="dark min-h-screen bg-[#0f172a] p-3 text-slate-100 sm:p-4 lg:p-5">
      <div className="mx-auto flex min-h-[calc(100vh-2rem)] max-w-[1900px] flex-col gap-4">
        <header className="rounded-2xl border border-slate-700 bg-[#1e293b] p-4 shadow-xl shadow-black/10">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-[#2563eb] text-white">
                <LayoutGrid className="size-6" />
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-black tracking-tight text-white sm:text-2xl">
                    Mapa de Salão
                  </h1>
                  <Badge className="border border-[#10b981]/30 bg-[#10b981]/10 text-[#6ee7b7] hover:bg-[#10b981]/10">
                    Online
                  </Badge>
                </div>
                <p className="mt-1 truncate text-xs text-slate-400">
                  {tenantId} · {unitId} · /v1/salao
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                className="h-11 rounded-xl border-slate-600 bg-slate-900 text-slate-100 hover:bg-slate-700"
                onClick={() => void Promise.all([refreshMap(), refreshProducts()])}
                disabled={refreshing || productsLoading}
              >
                <RefreshCw className={refreshing || productsLoading ? "animate-spin" : ""} />
                <span className="hidden sm:inline">Atualizar</span>
              </Button>
              <Button
                type="button"
                variant="ghost"
                className="h-11 rounded-xl text-slate-300 hover:bg-slate-700 hover:text-white"
                onClick={disconnect}
              >
                <LogOut />
                <span className="hidden sm:inline">Encerrar</span>
              </Button>
            </div>
          </div>

          <div className="mt-4 grid gap-2 sm:grid-cols-3">
            <div className="rounded-xl border border-slate-700 bg-slate-950/45 px-4 py-3">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">Livres</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-slate-100">{freeCount}</p>
            </div>
            <div className="rounded-xl border border-[#2563eb]/30 bg-[#2563eb]/10 px-4 py-3">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-blue-300">Ocupadas</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-white">{occupiedCount}</p>
            </div>
            <div className="rounded-xl border border-[#f59e0b]/30 bg-[#f59e0b]/10 px-4 py-3">
              <p className="text-xs font-bold uppercase tracking-[0.14em] text-amber-300">Contas solicitadas</p>
              <p className="mt-1 text-2xl font-black tabular-nums text-white">{billCount}</p>
            </div>
          </div>
        </header>

        {error ? (
          <div className="rounded-xl border border-[#ef4444]/40 bg-[#ef4444]/10 px-4 py-3 text-sm font-semibold text-[#fca5a5]">
            {error}
          </div>
        ) : null}

        <section className="flex-1 rounded-2xl border border-slate-800 bg-slate-950/35 p-3 sm:p-4">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-black text-white">Mesas da unidade</h2>
              <p className="mt-1 text-xs text-slate-500">
                Toque em uma mesa para abrir a comanda, lançar itens ou consultar o extrato.
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-400">
              <UsersRound className="size-4 text-[#2563eb]" />
              {floorMap.mesas.length} mesa(s)
            </div>
          </div>
          <FloorMap
            floorMap={floorMap}
            selectedTableId={selectedMesa?.id}
            onSelectTable={(mesa, comanda) => void selectTable(mesa, comanda)}
          />
        </section>

        <footer className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-800 bg-slate-950/50 px-4 py-2 text-xs text-slate-500">
          <span>Salão HTTP Foundation · pedidos canônicos · isolamento tenant/unidade</span>
          <Button asChild variant="ghost" size="sm" className="text-slate-400 hover:bg-slate-800 hover:text-white">
            <Link href="/">
              <ArrowLeft />
              Dashboard
            </Link>
          </Button>
        </footer>
      </div>

      <TableDetailModal
        key={selectedMesa?.id ?? "no-table"}
        open={modalOpen}
        mesa={selectedMesa}
        comanda={selectedComanda}
        details={details}
        produtos={produtos}
        loading={detailLoading}
        productsLoading={productsLoading}
        busy={mutationBusy}
        onOpenChange={handleModalOpenChange}
        onOpenComanda={handleOpenComanda}
        onLaunchOrder={handleLaunchOrder}
        onRequestBill={handleRequestBill}
      />
    </main>
  );
}
