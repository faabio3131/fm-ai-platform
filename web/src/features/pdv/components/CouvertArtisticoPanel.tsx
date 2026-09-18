"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  fetchConfiguracaoFechamento,
  salvarConfiguracaoFechamento,
  type ConfiguracaoFechamento,
} from "@/features/garcom/services/garcom-api";

export function CouvertArtisticoPanel() {
  const auth = useAuthStore();
  const canEdit = auth.permissions.includes("configuracao.alterar");
  const [config, setConfig] = useState<ConfiguracaoFechamento | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [value, setValue] = useState("0.00");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status !== "authenticated" || !auth.unitId) return;
    let cancelled = false;
    void fetchConfiguracaoFechamento()
      .then((item) => {
        if (cancelled) return;
        setConfig(item);
        setEnabled(item.couvert_ativado);
        setValue(item.couvert_valor);
      })
      .catch(() => {
        if (!cancelled) setMessage("Configuração de couvert indisponível.");
      });
    return () => {
      cancelled = true;
    };
  }, [auth.status, auth.unitId]);

  async function save() {
    if (!config || !canEdit) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await salvarConfiguracaoFechamento({
        modo_recebimento: config.modo_recebimento,
        couvert_ativado: enabled,
        couvert_valor: value,
        versao: config.versao,
      });
      setConfig(updated);
      setEnabled(updated.couvert_ativado);
      setValue(updated.couvert_valor);
      setMessage("Couvert artístico atualizado para esta unidade.");
    } catch (caught) {
      setMessage(
        caught instanceof Error
          ? caught.message
          : "Não foi possível salvar o couvert.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="rounded-2xl border bg-white p-4 shadow-sm" aria-label="Couvert artístico">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.14em] text-muted-foreground">
            Couvert artístico
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Configuração da unidade ativa. Não altera contas já consolidadas.
          </p>
        </div>
        <Button
          type="button"
          variant={enabled ? "default" : "outline"}
          onClick={() => setEnabled((current) => !current)}
          disabled={!config || !canEdit || saving}
          aria-pressed={enabled}
        >
          {enabled ? "ATIVADO" : "DESATIVADO"}
        </Button>
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="min-w-44 flex-1 text-sm font-semibold">
          Valor
          <Input
            className="mt-1 h-11"
            type="number"
            min="0"
            step="0.01"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            disabled={!config || !canEdit || saving}
          />
        </label>
        <Button
          type="button"
          className="h-11"
          onClick={() => void save()}
          disabled={!config || !canEdit || saving}
        >
          {saving ? "Salvando..." : "Salvar"}
        </Button>
      </div>
      {!canEdit ? (
        <p className="mt-2 text-xs text-muted-foreground">
          Somente uma identidade com configuracao.alterar pode modificar este parâmetro.
        </p>
      ) : null}
      {message ? <p className="mt-2 text-xs text-muted-foreground">{message}</p> : null}
    </section>
  );
}
