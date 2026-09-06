"use client";

import { Building2, Check, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { AuthUnit } from "@/features/auth/services/auth-api";

interface UnitSelectorModalProps {
  open: boolean;
  units: AuthUnit[];
  activeUnitId: string | null;
  busyUnitId?: string | null;
  onSelect: (unit: AuthUnit) => void | Promise<void>;
  onDismiss?: () => void;
}

function unitTitle(unit: AuthUnit): string {
  return unit.nome?.trim() || unit.codigo?.trim() || `Unidade ${unit.id}`;
}

export function UnitSelectorModal({
  open,
  units,
  activeUnitId,
  busyUnitId = null,
  onSelect,
  onDismiss,
}: UnitSelectorModalProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onDismiss?.();
      }}
    >
      <DialogContent className="max-w-xl p-0 overflow-hidden">
        <div className="border-b bg-slate-950 px-6 py-5 text-white">
          <DialogHeader>
            <div className="mb-1 flex size-11 items-center justify-center rounded-xl bg-blue-500/15 ring-1 ring-blue-400/30">
              <Building2 className="size-5 text-blue-300" />
            </div>
            <DialogTitle className="text-xl">Escolha a unidade operacional</DialogTitle>
            <DialogDescription className="text-slate-300">
              Sua sessão pode operar em mais de uma loja. Selecione onde deseja trabalhar agora.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="grid gap-3 p-6">
          {units.map((unit) => {
            const active = unit.id === activeUnitId;
            const busy = unit.id === busyUnitId;

            return (
              <Button
                key={unit.id}
                type="button"
                variant="outline"
                className="h-auto min-h-16 justify-between px-4 py-3 text-left"
                disabled={Boolean(busyUnitId)}
                onClick={() => void onSelect(unit)}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-foreground">
                    {unitTitle(unit)}
                  </span>
                  <span className="mt-1 block truncate text-xs font-normal text-muted-foreground">
                    {unit.codigo ? `${unit.codigo} · ` : ""}ID {unit.id}
                  </span>
                </span>
                <span className="ml-3 flex shrink-0 items-center gap-2 text-xs">
                  {busy ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : active ? (
                    <>
                      <Check className="size-4 text-success" />
                      Ativa
                    </>
                  ) : (
                    "Selecionar"
                  )}
                </span>
              </Button>
            );
          })}
        </div>
      </DialogContent>
    </Dialog>
  );
}
