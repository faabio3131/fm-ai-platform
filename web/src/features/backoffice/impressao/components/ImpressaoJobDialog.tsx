"use client";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import { JobImpressao } from "@/features/backoffice/impressao/services/impressao-api";
import { STATUS_LABELS, STATUS_COLORS } from "@/features/backoffice/impressao/constants";

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

interface ImpressaoJobDialogProps {
  job: JobImpressao;
  state: {
    processing: boolean;
    reimprimindo: boolean;
    reprintMotivo: string;
    erro: string | null;
    aviso: string | null;
  };
  onProcessar: (jobId: string) => void;
  onReimprimir: (jobId: string) => void;
  onClose: () => void;
  onMotivoChange: (motivo: string) => void;
}

export function ImpressaoJobDialog({
  job,
  state,
  onProcessar,
  onReimprimir,
  onClose,
  onMotivoChange,
}: ImpressaoJobDialogProps) {

  return (
    <Dialog open={true} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Detalhes do Job: {job.job_id}</DialogTitle>
        </DialogHeader>
        {state.erro && (
          <p role="alert" className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-100">
            {state.erro}
          </p>
        )}
        {state.aviso && (
          <p role="status" className="mb-4 text-emerald-300">{state.aviso}</p>
        )}
        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <Label className="block text-xs text-slate-400">Job ID</Label>
                <p className="font-mono text-xs">{job.job_id}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Setor</Label>
                <p>{job.setor_id}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Pedido</Label>
                <p>{job.pedido_id}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Item</Label>
                <p>{job.pedido_item_id}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Status</Label>
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs ${STATUS_COLORS[job.status]}`}
                >
                  {STATUS_LABELS[job.status] ?? job.status}
                </span>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Tentativa</Label>
                <p>{job.tentativa}/{job.max_tentativas}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Impressora</Label>
                <p>{job.impressora_id}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Criado em</Label>
                <p>{formatDate(job.criado_em)}</p>
              </div>
              <div>
                <Label className="block text-xs text-slate-400">Atualizado em</Label>
                <p>{formatDate(job.atualizado_em)}</p>
              </div>
              <div className="sm:col-span-2">
                <Label className="block text-xs text-slate-400">Dedup Key</Label>
                <p className="font-mono text-xs truncate">{job.dedup_key}</p>
              </div>
              <div className="sm:col-span-2">
                <Label className="block text-xs text-slate-400">Documento Hash</Label>
                <p className="font-mono text-xs truncate">{job.documento_hash}</p>
              </div>
              {job.reimpressao_de && (
                <div className="sm:col-span-2">
                  <Label className="block text-xs text-slate-400">Reimpressão de</Label>
                  <p className="font-mono text-xs">{job.reimpressao_de}</p>
                </div>
              )}
              {job.motivo_reimpressao && (
                <div className="sm:col-span-2">
                  <Label className="block text-xs text-slate-400">Motivo</Label>
                  <p>{job.motivo_reimpressao}</p>
                </div>
              )}
            </div>
          </div>

          <div className="border-t border-slate-800 pt-4">
            <Label className="block text-sm text-slate-300 mb-1">
              Conteúdo do Ticket
            </Label>
            <pre className="bg-slate-900 rounded-md p-4 text-xs overflow-x-auto max-h-64 whitespace-pre-wrap">
              {job.conteudo}
            </pre>
          </div>

          <div className="border-t border-slate-800 pt-4">
            <Label className="block text-sm text-slate-300 mb-1">
              Processar Impressão
            </Label>
            <p className="text-xs text-slate-400 mb-2">
              Envia o ticket para a impressora configurada.
            </p>
            <Button
              onClick={() => onProcessar(job.job_id)}
              disabled={state.processing || state.reimprimindo || job.status === "impresso"}
            >
              {state.processing ? "Processando..." : "Processar Impressão"}
            </Button>
          </div>

          <div className="border-t border-slate-800 pt-4">
            <Label className="block text-sm text-slate-300 mb-1">
              Criar Reimpressão
            </Label>
            <p className="text-xs text-slate-400 mb-2">
              Cria novo job no spool com mesmo conteúdo. Requer permissão <code>impressao.reimprimir</code>.
            </p>
            <Textarea
              value={state.reprintMotivo}
              onChange={(e) => onMotivoChange(e.target.value)}
              placeholder="Ex.: ticket danificado, papel atolado, impressão ilegível"
              rows={3}
              className="mt-1 border-slate-700 bg-slate-950 text-white w-full rounded-md border p-2"
              disabled={state.reimprimindo}
            />
            <Button
              onClick={() => onReimprimir(job.job_id)}
              disabled={state.reimprimindo || state.reprintMotivo.trim().length < 5}
              className="mt-2"
            >
              {state.reimprimindo ? "Criando..." : "Criar Reimpressão"}
            </Button>
          </div>

          <div className="flex justify-end gap-2 pt-4 border-t border-slate-800">
            <Button variant="outline" onClick={onClose} disabled={state.processing || state.reimprimindo}>
              Fechar
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}