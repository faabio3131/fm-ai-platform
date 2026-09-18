"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  atualizarPreferencias,
  configurarDestinatario,
  listarDestinatarios,
  type DestinatarioNotificacao,
} from "@/features/backoffice/notificacoes/services/notificacoes-api";

export function NotificacoesWorkspace() {
  const [items, setItems] = useState<DestinatarioNotificacao[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [form, setForm] = useState({
    destinatario_id: "",
    nome_exibicao: "",
    cargo: "",
    contato: "",
  });

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      setItems(await listarDestinatarios());
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Falha ao carregar destinatários.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar(): Promise<void> {
    setSaving(true);
    setErro(null);
    try {
      await configurarDestinatario({
        destinatario_id: form.destinatario_id.trim(),
        nome_exibicao: form.nome_exibicao.trim(),
        cargo: form.cargo.trim() || null,
        contato: form.contato.trim(),
        receber_alertas_estoque: true,
        ativo: true,
      });
      setForm({
        destinatario_id: "",
        nome_exibicao: "",
        cargo: "",
        contato: "",
      });
      await carregar();
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Falha ao salvar destinatário.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function alternar(
    item: DestinatarioNotificacao,
    campo: "ativo" | "alerta",
  ): Promise<void> {
    setSaving(true);
    setErro(null);
    try {
      await atualizarPreferencias(item.destinatario_id, {
        ativo: campo === "ativo" ? !item.ativo : item.ativo,
        receber_alertas_estoque:
          campo === "alerta"
            ? !item.receber_alertas_estoque
            : item.receber_alertas_estoque,
      });
      await carregar();
    } catch (error) {
      setErro(
        error instanceof Error
          ? error.message
          : "Falha ao atualizar preferências.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="space-y-6 p-4 md:p-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">
          WP-032
        </p>
        <h1 className="text-2xl font-black text-slate-950">
          Notificações internas
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          Destinatários e alertas da unidade ativa. Contatos permanecem
          cifrados e são exibidos apenas de forma mascarada.
        </p>
      </div>
      {erro ? (
        <p
          role="alert"
          className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700"
        >
          {erro}
        </p>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>Novo destinatário WhatsApp</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <Label>
            ID interno
            <Input
              value={form.destinatario_id}
              onChange={(event) =>
                setForm((state) => ({
                  ...state,
                  destinatario_id: event.target.value,
                }))
              }
            />
          </Label>
          <Label>
            Nome
            <Input
              value={form.nome_exibicao}
              onChange={(event) =>
                setForm((state) => ({
                  ...state,
                  nome_exibicao: event.target.value,
                }))
              }
            />
          </Label>
          <Label>
            Cargo
            <Input
              value={form.cargo}
              onChange={(event) =>
                setForm((state) => ({
                  ...state,
                  cargo: event.target.value,
                }))
              }
            />
          </Label>
          <Label>
            WhatsApp
            <Input
              value={form.contato}
              onChange={(event) =>
                setForm((state) => ({
                  ...state,
                  contato: event.target.value,
                }))
              }
              placeholder="+55 11 99999-9999"
            />
          </Label>
          <div className="md:col-span-2">
            <Button
              type="button"
              disabled={
                saving ||
                !form.destinatario_id.trim() ||
                !form.nome_exibicao.trim() ||
                !form.contato.trim()
              }
              onClick={() => void salvar()}
            >
              {saving ? "Salvando..." : "Adicionar destinatário"}
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Destinatários da unidade</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-slate-500">Carregando...</p>
          ) : items.length === 0 ? (
            <p className="text-sm text-slate-500">
              Nenhum destinatário configurado.
            </p>
          ) : (
            <div className="space-y-3">
              {items.map((item) => (
                <div
                  key={item.destinatario_id}
                  className="flex flex-col justify-between gap-3 rounded-xl border border-slate-200 p-4 md:flex-row md:items-center"
                >
                  <div>
                    <p className="font-semibold text-slate-900">
                      {item.nome_exibicao}
                    </p>
                    <p className="text-sm text-slate-500">
                      {item.cargo || "Sem cargo"} · {item.contato_mascara} ·
                      WhatsApp
                    </p>
                    <p className="text-xs text-slate-400">
                      Versão {item.versao}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      disabled={saving}
                      onClick={() => void alternar(item, "alerta")}
                    >
                      Alertas de estoque:{" "}
                      {item.receber_alertas_estoque
                        ? "ligados"
                        : "desligados"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={saving}
                      onClick={() => void alternar(item, "ativo")}
                    >
                      {item.ativo ? "Desativar" : "Ativar"}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
