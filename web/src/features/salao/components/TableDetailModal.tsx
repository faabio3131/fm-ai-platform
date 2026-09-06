"use client";

import { FormEvent, useState } from "react";
import {
  CircleDollarSign,
  LoaderCircle,
  ReceiptText,
  UserRound,
  UsersRound,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  OpenComandaPayload,
  SalaoComandaDetails,
  SalaoComandaMapa,
  SalaoMesa,
} from "@/features/salao/services/salao-api";

interface TableDetailModalProps {
  open: boolean;
  mesa: SalaoMesa | null;
  comanda: SalaoComandaMapa | null;
  details: SalaoComandaDetails | null;
  loading: boolean;
  busy: boolean;
  onOpenChange: (open: boolean) => void;
  onOpenComanda: (payload: OpenComandaPayload) => Promise<void>;
  onRequestBill: () => Promise<void>;
}

const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

function formatCurrency(value: string | number): string {
  const numericValue = Number(value);
  return Number.isFinite(numericValue)
    ? currencyFormatter.format(numericValue)
    : "R$ —";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
}

export function TableDetailModal({
  open,
  mesa,
  comanda,
  details,
  loading,
  busy,
  onOpenChange,
  onOpenComanda,
  onRequestBill,
}: TableDetailModalProps) {
  const [responsavelNome, setResponsavelNome] = useState("");
  const [quantidadePessoas, setQuantidadePessoas] = useState("2");

  if (!mesa) return null;

  const contaSolicitada =
    (details?.status_comanda ?? comanda?.status_comanda) === "CONTA_SOLICITADA";
  const livre = mesa.status === "LIVRE" && !comanda;

  async function submitOpen(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsedPeople = Number.parseInt(quantidadePessoas, 10);
    await onOpenComanda({
      mesa_id: mesa.id,
      responsavel_nome: responsavelNome.trim() || null,
      quantidade_pessoas:
        Number.isFinite(parsedPeople) && parsedPeople > 0 ? parsedPeople : null,
    });
  }

  const items = details?.pedidos.flatMap((pedido) => pedido.itens) ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="dark max-h-[92vh] overflow-y-auto border-slate-700 bg-[#1e293b] text-slate-100 sm:max-w-3xl">
        <DialogHeader className="border-b border-slate-700 pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3 pr-6">
            <div>
              <DialogTitle className="text-2xl font-black text-white">
                Mesa {mesa.numero}
              </DialogTitle>
              <DialogDescription className="mt-1 text-slate-400">
                {mesa.nome ?? `${mesa.capacidade} lugares`} · operação canônica de Salão
              </DialogDescription>
            </div>
            <Badge
              className={
                contaSolicitada
                  ? "border border-[#f59e0b]/40 bg-[#f59e0b]/15 text-amber-200 hover:bg-[#f59e0b]/15"
                  : livre
                    ? "border border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-800"
                    : "border border-[#2563eb]/40 bg-[#2563eb]/15 text-blue-200 hover:bg-[#2563eb]/15"
              }
            >
              {contaSolicitada ? "Conta solicitada" : livre ? "Livre" : "Ocupada"}
            </Badge>
          </div>
        </DialogHeader>

        {livre ? (
          <form className="space-y-5 py-2" onSubmit={(event) => void submitOpen(event)}>
            <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
              <h3 className="font-black text-white">Abrir nova comanda</h3>
              <p className="mt-1 text-sm text-slate-400">
                A mesa será ocupada atomicamente pelo backend. Replays usam a mesma chave de idempotência da tentativa.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm font-semibold text-slate-200">
                <span className="flex items-center gap-2">
                  <UserRound className="size-4 text-[#2563eb]" />
                  Responsável (opcional)
                </span>
                <Input
                  value={responsavelNome}
                  onChange={(event) => setResponsavelNome(event.target.value)}
                  placeholder="Nome de referência"
                  maxLength={120}
                  className="h-12 border-slate-600 bg-slate-950 text-white"
                />
              </label>
              <label className="space-y-1.5 text-sm font-semibold text-slate-200">
                <span className="flex items-center gap-2">
                  <UsersRound className="size-4 text-[#2563eb]" />
                  Pessoas
                </span>
                <Input
                  type="number"
                  min={1}
                  max={1000}
                  value={quantidadePessoas}
                  onChange={(event) => setQuantidadePessoas(event.target.value)}
                  className="h-12 border-slate-600 bg-slate-950 text-white tabular-nums"
                />
              </label>
            </div>

            <Button
              type="submit"
              disabled={busy}
              className="h-12 w-full rounded-xl bg-[#2563eb] text-base font-black hover:bg-blue-500"
            >
              {busy ? <LoaderCircle className="animate-spin" /> : <ReceiptText />}
              {busy ? "Abrindo comanda..." : "Abrir comanda"}
            </Button>
          </form>
        ) : loading ? (
          <div className="flex min-h-72 items-center justify-center gap-3 text-sm font-semibold text-slate-400">
            <LoaderCircle className="size-5 animate-spin text-[#2563eb]" />
            Carregando extrato da comanda...
          </div>
        ) : details ? (
          <div className="space-y-5 py-2">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-2xl border border-slate-700 bg-slate-950/55 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
                  Comanda
                </p>
                <p className="mt-2 font-mono text-lg font-black text-white">
                  {details.numero}
                </p>
              </div>
              <div className="rounded-2xl border border-slate-700 bg-slate-950/55 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
                  Aberta em
                </p>
                <p className="mt-2 text-sm font-bold text-slate-200">
                  {formatDate(details.aberta_em)}
                </p>
              </div>
              <div className="rounded-2xl border border-[#2563eb]/35 bg-[#2563eb]/10 p-4">
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-blue-300">
                  Total acumulado
                </p>
                <p className="mt-2 text-2xl font-black tabular-nums text-white">
                  {formatCurrency(details.total)}
                </p>
              </div>
            </div>

            <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/35">
              <div className="flex items-center justify-between gap-3 border-b border-slate-700 px-4 py-3">
                <div>
                  <h3 className="font-black text-white">Extrato de consumo</h3>
                  <p className="text-xs text-slate-500">
                    {details.pedidos.length} pedido(s) · {items.length} item(ns)
                  </p>
                </div>
                <ReceiptText className="size-5 text-[#2563eb]" />
              </div>

              {items.length > 0 ? (
                <Table>
                  <TableHeader>
                    <TableRow className="border-slate-800 hover:bg-transparent">
                      <TableHead className="text-slate-400">Item</TableHead>
                      <TableHead className="w-20 text-right text-slate-400">Qtd.</TableHead>
                      <TableHead className="w-32 text-right text-slate-400">Subtotal</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {items.map((item) => (
                      <TableRow key={item.id} className="border-slate-800 hover:bg-slate-900/60">
                        <TableCell>
                          <p className="font-semibold text-slate-100">{item.nome}</p>
                          {item.observacao ? (
                            <p className="mt-1 text-xs text-slate-500">{item.observacao}</p>
                          ) : null}
                        </TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-slate-300">
                          {item.quantidade}
                        </TableCell>
                        <TableCell className="text-right font-mono font-bold tabular-nums text-slate-100">
                          {formatCurrency(item.subtotal)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              ) : (
                <div className="px-4 py-10 text-center text-sm font-medium text-slate-500">
                  Nenhum item vinculado à comanda até o momento.
                </div>
              )}
            </div>

            <div className="flex flex-col gap-3 rounded-2xl border border-slate-700 bg-slate-950/50 p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.14em] text-slate-500">
                  Saldo da comanda
                </p>
                <p className="mt-1 text-2xl font-black tabular-nums text-white">
                  {formatCurrency(details.saldo)}
                </p>
              </div>
              <Button
                type="button"
                disabled={busy || contaSolicitada}
                onClick={() => void onRequestBill()}
                className={
                  contaSolicitada
                    ? "h-12 rounded-xl bg-[#f59e0b]/20 font-black text-amber-200"
                    : "h-12 rounded-xl bg-[#f59e0b] font-black text-slate-950 hover:bg-amber-400"
                }
              >
                {busy ? (
                  <LoaderCircle className="animate-spin" />
                ) : (
                  <CircleDollarSign />
                )}
                {contaSolicitada
                  ? "Conta já solicitada"
                  : busy
                    ? "Solicitando..."
                    : "Solicitar encerramento"}
              </Button>
            </div>
          </div>
        ) : (
          <div className="py-10 text-center text-sm font-medium text-slate-500">
            Não foi possível carregar os detalhes desta comanda.
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
