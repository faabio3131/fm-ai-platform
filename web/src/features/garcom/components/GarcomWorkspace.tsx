"use client";

import {
  ArrowLeft,
  CheckCircle2,
  ChefHat,
  CreditCard,
  ReceiptText,
  RefreshCw,
  ShieldAlert,
  Utensils,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  fetchComandaDetails,
  fetchProdutosSalao,
  launchOrder,
  type SalaoComandaDetails,
  type SalaoProduto,
} from "@/features/salao/services/salao-api";
import {
  abrirComandaGarcom,
  aplicarPagamentoGarcom,
  confirmarPagamentoGarcom,
  consolidarComponentes,
  criarPagamentoGarcom,
  definirDestino,
  definirDivisao,
  fecharComandaGarcom,
  fetchConfiguracaoFechamento,
  fetchDemonstrativo,
  fetchGarcomPainel,
  GarcomApiError,
  retomarConsumoGarcom,
  solicitarContaGarcom,
  type ConfiguracaoFechamento,
  type DemonstrativoFechamento,
  type GarcomComanda,
  type GarcomMesa,
  type GarcomPainel,
  type MetodoFechamento,
  type ParcelaFechamento,
} from "@/features/garcom/services/garcom-api";

const GARCOM_PERMISSION = "comanda.alterar";
const RECEBIMENTO_PERMISSIONS = [
  "pagamento.registrar",
  "pagamento.confirmar",
  "comanda.fechar",
] as const;
const EMPTY: GarcomPainel = {
  papel: "",
  kds_degradado: false,
  atualizado_em: "",
  mesas: [],
  comandas: [],
  alertas_prontos: [],
};

function errorText(caught: unknown, fallback: string): string {
  if (caught instanceof GarcomApiError) {
    return caught.code ? `${caught.message} · ${caught.code}` : caught.message;
  }
  return caught instanceof Error ? caught.message : fallback;
}

function brl(value: string | number): string {
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
    : "R$ —";
}

interface SplitDraft {
  id: string;
  metodo: Extract<
    MetodoFechamento,
    "dinheiro" | "cartao_credito" | "cartao_debito"
  >;
  valor: string;
}

