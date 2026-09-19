"use client";

import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  obterPagamento,
  reconciliarPagBank,
  type PagamentoWeb,
} from "@/features/pagamentos/services/pagamentos-api";

export function PagamentosWorkspace() {
  const auth = useAuthStore();
  const [pagamentoId, setPagamentoId] = useState("");
  const [pagamento, setPagamento] = useState<PagamentoWeb | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const podeReconciliar = auth.permissions.includes("pagamento.confirmar");

  async function consultar(event?: FormEvent) {
    event?.preventDefault();
    const id = pagamentoId.trim();
    if (!id) return;
    setLoading(true);
    setErro(null);
    try {
      setPagamento(await obterPagamento(id));
    } catch (error) {
      setPagamento(null);
      setErro(error instanceof Error ? error.message : "Falha ao consultar pagamento");
    } finally {
      setLoading(false);
    }
  }

  async function reconciliar() {
    if (!pagamento || !podeReconciliar) return;
    setLoading(true);
    setErro(null);
    try {
      setPagamento(await reconciliarPagBank(pagamento.pagamento_id));
    } catch (error) {
      setErro(error instanceof Error ? error.message : "Falha ao reconciliar pagamento");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-6 p-6 text-slate-100">
      <header>
        <h1 className="text-2xl font-semibold">Pagamentos e PIX</h1>
        <p className="mt-2 text-sm text-slate-400">
          Consulte o ledger financeiro canônico e reconcilie cobranças PagBank já vinculadas. Credenciais continuam geridas em Integrações.
        </p>
      </header>

      <Card>
        <CardHeader><CardTitle>Consultar pagamento</CardTitle></CardHeader>
        <CardContent>
          <form className="flex gap-3" onSubmit={(event) => void consultar(event)}>
            <Input
              value={pagamentoId}
              onChange={(event) => setPagamentoId(event.target.value)}
              placeholder="ID do pagamento"
              aria-label="ID do pagamento"
            />
            <Button type="submit" disabled={loading || !pagamentoId.trim()}>
              {loading ? "Consultando…" : "Consultar"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {erro ? <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-100">{erro}</p> : null}

      {pagamento ? (
        <>
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Pagamento {pagamento.pagamento_id}</CardTitle>
              <Button
                onClick={() => void reconciliar()}
                disabled={loading || !podeReconciliar || pagamento.provedor !== "pagbank"}
              >
                Reconciliar PagBank
              </Button>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div><span className="text-xs text-slate-400">Status</span><p>{pagamento.status}</p></div>
              <div><span className="text-xs text-slate-400">Método</span><p>{pagamento.metodo}</p></div>
              <div><span className="text-xs text-slate-400">Previsto</span><p>{pagamento.moeda} {pagamento.valor_previsto}</p></div>
              <div><span className="text-xs text-slate-400">Pago</span><p>{pagamento.moeda} {pagamento.valor_pago}</p></div>
              <div><span className="text-xs text-slate-400">Saldo</span><p>{pagamento.moeda} {pagamento.saldo}</p></div>
              <div><span className="text-xs text-slate-400">Pedido</span><p>{pagamento.pedido_id}</p></div>
              <div><span className="text-xs text-slate-400">Provedor</span><p>{pagamento.provedor ?? "—"}</p></div>
              <div><span className="text-xs text-slate-400">Versão</span><p>{pagamento.versao}</p></div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Transações append-only</CardTitle></CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader><TableRow><TableHead>Quando</TableHead><TableHead>Tipo</TableHead><TableHead>Status</TableHead><TableHead>Valor</TableHead><TableHead>Provedor</TableHead><TableHead>Referência</TableHead></TableRow></TableHeader>
                <TableBody>
                  {pagamento.transacoes.map((item) => (
                    <TableRow key={item.transacao_id}>
                      <TableCell>{new Date(item.occurred_at).toLocaleString("pt-BR")}</TableCell>
                      <TableCell>{item.tipo}</TableCell>
                      <TableCell>{item.status}</TableCell>
                      <TableCell>{pagamento.moeda} {item.valor}</TableCell>
                      <TableCell>{item.provedor ?? "—"}</TableCell>
                      <TableCell>{item.id_externo ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      ) : null}
    </main>
  );
}
