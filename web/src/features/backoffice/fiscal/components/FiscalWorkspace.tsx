"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  type FiscalEnvironment,
  type FiscalWorkspaceResponse,
  getFiscalWorkspace,
} from "@/features/backoffice/fiscal/services/fiscal-api";

function EmptyState({ children }: { children: string }) {
  return <p className="py-4 text-sm text-slate-400">{children}</p>;
}

function shortKey(value: string | null): string {
  if (!value) return "—";
  return value.length > 20 ? `${value.slice(0, 10)}…${value.slice(-8)}` : value;
}

export function FiscalWorkspace() {
  const [environment, setEnvironment] =
    useState<FiscalEnvironment>("homologation");
  const [data, setData] = useState<FiscalWorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextEnvironment: FiscalEnvironment) => {
    setLoading(true);
    setError(null);
    try {
      setData(await getFiscalWorkspace(nextEnvironment));
    } catch (caught: unknown) {
      setData(null);
      setError(
        caught instanceof Error
          ? caught.message
          : "Não foi possível carregar a área fiscal.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(environment), 0);
    return () => window.clearTimeout(timer);
  }, [environment, load]);

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-6 text-slate-100">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-300">
            Fiscal V1
          </p>
          <h1 className="mt-2 text-2xl font-semibold">Central Fiscal</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-400">
            Documentos emitidos e recebidos, Fiscal Inbox, manifestações,
            compras, recebimentos, financeiro e configuração governada.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label htmlFor="fiscal-environment" className="text-sm text-slate-300">
            Ambiente
          </label>
          <select
            id="fiscal-environment"
            value={environment}
            onChange={(event) =>
              setEnvironment(event.target.value as FiscalEnvironment)
            }
            className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm"
          >
            <option value="homologation">Homologação</option>
            <option value="production">Produção</option>
          </select>
          <Button asChild variant="outline">
            <Link href="/admin/integracoes">Configuração fiscal</Link>
          </Button>
        </div>
      </header>

      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200"
        >
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-slate-400">Carregando dados fiscais…</p> : null}

      {data ? (
        <>
          <section aria-label="Resumo fiscal" className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Documentos emitidos", data.summary.outbound_documents],
              ["Documentos recebidos", data.summary.inbound_documents],
              ["Manifestações", data.summary.manifestations],
              ["Capturas Smart Intake", data.summary.intake_captures],
              ["Pedidos de compra", data.summary.purchase_orders],
              ["Recebimentos", data.summary.receipts],
              ["Obrigações financeiras", data.summary.financial_obligations],
              ["Itens no archive", data.summary.archive_entries],
              ["Contingência", data.summary.contingency_entries],
              ["Produtos pendentes", data.summary.products_pending_fiscal],
            ].map(([label, value]) => (
              <article
                key={String(label)}
                className="rounded-xl border border-slate-800 bg-slate-900 p-4"
              >
                <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
                <p className="mt-2 text-2xl font-semibold">{value}</p>
              </article>
            ))}
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">Readiness e configuração</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Produção só é habilitada por configuração explícita e evidência
                  governada. Esta tela não exibe segredos.
                </p>
              </div>
              <Button asChild variant="outline">
                <Link href="/admin/integracoes">
                  Gerenciar certificado e provedor
                </Link>
              </Button>
            </div>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <dt className="text-slate-500">Provider</dt>
                <dd>{data.configuration?.provider ?? "Não configurado"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Ambiente configurado</dt>
                <dd>{data.configuration?.environment ?? "Homologação fail-safe"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Habilitada</dt>
                <dd>{data.configuration?.enabled ? "Sim" : "Não"}</dd>
              </div>
              <div>
                <dt className="text-slate-500">Homologação registrada</dt>
                <dd>{data.configuration?.homologated ? "Sim" : "Não"}</dd>
              </div>
            </dl>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="font-semibold">Documentos emitidos</h2>
            {data.outbound.length === 0 ? (
              <EmptyState>Nenhum documento emitido neste ambiente.</EmptyState>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="pb-2">Documento</th>
                      <th className="pb-2">Tipo</th>
                      <th className="pb-2">Estado</th>
                      <th className="pb-2">Chave</th>
                      <th className="pb-2">Protocolo / rejeição</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.outbound.map((item) => (
                      <tr key={item.document_id} className="border-t border-slate-800">
                        <td className="py-3">{item.document_id}</td>
                        <td>{item.document_kind}</td>
                        <td>{item.state}</td>
                        <td>{shortKey(item.access_key)}</td>
                        <td>
                          {item.protocol_reference ??
                            [item.rejection_code, item.rejection_message]
                              .filter(Boolean)
                              .join(" — ") ||
                            "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
            <h2 className="font-semibold">Fiscal Inbox — documentos recebidos</h2>
            {data.inbound.length === 0 ? (
              <EmptyState>Nenhum documento recebido neste ambiente.</EmptyState>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-slate-400">
                    <tr>
                      <th className="pb-2">Emitente</th>
                      <th className="pb-2">Chave</th>
                      <th className="pb-2">NSU</th>
                      <th className="pb-2">Origem</th>
                      <th className="pb-2">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.inbound.map((item) => (
                      <tr key={item.inbound_id} className="border-t border-slate-800">
                        <td className="py-3">{item.issuer_name ?? item.issuer_document ?? "—"}</td>
                        <td>{shortKey(item.access_key)}</td>
                        <td>{item.nsu ?? "—"}</td>
                        <td>{item.source}</td>
                        <td>{item.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="font-semibold">Compras e recebimentos</h2>
              <p className="mt-1 text-sm text-slate-400">
                A NF-e não equivale a recebimento físico nem a pagamento.
              </p>
              <div className="mt-4 space-y-2 text-sm">
                {data.procurement.orders.map((item) => (
                  <div key={item.pedido_id} className="rounded-lg border border-slate-800 p-3">
                    Pedido {item.pedido_id} · fornecedor {item.fornecedor_id} · {item.status}
                  </div>
                ))}
                {data.procurement.receipts.map((item) => (
                  <div
                    key={item.recebimento_id}
                    className="rounded-lg border border-slate-800 p-3"
                  >
                    Recebimento {item.recebimento_id} · pedido {item.pedido_id} · {item.status}
                  </div>
                ))}
                {data.procurement.orders.length === 0 &&
                data.procurement.receipts.length === 0 ? (
                  <EmptyState>Nenhum movimento de procurement neste ambiente.</EmptyState>
                ) : null}
              </div>
            </article>

            <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="font-semibold">Financeiro de compras</h2>
              <p className="mt-1 text-sm text-slate-400">
                Obrigações são separadas de pagamentos e preservam reconciliação.
              </p>
              <div className="mt-4 space-y-2 text-sm">
                {data.financial.map((item) => (
                  <div key={item.obrigacao_id} className="rounded-lg border border-slate-800 p-3">
                    <div>{item.obrigacao_id} · {item.status}</div>
                    <div className="mt-1 text-slate-400">
                      Saldo {item.currency} {item.balance} · {item.reconciliation}
                    </div>
                  </div>
                ))}
                {data.financial.length === 0 ? (
                  <EmptyState>Nenhuma obrigação fiscal de compra neste ambiente.</EmptyState>
                ) : null}
              </div>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="font-semibold">Manifestações</h2>
              <div className="mt-4 space-y-2 text-sm">
                {data.manifestations.map((item) => (
                  <div
                    key={item.manifestation_id}
                    className="rounded-lg border border-slate-800 p-3"
                  >
                    {item.event_type} · {shortKey(item.access_key)}
                    <div className="mt-1 text-slate-400">
                      {item.protocol_reference ?? "Sem protocolo externo"}
                    </div>
                  </div>
                ))}
                {data.manifestations.length === 0 ? (
                  <EmptyState>Nenhuma manifestação registrada.</EmptyState>
                ) : null}
              </div>
            </article>

            <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="font-semibold">Smart Fiscal Intake</h2>
              <div className="mt-4 space-y-2 text-sm">
                {data.intake.map((item) => (
                  <div key={item.capture_id} className="rounded-lg border border-slate-800 p-3">
                    {item.source} · {item.authority} · {item.status}
                    <div className="mt-1 text-slate-400">{item.media_type}</div>
                  </div>
                ))}
                {data.intake.length === 0 ? (
                  <EmptyState>Nenhuma captura fiscal preliminar.</EmptyState>
                ) : null}
              </div>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="font-semibold">Produtos com pendência fiscal</h2>
              {!data.products_pending_fiscal.available ? (
                <EmptyState>
                  O catálogo legado não está mapeado para esta unidade; nenhuma pendência foi inferida.
                </EmptyState>
              ) : data.products_pending_fiscal.items.length === 0 ? (
                <EmptyState>Nenhum produto sem perfil fiscal neste ambiente.</EmptyState>
              ) : (
                <div className="mt-4 space-y-2 text-sm">
                  {data.products_pending_fiscal.items.map((item) => (
                    <div key={item.product_id} className="rounded-lg border border-slate-800 p-3">
                      {item.product_id} · {item.name}
                    </div>
                  ))}
                </div>
              )}
            </article>

            <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h2 className="font-semibold">Contingência e retries</h2>
              {data.contingency.length === 0 ? (
                <EmptyState>Nenhuma entrada pendente no outbox fiscal.</EmptyState>
              ) : (
                <div className="mt-4 space-y-2 text-sm">
                  {data.contingency.map((item) => (
                    <div key={item.entry_id} className="rounded-lg border border-slate-800 p-3">
                      {item.operation} · {item.status} · tentativa {item.attempt_count}
                      {item.last_error ? (
                        <div className="mt-1 text-slate-400">{item.last_error}</div>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </article>
          </section>

          <section className="rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm">
            <h2 className="font-semibold">Operações sensíveis</h2>
            <p className="mt-2 text-slate-400">
              Cancelamento, inutilização, certificado e alterações de ambiente
              permanecem protegidos por RBAC, step-up e gateway governado. Nenhuma
              homologação SEFAZ real é presumida por esta certificação interna.
            </p>
          </section>
        </>
      ) : null}
    </main>
  );
}
