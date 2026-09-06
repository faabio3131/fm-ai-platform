"use client";

import { Armchair, ReceiptText, UsersRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type {
  SalaoComandaMapa,
  SalaoFloorMap,
  SalaoMesa,
} from "@/features/salao/services/salao-api";

interface FloorMapProps {
  floorMap: SalaoFloorMap;
  selectedTableId?: string | null;
  onSelectTable: (mesa: SalaoMesa, comanda: SalaoComandaMapa | null) => void;
}

function visualState(
  mesa: SalaoMesa,
  comanda: SalaoComandaMapa | null,
): "livre" | "ocupada" | "conta" | "inativa" {
  if (mesa.status === "INATIVA") return "inativa";
  if (comanda?.status_comanda === "CONTA_SOLICITADA") return "conta";
  if (mesa.status === "OCUPADA" || comanda) return "ocupada";
  return "livre";
}

const stateStyles = {
  livre: {
    card: "border-slate-700 bg-slate-900/65 hover:border-slate-500 hover:bg-slate-800/80",
    icon: "bg-slate-800 text-slate-300",
    badge: "border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-800",
    label: "Livre",
  },
  ocupada: {
    card: "border-[#2563eb]/55 bg-[#2563eb]/10 hover:border-[#2563eb] hover:bg-[#2563eb]/15",
    icon: "bg-[#2563eb] text-white",
    badge: "border-[#2563eb]/40 bg-[#2563eb]/15 text-blue-200 hover:bg-[#2563eb]/15",
    label: "Ocupada",
  },
  conta: {
    card: "border-[#f59e0b]/60 bg-[#f59e0b]/10 hover:border-[#f59e0b] hover:bg-[#f59e0b]/15",
    icon: "bg-[#f59e0b] text-slate-950",
    badge: "border-[#f59e0b]/40 bg-[#f59e0b]/15 text-amber-200 hover:bg-[#f59e0b]/15",
    label: "Conta solicitada",
  },
  inativa: {
    card: "cursor-not-allowed border-slate-800 bg-slate-950/45 opacity-50",
    icon: "bg-slate-900 text-slate-600",
    badge: "border-slate-800 bg-slate-900 text-slate-500 hover:bg-slate-900",
    label: "Inativa",
  },
} as const;

export function FloorMap({
  floorMap,
  selectedTableId,
  onSelectTable,
}: FloorMapProps) {
  const commandByTable = new Map(
    floorMap.comandas
      .filter((comanda) => comanda.mesa_id)
      .map((comanda) => [comanda.mesa_id as string, comanda]),
  );

  return (
    <section aria-label="Mapa de mesas" className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-slate-400">
        <Badge className="border border-slate-600 bg-slate-800 text-slate-200 hover:bg-slate-800">
          Livre
        </Badge>
        <Badge className="border border-[#2563eb]/40 bg-[#2563eb]/15 text-blue-200 hover:bg-[#2563eb]/15">
          Ocupada
        </Badge>
        <Badge className="border border-[#f59e0b]/40 bg-[#f59e0b]/15 text-amber-200 hover:bg-[#f59e0b]/15">
          Conta solicitada
        </Badge>
      </div>

      {floorMap.mesas.length === 0 ? (
        <div className="flex min-h-64 items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 p-8 text-center text-sm font-medium text-slate-500">
          Nenhuma mesa disponível para este tenant e unidade.
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
          {floorMap.mesas.map((mesa) => {
            const comanda = commandByTable.get(mesa.id) ?? null;
            const state = visualState(mesa, comanda);
            const styles = stateStyles[state];
            const selected = selectedTableId === mesa.id;

            return (
              <button
                key={mesa.id}
                type="button"
                disabled={state === "inativa"}
                onClick={() => onSelectTable(mesa, comanda)}
                className={`min-h-40 rounded-2xl border p-4 text-left shadow-lg shadow-black/10 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb] ${styles.card} ${selected ? "ring-2 ring-[#2563eb] ring-offset-2 ring-offset-[#0f172a]" : ""}`}
                aria-label={`Mesa ${mesa.numero}, ${styles.label}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className={`flex size-11 items-center justify-center rounded-xl ${styles.icon}`}>
                    {state === "conta" ? (
                      <ReceiptText className="size-5" />
                    ) : (
                      <Armchair className="size-5" />
                    )}
                  </div>
                  <Badge className={`border ${styles.badge}`}>
                    {styles.label}
                  </Badge>
                </div>

                <div className="mt-5">
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
                    Mesa
                  </p>
                  <p className="mt-1 text-3xl font-black tabular-nums text-white">
                    {mesa.numero}
                  </p>
                  {mesa.nome ? (
                    <p className="mt-1 truncate text-sm font-medium text-slate-300">
                      {mesa.nome}
                    </p>
                  ) : null}
                </div>

                <div className="mt-4 flex items-center justify-between gap-3 border-t border-white/5 pt-3 text-xs text-slate-400">
                  <span className="flex items-center gap-1.5">
                    <UsersRound className="size-3.5" />
                    {mesa.capacidade} lugares
                  </span>
                  {comanda ? (
                    <span className="flex items-center gap-1.5 font-mono text-slate-300">
                      <ReceiptText className="size-3.5" />
                      {comanda.id.slice(0, 8)}
                    </span>
                  ) : null}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
