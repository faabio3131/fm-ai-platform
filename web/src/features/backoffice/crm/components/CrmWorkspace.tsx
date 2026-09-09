"use client";

import {
  ArrowDownCircle,
  ArrowUpCircle,
  BadgeDollarSign,
  LoaderCircle,
  RefreshCw,
  Search,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  consultarCashback,
  creditarCashback,
  CrmApiError,
  listarClientesCrm,
  type CashbackDetalhe,
  type CrmCliente,
} from "@/features/backoffice/crm/services/crm-api";

function moeda(valor: string | number | null): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(valor ?? 0));
}

function dataHora(valor: string | null): string {
  if (!valor) return "Não registrada";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(valor));
}

function mensagemErro(error: unknown): string {
  if (error instanceof CrmApiError) {
    if (error.status === 401) return "Sua sessão não está mais válida.";
    if (error.status === 403) return "Seu perfil não pode acessar o CRM desta unidade.";
    if (error.code === "cliente_legado_sem_mapping_crm") {
      return "Este cliente ainda não possui vínculo governado com o cadastro legado.";
    }
  }
  return "Não foi possível concluir a operação no CRM.";
}

export function CrmWorkspace() {
  const auth = useAuthStore();
  const [clientes, setClientes] = useState<CrmCliente[]>([]);
  const [saldoTotal, setSaldoTotal] = useState("0.00");
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<CashbackDetalhe | null>(null);
  const [busca, setBusca] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregarDetalhe = useCallback(async (clienteId: string) => {
    setErro(null);
    try {
      setDetalhe(await consultarCashback(clienteId));
    } catch (error) {
      setDetalhe(null);
      setErro(mensagemErro(error));
    }
  }, []);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const resumo = await listarClientesCrm();
      setClientes(resumo.itens);
      setSaldoTotal(resumo.saldo_total);
      const proximoSelecionado = resumo.itens[0]?.cliente_id ?? null;
      setSelecionado(proximoSelecionado);
      if (proximoSelecionado) await carregarDetalhe(proximoSelecionado);
      else setDetalhe(null);
    } catch (error) {
      setClientes([]);
      setDetalhe(null);
      setErro(mensagemErro(error));
    } finally {
      setLoading(false);
    }
  }, [carregarDetalhe]);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId) return;
    const timeoutId = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timeoutId);
  }, [auth.status, auth.unitId, carregar]);

  const clienteSelecionado = clientes.find(
    (cliente) => cliente.cliente_id === selecionado,
  );
  const filtrados = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase("pt-BR");
    if (!termo) return clientes;
    return clientes.filter((cliente) =>
      [cliente.nome, cliente.whatsapp, cliente.cliente_id, cliente.status]
        .filter(Boolean)
        .some((valor) => String(valor).toLocaleLowerCase("pt-BR").includes(termo)),
    );
  }, [busca, clientes]);

  async function selecionar(clienteId: string) {
    setSelecionado(clienteId);
    setDetalhe(null);
    await carregarDetalhe(clienteId);
  }

  async function creditar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!clienteSelecionado || clienteSelecionado.legacy_cliente_id === null || busy) return;
    const form = new FormData(event.currentTarget);
    const valor = String(form.get("valor") || "");
    setBusy(true);
    setErro(null);
    setAviso(null);
    try {
      const resultado = await creditarCashback(
        clienteSelecionado.cliente_id,
        valor,
        `crm-web-${clienteSelecionado.cliente_id}-${crypto.randomUUID()}`,
      );
      setAviso(`Crédito registrado. Novo saldo: ${moeda(resultado.saldo)}.`);
      event.currentTarget.reset();
      await carregar();
    } catch (error) {
      setErro(mensagemErro(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 p-4 text-slate-100 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-[1500px] space-y-6">
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-300">
              Retaguarda · Unidade ativa
            </p>
            <h1 className="mt-2 text-3xl font-black tracking-tight">CRM, Clientes e Cashback</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-400">
              Clientes escopados, histórico e saldo produzidos pelas autoridades canônicas do CRM.
            </p>
          </div>
          <Button variant="outline" onClick={() => void carregar()} disabled={loading || busy}>
            <RefreshCw className={loading ? "animate-spin" : ""} />
            Atualizar
          </Button>
        </header>

        <section className="grid gap-3 md:grid-cols-3">
          <Metric label="Clientes no escopo" value={String(clientes.length)} />
          <Metric label="Saldo total de cashback" value={moeda(saldoTotal)} />
          <Metric
            label="Vínculos regularizados"
            value={String(clientes.filter((cliente) => cliente.legacy_cliente_id !== null).length)}
          />
        </section>

        {erro ? <Feedback tone="error">{erro}</Feedback> : null}
        {aviso ? <Feedback tone="success">{aviso}</Feedback> : null}

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,1fr)]">
          <div className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
            <div className="flex flex-col gap-3 border-b border-slate-800 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2">
                <Users className="size-5 text-blue-400" />
                <h2 className="font-bold">Clientes da unidade</h2>
              </div>
              <label className="relative block sm:w-72">
                <Search className="pointer-events-none absolute left-3 top-2.5 size-4 text-slate-500" />
                <Input
                  aria-label="Buscar cliente"
                  value={busca}
                  onChange={(event) => setBusca(event.target.value)}
                  placeholder="Nome, WhatsApp ou ID"
                  className="border-slate-700 bg-slate-950 pl-9 text-white"
                />
              </label>
            </div>

            {loading ? (
              <div className="flex min-h-72 items-center justify-center gap-2 text-sm text-slate-400">
                <LoaderCircle className="size-5 animate-spin" /> Carregando CRM…
              </div>
            ) : filtrados.length === 0 ? (
              <div className="flex min-h-72 items-center justify-center px-6 text-center text-sm text-slate-400">
                Nenhum cliente CRM encontrado nesta unidade.
              </div>
            ) : (
              <div className="divide-y divide-slate-800">
                {filtrados.map((cliente) => (
                  <button
                    key={cliente.cliente_id}
                    type="button"
                    onClick={() => void selecionar(cliente.cliente_id)}
                    className={`grid w-full gap-2 p-4 text-left transition-colors sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-center ${
                      cliente.cliente_id === selecionado
                        ? "bg-blue-500/10"
                        : "hover:bg-slate-800/60"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="truncate font-semibold text-white">
                        {cliente.nome || cliente.cliente_id}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        {cliente.whatsapp || cliente.canais.join(", ")} · {cliente.origem}
                      </p>
                    </div>
                    <div className="text-xs text-slate-400">
                      <p>{cliente.status || "Cadastro CRM"}</p>
                      <p>Última compra: {dataHora(cliente.ultima_compra)}</p>
                    </div>
                    <p className="font-black tabular-nums text-emerald-300">
                      {moeda(cliente.saldo_cashback)}
                    </p>
                  </button>
                ))}
              </div>
            )}
          </div>

          <aside className="space-y-6">
            <section className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
              <div className="flex items-center gap-2">
                <BadgeDollarSign className="size-5 text-emerald-400" />
                <h2 className="font-bold">Fidelidade e cashback</h2>
              </div>
              {!clienteSelecionado ? (
                <p className="mt-5 text-sm text-slate-400">Selecione um cliente para consultar o ledger.</p>
              ) : (
                <>
                  <p className="mt-5 text-sm text-slate-400">
                    {clienteSelecionado.nome || clienteSelecionado.cliente_id}
                  </p>
                  <p className="mt-1 text-3xl font-black tabular-nums text-white">
                    {moeda(detalhe?.saldo ?? clienteSelecionado.saldo_cashback)}
                  </p>

                  {clienteSelecionado.legacy_cliente_id === null ? (
                    <p className="mt-5 rounded-xl border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-200">
                      Crédito manual indisponível até existir vínculo governado com o cadastro legado.
                    </p>
                  ) : (
                    <form onSubmit={(event) => void creditar(event)} className="mt-5 space-y-3">
                      <label className="block text-xs font-semibold text-slate-400">
                        Valor do crédito (R$)
                        <Input
                          name="valor"
                          type="number"
                          min="0.01"
                          step="0.01"
                          defaultValue="10.00"
                          required
                          className="mt-1 border-slate-700 bg-slate-950 text-white"
                        />
                      </label>
                      <Button type="submit" disabled={busy} className="w-full">
                        {busy ? <LoaderCircle className="animate-spin" /> : <BadgeDollarSign />}
                        Confirmar crédito de cashback
                      </Button>
                    </form>
                  )}
                </>
              )}
            </section>

            <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60">
              <div className="border-b border-slate-800 px-5 py-4">
                <h2 className="font-bold">Histórico do ledger</h2>
              </div>
              {!detalhe ? (
                <p className="p-5 text-sm text-slate-400">Selecione um cliente para ver os movimentos.</p>
              ) : detalhe.movimentos.length === 0 ? (
                <p className="p-5 text-sm text-slate-400">Nenhum movimento de cashback registrado.</p>
              ) : (
                <div className="max-h-[420px] divide-y divide-slate-800 overflow-y-auto">
                  {[...detalhe.movimentos].reverse().map((movimento) => {
                    const credito = movimento.tipo === "credito";
                    const Icon = credito ? ArrowUpCircle : ArrowDownCircle;
                    return (
                      <div key={movimento.movimento_id} className="flex gap-3 p-4">
                        <Icon className={`mt-0.5 size-5 shrink-0 ${credito ? "text-emerald-400" : "text-amber-400"}`} />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-start justify-between gap-3">
                            <p className="truncate text-sm font-semibold text-white">{movimento.origem}</p>
                            <p className={`text-sm font-bold tabular-nums ${credito ? "text-emerald-300" : "text-amber-300"}`}>
                              {credito ? "+" : "−"}{moeda(movimento.valor)}
                            </p>
                          </div>
                          <p className="mt-1 truncate text-xs text-slate-500">{movimento.referencia}</p>
                          <p className="mt-1 text-xs text-slate-500">{dataHora(movimento.ocorrido_em)}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          </aside>
        </section>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4">
      <p className="text-xs font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-2 text-2xl font-black tabular-nums text-white">{value}</p>
    </div>
  );
}

function Feedback({
  tone,
  children,
}: {
  tone: "error" | "success";
  children: string;
}) {
  return (
    <div
      role="status"
      className={`rounded-xl border px-4 py-3 text-sm ${
        tone === "error"
          ? "border-red-500/30 bg-red-500/10 text-red-200"
          : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
      }`}
    >
      {children}
    </div>
  );
}
