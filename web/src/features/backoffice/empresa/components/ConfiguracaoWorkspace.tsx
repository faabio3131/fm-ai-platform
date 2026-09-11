"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/features/auth/store/auth-store";
import { API_BASE_URL } from "@/lib/api";
import {
  obterConfiguracao,
  salvarConfiguracao,
  type ConfiguracaoFinanceira,
} from "@/features/backoffice/empresa/services/empresa-api";

const FORMAS_PAGAMENTO_DISPONIVEIS = [
  "dinheiro",
  "pix",
  "cartao_credito",
  "cartao_debito",
  "voucher",
  "outro",
  "pagamento_na_entrega",
  "recebimento_posterior",
] as const;

type FormaPagamento = typeof FORMAS_PAGAMENTO_DISPONIVEIS[number];

interface ConfiguracaoWorkspaceState {
  configuracoes: Record<string, ConfiguracaoFinanceira>;
  unidades: { unidade_id: string; nome_fantasia: string }[];
  loading: boolean;
  saving: boolean;
  editingUnidadeId: string | null;
  form: {
    formas_pagamento: FormaPagamento[];
    taxa_servico_percentual: string;
    parametros_operacionais: string;
    politica_financeira: string;
  };
  erro: string | null;
  aviso: string | null;
}

export function ConfiguracaoWorkspace() {
  const auth = useAuthStore();
  const [state, setState] = useState<ConfiguracaoWorkspaceState>({
    configuracoes: {},
    unidades: [],
    loading: true,
    saving: false,
    editingUnidadeId: null,
    form: {
      formas_pagamento: [],
      taxa_servico_percentual: "0",
      parametros_operacionais: "{}",
      politica_financeira: "{}",
    },
    erro: null,
    aviso: null,
  });

  const fetchUnidades = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/v1/admin/empresa`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (res.ok) {
        const data = await res.json();
        setState((s) => ({
          ...s,
          unidades: data.unidades.map((u: any) => ({
            unidade_id: u.unidade_id,
            nome_fantasia: u.nome_fantasia,
          })),
        }));
      }
    } catch {
      // silencioso
    }
  }, []);

  const fetchConfiguracao = useCallback(async (unidadeId: string) => {
    try {
      const config = await obterConfiguracao(unidadeId);
      setState((s) => ({
        ...s,
        configuracoes: {
          ...s.configuracoes,
          [unidadeId]: config,
        },
      }));
    } catch {
      // silencioso - configuração pode não existir ainda
    }
  }, []);

  const fetchAllConfiguracoes = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, erro: null }));
    try {
      for (const unidade of state.unidades) {
        await fetchConfiguracao(unidade.unidade_id);
      }
      setState((s) => ({ ...s, loading: false }));
    } catch {
      setState((s) => ({ ...s, loading: false, erro: "Erro ao carregar configurações" }));
    }
  }, [state.unidades, fetchConfiguracao]);

  const handleOpenEdit = useCallback((unidadeId: string) => {
    const config = state.configuracoes[unidadeId];
    if (!config) return;

    setState((s) => ({
      ...s,
      editingUnidadeId: unidadeId,
      form: {
        formas_pagamento: config.formas_pagamento as FormaPagamento[],
        taxa_servico_percentual: config.taxa_servico_percentual,
        parametros_operacionais: JSON.stringify(config.parametros_operacionais, null, 2),
        politica_financeira: JSON.stringify(config.politica_financeira, null, 2),
      },
      erro: null,
      aviso: null,
    }));
  }, [state.configuracoes]);

  const handleCloseEdit = useCallback(() => {
    setState((s) => ({
      ...s,
      editingUnidadeId: null,
      form: {
        formas_pagamento: [],
        taxa_servico_percentual: "0",
        parametros_operacionais: "{}",
        politica_financeira: "{}",
      },
      erro: null,
      aviso: null,
    }));
  }, []);

  const handleChange = useCallback((field: string, value: any) => {
    setState((s) => ({ ...s, form: { ...s.form, [field]: value } }));
  }, []);

  const handleToggleFormaPagamento = useCallback((forma: FormaPagamento) => {
    setState((s) => ({
      ...s,
      form: {
        ...s.form,
        formas_pagamento: s.form.formas_pagamento.includes(forma)
          ? s.form.formas_pagamento.filter((f) => f !== forma)
          : [...s.form.formas_pagamento, forma],
      },
    }));
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!state.editingUnidadeId) return;

    let parametros_operacionais: Record<string, unknown>;
    let politica_financeira: Record<string, unknown>;

    try {
      parametros_operacionais = JSON.parse(state.form.parametros_operacionais);
      politica_financeira = JSON.stringify(state.form.politica_financeira) === "{}" 
        ? {} 
        : JSON.parse(state.form.politica_financeira);
    } catch {
      setState((s) => ({ ...s, erro: "JSON inválido em parâmetros operacionais ou política financeira" }));
      return;
    }

    setState((s) => ({ ...s, saving: true, erro: null, aviso: null }));

    try {
      const configAtual = state.configuracoes[state.editingUnidadeId];
      if (!configAtual) {
        setState((s) => ({ ...s, saving: false, erro: "Configuração não encontrada" }));
        return;
      }

      await salvarConfiguracao(state.editingUnidadeId, {
        formas_pagamento: state.form.formas_pagamento,
        taxa_servico_percentual: state.form.taxa_servico_percentual,
        parametros_operacionais,
        politica_financeira,
        versao: configAtual.versao,
      });

      handleCloseEdit();
      await fetchConfiguracao(state.editingUnidadeId!);
      setState((s) => ({ ...s, aviso: "Configuração salva com sucesso" }));
    } catch (error) {
      setState((s) => ({ ...s, saving: false, erro: error instanceof Error ? error.message : "Falha ao salvar" }));
    }
  }, [state.editingUnidadeId, state.form, state.configuracoes, fetchConfiguracao, handleCloseEdit]);

  useEffect(() => {
    fetchUnidades();
  }, [fetchUnidades, auth.tenantId, auth.unitId]);

  useEffect(() => {
    if (state.unidades.length > 0) {
      fetchAllConfiguracoes();
    }
  }, [state.unidades, fetchAllConfiguracoes, auth.tenantId, auth.unitId]);

  const inputClass = "mt-1 border-slate-700 bg-slate-950 text-white";

  const currentConfig = state.editingUnidadeId ? state.configuracoes[state.editingUnidadeId] : null;

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 p-6 text-slate-100">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Parâmetros Financeiros</h1>
          <p className="mt-2 text-sm text-slate-400">
            Configure formas de pagamento, taxa de serviço e parâmetros operacionais por unidade.
          </p>
        </div>
        <Button onClick={() => void fetchAllConfiguracoes()} disabled={state.loading || state.saving}>
          Recarregar
        </Button>
      </header>

      {state.erro ? (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-100">
          {state.erro}
        </p>
      ) : null}
      {state.aviso ? (
        <p role="status" className="text-emerald-300">{state.aviso}</p>
      ) : null}

      {state.loading ? (
        <p role="status">Carregando configurações…</p>
      ) : state.unidades.length === 0 ? (
        <p>Nenhuma unidade cadastrada.</p>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Configurações por Unidade</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Unidade</TableHead>
                      <TableHead>Formas de Pagamento</TableHead>
                      <TableHead>Taxa Serviço (%)</TableHead>
                      <TableHead>Versão</TableHead>
                      <TableHead className="w-[100px]">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {state.unidades.map((unidade) => {
                      const config = state.configuracoes[unidade.unidade_id];
                      return (
                        <TableRow key={unidade.unidade_id}>
                          <TableCell>{unidade.nome_fantasia} ({unidade.unidade_id})</TableCell>
                          <TableCell>
                            {config ? (
                              <div className="flex flex-wrap gap-1">
                                {config.formas_pagamento.map((f) => (
                                  <span
                                    key={f}
                                    className="inline-flex items-center rounded-full bg-blue-500/20 px-2 py-0.5 text-xs text-blue-300"
                                  >
                                    {f}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </TableCell>
                          <TableCell>{config ? config.taxa_servico_percentual : "—"}</TableCell>
                          <TableCell>{config ? String(config.versao) : "—"}</TableCell>
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleOpenEdit(unidade.unidade_id)}
                              aria-label="Editar configuração"
                              disabled={state.saving}
                            >
                              ✏️
                            </Button>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {state.editingUnidadeId && currentConfig && (
            <Card className="border-amber-500/30 bg-amber-500/[0.02]">
              <CardHeader>
                <CardTitle>Editar: {state.unidades.find(u => u.unidade_id === state.editingUnidadeId)?.nome_fantasia}</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={(e) => { e.preventDefault(); handleSubmit(); }} className="space-y-4">
                  <div>
                    <Label className="block text-sm text-slate-300 mb-1">
                      Formas de Pagamento <span className="text-rose-400">*</span>
                    </Label>
                    <div className="flex flex-wrap gap-2">
                      {FORMAS_PAGAMENTO_DISPONIVEIS.map((forma) => (
                        <Button
                          key={forma}
                          type="button"
                          variant={state.form.formas_pagamento.includes(forma) ? "default" : "outline"}
                          size="sm"
                          onClick={() => handleToggleFormaPagamento(forma)}
                        >
                          {forma}
                        </Button>
                      ))}
                    </div>
                    {state.form.formas_pagamento.length === 0 && (
                      <p className="mt-1 text-xs text-rose-400">Selecione ao menos uma forma de pagamento</p>
                    )}
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <Label className="block text-sm text-slate-300">
                      Taxa de Serviço (%) <span className="text-rose-400">*</span>
                      <Input
                        type="number"
                        step="0.01"
                        min="0"
                        max="100"
                        value={state.form.taxa_servico_percentual}
                        onChange={(e) => handleChange("taxa_servico_percentual", e.target.value)}
                        className={`${inputClass} w-full rounded-md border p-2 mt-1`}
                      />
                    </Label>

                    <Label className="block text-sm text-slate-300">
                      Versão Atual (concorrência)
                      <Input
                        type="text"
                        value={String(currentConfig.versao)}
                        readOnly
                        className={`${inputClass} w-full rounded-md border p-2 mt-1 bg-slate-800`}
                      />
                    </Label>
                  </div>

                  <Label className="block text-sm text-slate-300">
                    Parâmetros Operacionais (JSON)
                    <textarea
                      value={state.form.parametros_operacionais}
                      onChange={(e) => handleChange("parametros_operacionais", e.target.value)}
                      rows={4}
                      className={`${inputClass} w-full rounded-md border p-2 mt-1 font-mono text-xs`}
                      placeholder='{"chave": "valor"}'
                    />
                  </Label>

                  <Label className="block text-sm text-slate-300">
                    Política Financeira (JSON)
                    <textarea
                      value={state.form.politica_financeira}
                      onChange={(e) => handleChange("politica_financeira", e.target.value)}
                      rows={4}
                      className={`${inputClass} w-full rounded-md border p-2 mt-1 font-mono text-xs`}
                      placeholder='{"chave": "valor"}'
                    />
                  </Label>

                  <div className="flex justify-end gap-2 pt-4 border-t border-slate-800">
                    <Button type="button" variant="outline" onClick={handleCloseEdit} disabled={state.saving}>
                      Cancelar
                    </Button>
                    <Button type="submit" disabled={state.saving || state.form.formas_pagamento.length === 0}>
                      {state.saving ? "Salvando..." : "Salvar Configuração"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </main>
  );
}