export function GarcomWorkspace() {
  const auth = useAuthStore();
  const allowed = auth.permissions.includes(GARCOM_PERMISSION);
  const canReceiveAtTable = RECEBIMENTO_PERMISSIONS.every((permission) =>
    auth.permissions.includes(permission),
  );
  const [panel, setPanel] = useState<GarcomPainel>(EMPTY);
  const [config, setConfig] = useState<ConfiguracaoFechamento | null>(null);
  const [products, setProducts] = useState<SalaoProduto[]>([]);
  const [selectedMesa, setSelectedMesa] = useState<GarcomMesa | null>(null);
  const [selectedComanda, setSelectedComanda] = useState<GarcomComanda | null>(null);
  const [details, setDetails] = useState<SalaoComandaDetails | null>(null);
  const [preview, setPreview] = useState<DemonstrativoFechamento | null>(null);
  const [includeService, setIncludeService] = useState(true);
  const [splits, setSplits] = useState<SplitDraft[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function reload(): Promise<GarcomPainel> {
    const next = await fetchGarcomPainel();
    setPanel(next);
    if (selectedMesa) {
      const nextComanda =
        next.comandas.find((item) => item.mesa_id === selectedMesa.id) ?? null;
      setSelectedComanda(nextComanda);
    }
    return next;
  }

  async function loadDetails(comanda: GarcomComanda | null) {
    setSelectedComanda(comanda);
    setDetails(null);
    setPreview(null);
    setSplits([]);
    if (!comanda) return;
    const nextDetails = await fetchComandaDetails(comanda.id);
    setDetails(nextDetails);
    if (comanda.status === "CONTA_SOLICITADA") {
      const nextPreview = await fetchDemonstrativo(comanda.id, includeService);
      setPreview(nextPreview);
      setSplits([
        {
          id: crypto.randomUUID(),
          metodo: "dinheiro",
          valor: nextPreview.total,
        },
      ]);
    }
  }

  useEffect(() => {
    if (auth.status !== "authenticated" || !allowed || !auth.unitId) return;
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError(null);
      void Promise.all([
        fetchGarcomPainel(),
        fetchConfiguracaoFechamento(),
        fetchProdutosSalao(),
      ])
        .then(([nextPanel, nextConfig, nextProducts]) => {
          if (cancelled) return;
          setPanel(nextPanel);
          setConfig(nextConfig);
          setProducts(nextProducts);
        })
        .catch((caught: unknown) => {
          if (!cancelled) {
            setError(errorText(caught, "Falha ao abrir o atendimento do garçom."));
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [auth.status, auth.unitId, allowed]);

  const tableComanda = useMemo(() => {
    const byTable = new Map<string, GarcomComanda>();
    for (const comanda of panel.comandas) {
      if (comanda.mesa_id) byTable.set(comanda.mesa_id, comanda);
    }
    return byTable;
  }, [panel.comandas]);

  async function selectTable(mesa: GarcomMesa) {
    setSelectedMesa(mesa);
    setError(null);
    setNotice(null);
    await loadDetails(tableComanda.get(mesa.id) ?? null).catch((caught) =>
      setError(errorText(caught, "Falha ao carregar a comanda.")),
    );
  }

  async function openSelected() {
    if (!selectedMesa) return;
    setBusy(true);
    setError(null);
    try {
      const result = await abrirComandaGarcom(
        selectedMesa.id,
        selectedMesa.versao,
      );
      await reload();
      await loadDetails(result.comanda);
      setNotice("Comanda aberta. Os próximos pedidos continuarão nesta mesma visita.");
    } catch (caught) {
      setError(errorText(caught, "Falha ao abrir a comanda."));
    } finally {
      setBusy(false);
    }
  }

  async function addProduct(product: SalaoProduto) {
    if (!selectedComanda) return;
    setBusy(true);
    setError(null);
    try {
      await launchOrder(selectedComanda.id, {
        itens: [{ produto_id: product.id, quantidade: 1 }],
      });
      const [nextPanel, nextDetails] = await Promise.all([
        reload(),
        fetchComandaDetails(selectedComanda.id),
      ]);
      setDetails(nextDetails);
      setSelectedComanda(
        nextPanel.comandas.find((item) => item.id === selectedComanda.id) ??
          selectedComanda,
      );
      setNotice("Pedido lançado na mesma comanda e encaminhado ao fluxo canônico.");
    } catch (caught) {
      setError(errorText(caught, "Falha ao lançar pedido."));
    } finally {
      setBusy(false);
    }
  }

  async function requestBill() {
    if (!selectedComanda) return;
    setBusy(true);
    setError(null);
    try {
      const result = await solicitarContaGarcom(
        selectedComanda.id,
        selectedComanda.versao,
      );
      const nextPanel = await reload();
      const next = nextPanel.comandas.find((item) => item.id === result.comanda.id) ??
        result.comanda;
      await loadDetails(next);
      setNotice("Conta solicitada. O consumo pode ser retomado antes da consolidação.");
    } catch (caught) {
      setError(errorText(caught, "Falha ao solicitar conta."));
    } finally {
      setBusy(false);
    }
  }

  async function resumeConsumption() {
    if (!selectedComanda || preview?.consolidado) return;
    setBusy(true);
    setError(null);
    try {
      const result = await retomarConsumoGarcom(
        selectedComanda.id,
        selectedComanda.versao,
      );
      const nextPanel = await reload();
      const next = nextPanel.comandas.find((item) => item.id === result.comanda.id) ??
        result.comanda;
      await loadDetails(next);
      setNotice("Consumo retomado na mesma comanda.");
    } catch (caught) {
      setError(errorText(caught, "Falha ao retomar consumo."));
    } finally {
      setBusy(false);
    }
  }

  async function refreshPreview(nextInclude = includeService) {
    if (!selectedComanda) return;
    try {
      const next = await fetchDemonstrativo(selectedComanda.id, nextInclude);
      setPreview(next);
      if (!next.consolidado) {
        setSplits([
          { id: crypto.randomUUID(), metodo: "dinheiro", valor: next.total },
        ]);
      }
    } catch (caught) {
      setError(errorText(caught, "Falha ao atualizar demonstrativo."));
    }
  }

  async function consolidate() {
    if (!selectedComanda) return;
    setBusy(true);
    setError(null);
    try {
      const next = await consolidarComponentes(
        selectedComanda.id,
        selectedComanda.versao,
        includeService,
      );
      setPreview(next);
      const nextPanel = await reload();
      const refreshed =
        nextPanel.comandas.find((item) => item.id === selectedComanda.id) ??
        selectedComanda;
      setSelectedComanda(refreshed);
      setDetails(await fetchComandaDetails(selectedComanda.id));
      setSplits([
        { id: crypto.randomUUID(), metodo: "dinheiro", valor: next.total },
      ]);
      setNotice("Demonstrativo consolidado com snapshot dos valores aplicados.");
    } catch (caught) {
      setError(errorText(caught, "Falha ao consolidar o fechamento."));
    } finally {
      setBusy(false);
    }
  }

  async function chooseDestination(destino: "mesa" | "caixa") {
    if (!selectedComanda) return;
    setBusy(true);
    setError(null);
    try {
      await definirDestino(
        selectedComanda.id,
        selectedComanda.versao,
        destino,
      );
      await refreshPreview();
      setNotice(
        destino === "caixa"
          ? "A mesma comanda foi direcionada ao Caixa, sem duplicação."
          : "Recebimento na mesa selecionado.",
      );
    } catch (caught) {
      setError(errorText(caught, "Falha ao definir local de recebimento."));
    } finally {
      setBusy(false);
    }
  }

  function updateSplit(
    id: string,
    field: "metodo" | "valor",
    value: string,
  ) {
    setSplits((current) =>
      current.map((split) =>
        split.id === id ? { ...split, [field]: value } : split,
      ),
    );
  }

  async function receiveAndClose() {
    if (!selectedComanda || !details || !preview || !canReceiveAtTable) return;
    const firstOrder = details.pedidos[0];
    if (!firstOrder) {
      setError("A comanda não possui pedido canônico para vincular o pagamento.");
      return;
    }
    const totalSplits = splits.reduce(
      (sum, split) => sum + Number(split.valor || 0),
      0,
    );
    if (Math.abs(totalSplits - Number(preview.total)) > 0.009) {
      setError("A soma dos recebimentos deve ser igual ao total da conta.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const division = await definirDivisao(
        selectedComanda.id,
        selectedComanda.versao,
        splits.map<ParcelaFechamento>((split) => ({
          metodo: split.metodo,
          valor: split.valor,
        })),
      );
      let comanda = division.comanda;

      for (const split of splits) {
        const pagamentoId = crypto.randomUUID();
        const created = await criarPagamentoGarcom(selectedComanda.id, {
          pagamento_id: pagamentoId,
          pedido_id: firstOrder.pedido_id,
          metodo: split.metodo,
          valor: split.valor,
        });
        const confirmed = await confirmarPagamentoGarcom(
          selectedComanda.id,
          pagamentoId,
          {
            metodo: split.metodo,
            valor: split.valor,
            versao_pagamento: created.versao,
            referencia_externa:
              split.metodo === "dinheiro"
                ? null
                : `presencial:${crypto.randomUUID()}`,
          },
        );
        if (confirmed.status !== "pago") {
          throw new Error("A autoridade financeira não confirmou o pagamento.");
        }
        const applied = await aplicarPagamentoGarcom(
          selectedComanda.id,
          pagamentoId,
          {
            metodo: split.metodo,
            valor: split.valor,
            versao: comanda.versao,
          },
        );
        comanda = applied.comanda;
      }

      const closed = await fecharComandaGarcom(
        selectedComanda.id,
        comanda.versao,
      );
      setSelectedComanda(closed.comanda);
      setDetails(null);
      setPreview(null);
      setSplits([]);
      await reload();
      setNotice("Pagamento confirmado, comanda quitada, fechada e mesa liberada.");
    } catch (caught) {
      setError(errorText(caught, "Falha no recebimento autoritativo."));
    } finally {
      setBusy(false);
    }
  }

  if (auth.status === "authenticated" && !allowed) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-950 px-6 text-white">
        <div className="w-full max-w-md rounded-2xl border border-slate-700 bg-slate-900 p-6">
          <ShieldAlert className="size-8 text-amber-400" />
          <h1 className="mt-4 text-xl font-black">Garçom não liberado</h1>
          <p className="mt-2 text-sm text-slate-400">
            A sessão é válida, mas esta identidade não possui comanda.alterar.
          </p>
          <Button asChild className="mt-5 w-full">
            <Link href="/"><ArrowLeft />Dashboard</Link>
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 p-3 text-white sm:p-4">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <Utensils className="size-6 text-blue-400" />
                <h1 className="text-xl font-black sm:text-2xl">Garçom Web</h1>
                <Badge className="bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/15">
                  Sessão única
                </Badge>
              </div>
              <p className="mt-1 text-xs text-slate-400">
                {auth.tenantId ?? "—"} · {auth.unitId ?? "—"} · touch-first
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="border-slate-700 bg-slate-950 text-white"
                onClick={() => void reload().catch((caught) =>
                  setError(errorText(caught, "Falha ao atualizar.")),
                )}
                disabled={loading || busy}
              >
                <RefreshCw className={loading ? "animate-spin" : ""} />
                Atualizar
              </Button>
              <Button asChild variant="ghost">
                <Link href="/"><ArrowLeft />Dashboard</Link>
              </Button>
            </div>
          </div>
          {config ? (
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <Badge variant="outline" className="border-slate-700 text-slate-300">
                Recebimento: {config.modo_recebimento.replace("_", " ")}
              </Badge>
              <Badge variant="outline" className="border-slate-700 text-slate-300">
                Serviço: {config.taxa_servico_percentual}%
              </Badge>
              <Badge variant="outline" className="border-slate-700 text-slate-300">
                Couvert: {config.couvert_ativado ? brl(config.couvert_valor) : "desativado"}
              </Badge>
            </div>
          ) : null}
        </header>

        {error ? (
          <div role="alert" className="rounded-xl border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
            {error}
          </div>
        ) : null}
        {notice ? (
          <div role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
            {notice}
          </div>
        ) : null}

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-3">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="font-black">Mesas e comandas</h2>
              <p className="text-xs text-slate-400">Toque para operar sem novo login.</p>
            </div>
            <Badge variant="outline" className="border-slate-700 text-slate-300">
              {panel.mesas.length} mesas
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
            {panel.mesas.map((mesa) => {
              const comanda = tableComanda.get(mesa.id);
              const active = selectedMesa?.id === mesa.id;
              return (
                <button
                  key={mesa.id}
                  type="button"
                  onClick={() => void selectTable(mesa)}
                  className={`min-h-24 rounded-xl border p-3 text-left transition ${active ? "border-blue-400 bg-blue-500/15" : "border-slate-700 bg-slate-950 active:scale-[0.98]"}`}
                >
                  <p className="text-lg font-black">Mesa {mesa.codigo}</p>
                  <p className="mt-1 text-xs text-slate-400">
                    {comanda ? `${comanda.numero} · ${comanda.status}` : mesa.status}
                  </p>
                  {comanda ? (
                    <p className="mt-2 text-sm font-bold">{brl(comanda.total)}</p>
                  ) : null}
                </button>
              );
            })}
          </div>
        </section>

        {selectedMesa ? (
          <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black">Mesa {selectedMesa.codigo}</h2>
                <p className="text-xs text-slate-400">
                  {selectedComanda ? selectedComanda.numero : "Sem comanda ativa"}
                </p>
              </div>
              {!selectedComanda && selectedMesa.disponivel_para_abertura ? (
                <Button className="h-12" onClick={() => void openSelected()} disabled={busy}>
                  Abrir comanda
                </Button>
              ) : null}
            </div>

            {selectedComanda && details ? (
              <div className="mt-4 space-y-4">
                <div className="grid gap-2 sm:grid-cols-3">
                  <div className="rounded-xl bg-slate-950 p-3">
                    <p className="text-xs text-slate-500">Consumo atual</p>
                    <p className="text-xl font-black">{brl(details.total)}</p>
                  </div>
                  <div className="rounded-xl bg-slate-950 p-3">
                    <p className="text-xs text-slate-500">Saldo</p>
                    <p className="text-xl font-black">{brl(details.saldo)}</p>
                  </div>
                  <div className="rounded-xl bg-slate-950 p-3">
                    <p className="text-xs text-slate-500">Pedidos</p>
                    <p className="text-xl font-black">{details.pedidos.length}</p>
                  </div>
                </div>

                {selectedComanda.status === "EM_CONSUMO" || selectedComanda.status === "ABERTA" ? (
                  <>
                    <div>
                      <h3 className="mb-2 font-bold">Adicionar pedido</h3>
                      <div className="grid max-h-60 grid-cols-1 gap-2 overflow-y-auto sm:grid-cols-2">
                        {products.filter((item) => item.disponivel).map((product) => (
                          <Button
                            key={product.id}
                            type="button"
                            variant="outline"
                            className="h-auto min-h-14 justify-between border-slate-700 bg-slate-950 px-3 py-2 text-left text-white"
                            disabled={busy}
                            onClick={() => void addProduct(product)}
                          >
                            <span className="truncate">{product.nome}</span>
                            <span>{brl(product.preco)}</span>
                          </Button>
                        ))}
                      </div>
                    </div>
                    <Button className="h-12 w-full" onClick={() => void requestBill()} disabled={busy}>
                      <ReceiptText />Solicitar conta
                    </Button>
                  </>
                ) : null}

                {selectedComanda.status === "CONTA_SOLICITADA" && preview ? (
                  <div className="space-y-4 rounded-xl border border-slate-700 bg-slate-950 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <h3 className="font-black">Demonstrativo / pré-conta</h3>
                      {!preview.consolidado ? (
                        <Button variant="outline" className="border-slate-700 text-white" onClick={() => void resumeConsumption()} disabled={busy}>
                          Retomar consumo
                        </Button>
                      ) : null}
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between"><span>Consumo</span><strong>{brl(preview.consumo)}</strong></div>
                      <div className="flex justify-between"><span>Couvert artístico</span><strong>{brl(preview.couvert_artistico)}</strong></div>
                      <div className="flex justify-between"><span>Taxa de serviço ({preview.taxa_servico_percentual}%)</span><strong>{brl(preview.taxa_servico_valor)}</strong></div>
                      <div className="flex justify-between"><span>Desconto</span><strong>{brl(preview.desconto)}</strong></div>
                      <div className="border-t border-slate-700 pt-2 flex justify-between text-base"><span>Total</span><strong>{brl(preview.total)}</strong></div>
                    </div>

                    {!preview.consolidado ? (
                      <>
                        <label className="flex min-h-12 items-center gap-3 rounded-lg border border-slate-700 px-3">
                          <input
                            type="checkbox"
                            checked={includeService}
                            onChange={(event) => {
                              const next = event.target.checked;
                              setIncludeService(next);
                              void refreshPreview(next);
                            }}
                            className="size-5"
                          />
                          <span>Incluir taxa de serviço (recusa não é desconto)</span>
                        </label>
                        <Button className="h-12 w-full" onClick={() => void consolidate()} disabled={busy}>
                          Consolidar demonstrativo
                        </Button>
                      </>
                    ) : (
                      <>
                        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs text-emerald-200">
                          Snapshot aplicado. Alterações futuras da configuração não mudam esta conta.
                        </div>
                        {!preview.destino_recebimento ? (
                          <div className="grid gap-2 sm:grid-cols-2">
                            {config?.modo_recebimento !== "no_caixa" ? (
                              <Button className="h-12" onClick={() => void chooseDestination("mesa")} disabled={busy}>
                                Receber na mesa
                              </Button>
                            ) : null}
                            {config?.modo_recebimento !== "na_mesa" ? (
                              <Button variant="outline" className="h-12 border-slate-700 text-white" onClick={() => void chooseDestination("caixa")} disabled={busy}>
                                Enviar ao caixa
                              </Button>
                            ) : null}
                          </div>
                        ) : null}

                        {preview.destino_recebimento === "caixa" ? (
                          <div className="rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-sm text-blue-200">
                            <CreditCard className="mr-2 inline size-4" />
                            Mesma comanda direcionada ao Caixa. Nenhuma comanda nova foi criada.
                          </div>
                        ) : null}

                        {preview.destino_recebimento === "mesa" ? (
                          <div className="space-y-3">
                            {!canReceiveAtTable ? (
                              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
                                Esta identidade pode atender a mesa, mas não possui toda a alçada financeira para confirmar pagamento e fechar a comanda.
                              </div>
                            ) : (
                              <>
                                <h4 className="font-bold">Recebimentos</h4>
                                {splits.map((split, index) => (
                                  <div key={split.id} className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
                                    <select
                                      value={split.metodo}
                                      onChange={(event) => updateSplit(split.id, "metodo", event.target.value)}
                                      className="h-12 rounded-md border border-slate-700 bg-slate-900 px-3"
                                      aria-label={`Método ${index + 1}`}
                                    >
                                      <option value="dinheiro">Dinheiro</option>
                                      <option value="cartao_credito">Cartão crédito</option>
                                      <option value="cartao_debito">Cartão débito</option>
                                    </select>
                                    <Input
                                      type="number"
                                      step="0.01"
                                      min="0.01"
                                      value={split.valor}
                                      onChange={(event) => updateSplit(split.id, "valor", event.target.value)}
                                      className="h-12 border-slate-700 bg-slate-900 text-white"
                                    />
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      disabled={splits.length === 1}
                                      onClick={() => setSplits((current) => current.filter((item) => item.id !== split.id))}
                                    >
                                      Remover
                                    </Button>
                                  </div>
                                ))}
                                <Button
                                  type="button"
                                  variant="outline"
                                  className="border-slate-700 text-white"
                                  onClick={() => setSplits((current) => [
                                    ...current,
                                    { id: crypto.randomUUID(), metodo: "dinheiro", valor: "0.00" },
                                  ])}
                                >
                                  Adicionar método
                                </Button>
                                <Button className="h-12 w-full" onClick={() => void receiveAndClose()} disabled={busy}>
                                  <CheckCircle2 />Confirmar recebimentos e fechar
                                </Button>
                              </>
                            )}
                          </div>
                        ) : null}
                      </>
                    )}
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        ) : null}

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex items-center gap-2">
            <ChefHat className="size-5 text-amber-300" />
            <h2 className="font-black">Prontos para retirada</h2>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {panel.alertas_prontos.length === 0 ? (
              <p className="text-sm text-slate-400">Nenhum item pronto para suas comandas.</p>
            ) : panel.alertas_prontos.map((alert) => (
              <div key={alert.producao_id} className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3">
                <p className="font-bold">Mesa {alert.mesa_codigo ?? "—"} · {alert.comanda_numero}</p>
                <p className="text-xs text-amber-100/70">{alert.setor_nome} · pedido {alert.pedido_id}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}
