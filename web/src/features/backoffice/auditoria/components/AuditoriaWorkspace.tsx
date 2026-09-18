"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  listarAuditoria,
  type AuditoriaPage,
} from "@/features/backoffice/auditoria/services/auditoria-api";

const EMPTY_PAGE: AuditoriaPage = {
  eventos: [],
  pagina: 1,
  tamanho: 50,
  tem_mais: false,
};

export function AuditoriaWorkspace() {
  const [pagina, setPagina] = useState(1);
  const [dados, setDados] = useState<AuditoriaPage>(EMPTY_PAGE);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [acao, setAcao] = useState("");
  const [resultado, setResultado] = useState("");
  const [usuarioId, setUsuarioId] = useState("");
  const [recursoTipo, setRecursoTipo] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void listarAuditoria(pagina, {
      acao,
      resultado,
      usuario_id: usuarioId,
      recurso_tipo: recursoTipo,
    })
      .then((next) => {
        if (!cancelled) {
          setDados(next);
          setErro(null);
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setErro(
            error instanceof Error ? error.message : "Falha ao carregar auditoria.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [acao, pagina, recursoTipo, resultado, usuarioId]);

  function resetarPagina(): void {
    setPagina(1);
  }

  return (
    <main className="space-y-6 p-4 md:p-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-blue-600">
          WP-033
        </p>
        <h1 className="text-2xl font-black text-slate-950">Auditoria</h1>
        <p className="mt-1 text-sm text-slate-600">
          Trilha read-only da unidade ativa. Segredos, tokens e metadata interna
          não são expostos nesta superfície.
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
          <CardTitle>Filtros</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <Label>
            Ação
            <Input value={acao} onChange={(event) => { setAcao(event.target.value); resetarPagina(); }} />
          </Label>
          <Label>
            Resultado
            <Input value={resultado} onChange={(event) => { setResultado(event.target.value); resetarPagina(); }} />
          </Label>
          <Label>
            Usuário
            <Input value={usuarioId} onChange={(event) => { setUsuarioId(event.target.value); resetarPagina(); }} />
          </Label>
          <Label>
            Recurso
            <Input value={recursoTipo} onChange={(event) => { setRecursoTipo(event.target.value); resetarPagina(); }} />
          </Label>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Eventos da unidade</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {loading ? (
            <p className="text-sm text-slate-500">Carregando...</p>
          ) : dados.eventos.length === 0 ? (
            <p className="text-sm text-slate-500">Nenhum evento encontrado.</p>
          ) : (
            dados.eventos.map((evento) => (
              <article
                key={evento.audit_id}
                className="rounded-xl border border-slate-200 p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-slate-900">{evento.acao}</p>
                  <time className="text-xs text-slate-500">
                    {new Date(evento.timestamp).toLocaleString("pt-BR")}
                  </time>
                </div>
                <p className="mt-1 text-sm text-slate-600">
                  {evento.resultado} · {evento.usuario_id} · {evento.recurso_tipo}
                  {evento.recurso_id ? `/${evento.recurso_id}` : ""}
                </p>
                <p className="mt-2 text-xs text-slate-500">{evento.motivo}</p>
                <p className="mt-1 break-all font-mono text-[11px] text-slate-400">
                  correlation: {evento.correlation_id}
                </p>
              </article>
            ))
          )}
          <div className="flex justify-between gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              disabled={loading || pagina <= 1}
              onClick={() => setPagina((value) => Math.max(1, value - 1))}
            >
              Anterior
            </Button>
            <span className="self-center text-xs text-slate-500">Página {pagina}</span>
            <Button
              type="button"
              variant="outline"
              disabled={loading || !dados.tem_mais}
              onClick={() => setPagina((value) => value + 1)}
            >
              Próxima
            </Button>
          </div>
        </CardContent>
      </Card>
    </main>
  );
}
