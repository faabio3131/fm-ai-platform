"use client";

import {
  CheckCircle2,
  Clock3,
  Hand,
  Loader2,
  Play,
  RotateCcw,
  UtensilsCrossed,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type {
  KdsDestination,
  KdsTicket,
} from "@/features/kds/services/kds-api";

interface KDSTicketCardProps {
  ticket: KdsTicket;
  readOnly: boolean;
  busy: boolean;
  onTransition: (ticket: KdsTicket, destino: KdsDestination) => void;
}

function shortId(value: string): string {
  return value.length <= 18 ? value : `${value.slice(0, 8)}…${value.slice(-6)}`;
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    aguardando: "Aguardando",
    aceita: "Aceito",
    em_preparo: "Em preparo",
    pausada: "Pausado",
    pronta: "Pronto",
    retirada: "Retirado",
    cancelada: "Cancelado",
  };
  return labels[status] ?? status;
}

function nextAction(status: string): {
  destino: KdsDestination;
  label: string;
  icon: typeof Play;
  className: string;
} | null {
  if (status === "aguardando") {
    return {
      destino: "aceita",
      label: "Aceitar ticket",
      icon: Hand,
      className: "bg-sky-600 hover:bg-sky-500",
    };
  }
  if (status === "aceita") {
    return {
      destino: "em_preparo",
      label: "Iniciar preparo",
      icon: Play,
      className: "bg-[#2563eb] hover:bg-blue-500",
    };
  }
  if (status === "pausada") {
    return {
      destino: "em_preparo",
      label: "Retomar preparo",
      icon: RotateCcw,
      className: "bg-[#2563eb] hover:bg-blue-500",
    };
  }
  if (status === "em_preparo") {
    return {
      destino: "pronta",
      label: "Concluir / Pronto",
      icon: CheckCircle2,
      className: "bg-[#10b981] hover:bg-emerald-400",
    };
  }
  if (status === "pronta") {
    return {
      destino: "retirada",
      label: "Confirmar retirada",
      icon: UtensilsCrossed,
      className: "bg-slate-600 hover:bg-slate-500",
    };
  }
  return null;
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function KDSTicketCard({
  ticket,
  readOnly,
  busy,
  onTransition,
}: KDSTicketCardProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const createdAt = new Date(ticket.criado_em).getTime();
  const elapsedSeconds = Math.max(0, Math.floor((now - createdAt) / 1000));
  const elapsedMinutes = elapsedSeconds / 60;
  const slaClass =
    elapsedMinutes > 20
      ? "border-[#ef4444]/70 bg-[#ef4444]/15 text-[#fca5a5] animate-pulse"
      : elapsedMinutes >= 10
        ? "border-[#f59e0b]/60 bg-[#f59e0b]/15 text-[#fcd34d]"
        : "border-[#10b981]/50 bg-[#10b981]/15 text-[#6ee7b7]";
  const action = nextAction(ticket.status);
  const ActionIcon = action?.icon;

  return (
    <Card className="overflow-hidden border-slate-700 bg-[#1e293b] text-slate-100 shadow-xl shadow-black/10">
      <CardHeader className="space-y-3 border-b border-slate-700/80 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-slate-400">
              Pedido
            </p>
            <h3 className="truncate text-xl font-black tracking-tight" title={ticket.pedido_id}>
              #{shortId(ticket.pedido_id)}
            </h3>
            <p className="mt-1 truncate text-xs font-medium text-slate-400">
              {ticket.setor_nome} · Produção {shortId(ticket.producao_id)}
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-2">
            <Badge className="border border-slate-600 bg-slate-800 text-slate-100 hover:bg-slate-800">
              {statusLabel(ticket.status)}
            </Badge>
            {ticket.prioridade > 0 ? (
              <Badge className="border border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fcd34d] hover:bg-[#f59e0b]/10">
                Prioridade {ticket.prioridade}
              </Badge>
            ) : null}
          </div>
        </div>

        <div className={`flex items-center justify-between rounded-xl border px-3 py-2 font-mono text-sm font-bold tabular-nums ${slaClass}`}>
          <span className="flex items-center gap-2">
            <Clock3 className="size-4" />
            SLA vivo
          </span>
          <span className="text-base">{formatElapsed(elapsedSeconds)}</span>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4">
        <div className="space-y-3">
          {ticket.itens.map((item) => (
            <div key={item.pedido_item_id} className="rounded-xl border border-slate-700 bg-slate-950/40 p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-base font-bold leading-tight text-white">{item.nome}</p>
                  <p className="mt-1 text-xs text-slate-400">Item {shortId(item.pedido_item_id)}</p>
                </div>
                <Badge className="min-w-11 justify-center bg-slate-700 text-base font-black tabular-nums text-white hover:bg-slate-700">
                  {item.quantidade}×
                </Badge>
              </div>
              {item.observacoes ? (
                <div className="mt-3 rounded-lg border border-[#f59e0b]/50 bg-[#f59e0b]/10 px-3 py-2 text-sm font-black uppercase tracking-wide text-[#fcd34d]">
                  {item.observacoes}
                </div>
              ) : null}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
          <div className="rounded-lg bg-slate-900/60 px-3 py-2">
            <span className="block uppercase tracking-wide">Versão</span>
            <strong className="mt-1 block font-mono text-sm text-slate-200 tabular-nums">v{ticket.versao}</strong>
          </div>
          <div className="rounded-lg bg-slate-900/60 px-3 py-2">
            <span className="block uppercase tracking-wide">Tentativa</span>
            <strong className="mt-1 block font-mono text-sm text-slate-200 tabular-nums">{ticket.tentativa}</strong>
          </div>
        </div>

        {action && ActionIcon ? (
          <Button
            type="button"
            className={`h-14 w-full rounded-xl text-base font-black text-white shadow-lg ${action.className}`}
            disabled={readOnly || busy}
            onClick={() => onTransition(ticket, action.destino)}
          >
            {busy ? <Loader2 className="animate-spin" /> : <ActionIcon />}
            {busy ? "Atualizando..." : action.label}
          </Button>
        ) : (
          <div className="rounded-xl border border-slate-700 bg-slate-900/50 px-3 py-3 text-center text-sm font-semibold text-slate-400">
            Nenhuma ação operacional disponível
          </div>
        )}
      </CardContent>
    </Card>
  );
}
