"use client";

import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAuthStore } from "@/features/auth/store/auth-store";
import {
  listarJobs,
  processarJob,
  reimprimirJob,
  type JobImpressao,
} from "@/features/backoffice/impressao/services/impressao-api";
import { ImpressaoJobDialog } from "@/features/backoffice/impressao/components/ImpressaoJobDialog";
import { STATUS_LABELS, STATUS_COLORS } from "@/features/backoffice/impressao/constants";

interface ImpressaoWorkspaceState {
  jobs: JobImpressao[];
  loading: boolean;
  processing: boolean;
  reimprimindo: boolean;
  selectedJob: JobImpressao | null;
  reprintMotivo: string;
  erro: string | null;
  aviso: string | null;
}

export function ImpressaoWorkspace() {
  const auth = useAuthStore();
  const [state, setState] = useState<ImpressaoWorkspaceState>({
    jobs: [],
    loading: true,
    processing: false,
    reimprimindo: false,
    selectedJob: null,
    reprintMotivo: "",
    erro: null,
    aviso: null,
  });

  const carregar = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, erro: null }));
    try {
      const jobs = await listarJobs();
      setState((s) => ({ ...s, jobs, loading: false }));
    } catch (error) {
      setState((s) => ({
        ...s,
        loading: false,
        erro: error instanceof Error ? error.message : "Não foi possível carregar jobs de impressão.",
      }));
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timer);
  }, [carregar, auth.tenantId, auth.unitId]);

  const handleVerDetalhes = useCallback((job: JobImpressao) => {
    setState((s) => ({ ...s, selectedJob: job, erro: null, aviso: null }));
  }, []);

  const handleFecharDetalhes = useCallback(() => {
    setState((s) => ({ ...s, selectedJob: null, reprintMotivo: "", erro: null, aviso: null }));
  }, []);

  const handleProcessar = useCallback(async (jobId: string) => {
    setState((s) => ({ ...s, processing: true, erro: null, aviso: null }));
    try {
      const resultado = await processarJob(jobId);
      await carregar();
      if (resultado.impresso) {
        setState((s) => ({ ...s, aviso: "Impressão enviada com sucesso." }));
      } else if (resultado.contingencia) {
        setState((s) => ({ ...s, aviso: "Job movido para contingência." }));
      } else {
        setState((s) => ({ ...s, aviso: "Impressora indisponível; tentativa registrada." }));
      }
    } catch (error) {
      setState((s) => ({
        ...s,
        erro: error instanceof Error ? error.message : "Não foi possível processar a impressão.",
      }));
    } finally {
      setState((s) => ({ ...s, processing: false }));
    }
  }, [carregar]);

  const handleReimprimir = useCallback(async (jobId: string) => {
    setState((s) => ({ ...s, reimprimindo: true, erro: null, aviso: null }));
    try {
      await reimprimirJob(jobId, {
        motivo: state.reprintMotivo.trim(),
        idempotency_key: `ui-reprint:${jobId}:${crypto.randomUUID()}`,
      });
      handleFecharDetalhes();
      await carregar();
      setState((s) => ({ ...s, aviso: "Reimpressão criada no spool." }));
    } catch (error) {
      setState((s) => ({
        ...s,
        erro: error instanceof Error ? error.message : "Reimpressão não autorizada ou motivo inválido.",
      }));
    } finally {
      setState((s) => ({ ...s, reimprimindo: false }));
    }
  }, [state.reprintMotivo, carregar, handleFecharDetalhes]);

  const handleMotivoChange = useCallback((motivo: string) => {
    setState((s) => ({ ...s, reprintMotivo: motivo }));
  }, []);

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  return (
    <main className="mx-auto w-full max-w-5xl space-y-6 p-6 text-slate-100">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Impressão Operacional</h1>
          <p className="mt-2 text-sm text-slate-400">
            Spool auxiliar do KDS. Falha de impressora não altera Pedido nem Produção.
          </p>
        </div>
        <Button onClick={() => void carregar()} disabled={state.loading || state.processing}>
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
        <p role="status">Carregando spool de impressão…</p>
      ) : state.jobs.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-slate-400">
            Nenhum job de impressão encontrado nesta unidade.
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle>Jobs de Impressão</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Criado</TableHead>
                      <TableHead>Setor</TableHead>
                      <TableHead>Pedido</TableHead>
                      <TableHead>Item</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Tentativa</TableHead>
                      <TableHead>Impressora</TableHead>
                      <TableHead className="w-[80px]">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {state.jobs.map((job) => (
                      <TableRow key={job.job_id}>
                        <TableCell>{formatDate(job.criado_em)}</TableCell>
                        <TableCell>{job.setor_id}</TableCell>
                        <TableCell>{job.pedido_id}</TableCell>
                        <TableCell>{job.pedido_item_id}</TableCell>
                        <TableCell>
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${STATUS_COLORS[job.status]}`}
                          >
                            {STATUS_LABELS[job.status] ?? job.status}
                          </span>
                        </TableCell>
                        <TableCell>{job.tentativa}/{job.max_tentativas}</TableCell>
                        <TableCell>{job.impressora_id}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleVerDetalhes(job)}
                            aria-label="Ver detalhes"
                            disabled={state.processing || state.reimprimindo}
                          >
                            👁️
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {state.selectedJob && (
            <ImpressaoJobDialog
              job={state.selectedJob}
              state={{
                processing: state.processing,
                reimprimindo: state.reimprimindo,
                reprintMotivo: state.reprintMotivo,
                erro: state.erro,
                aviso: state.aviso,
              }}
              onProcessar={handleProcessar}
              onReimprimir={handleReimprimir}
              onClose={handleFecharDetalhes}
              onMotivoChange={handleMotivoChange}
            />
          )}
        </>
      )}
    </main>
  );
}