"use client";

import { FormEvent, useMemo, useState } from "react";

import {
  confirmarGerenteIA,
  GerenteIAResponse,
  perguntarGerenteIA,
} from "../services/gerente-ia-api";

function recordOf(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function previewOf(response: GerenteIAResponse | null) {
  const result = recordOf(response?.resultado);
  if (!result) return null;
  const previewId = result.preview_id;
  const fingerprint = result.fingerprint;
  if (typeof previewId !== "string" || typeof fingerprint !== "string") return null;
  return { previewId, fingerprint };
}

export function GerenteIAWorkspace() {
  const [pergunta, setPergunta] = useState("");
  const [resposta, setResposta] = useState<GerenteIAResponse | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const preview = useMemo(() => previewOf(resposta), [resposta]);

  async function perguntar(event: FormEvent) {
    event.preventDefault();
    if (!pergunta.trim() || carregando) return;
    setCarregando(true);
    setErro(null);
    try {
      setResposta(await perguntarGerenteIA(pergunta.trim()));
    } catch (error) {
      setErro(error instanceof Error ? error.message : "gerente_ia.indisponivel");
    } finally {
      setCarregando(false);
    }
  }

  async function confirmar() {
    if (!preview || carregando) return;
    setCarregando(true);
    setErro(null);
    try {
      setResposta(
        await confirmarGerenteIA({
          preview_id: preview.previewId,
          fingerprint: preview.fingerprint,
          idempotency_key: crypto.randomUUID(),
        }),
      );
    } catch (error) {
      setErro(error instanceof Error ? error.message : "gerente_ia.confirmacao_falhou");
    } finally {
      setCarregando(false);
    }
  }

  return (
    <section className="mx-auto flex w-full max-w-5xl flex-col gap-6">
      <header>
        <p className="text-sm font-medium text-muted-foreground">Operação assistida por IA</p>
        <h1 className="text-3xl font-semibold tracking-tight">Gerente IA</h1>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Consulte a operação, prepare decisões e confirme ações governadas sem sair do escopo da unidade ativa.
        </p>
      </header>

      <form onSubmit={perguntar} className="rounded-xl border bg-card p-5 shadow-sm">
        <label htmlFor="gerente-pergunta" className="text-sm font-medium">
          Pergunte ao Gerente IA
        </label>
        <textarea
          id="gerente-pergunta"
          value={pergunta}
          onChange={(event) => setPergunta(event.target.value)}
          rows={5}
          maxLength={4000}
          className="mt-2 w-full rounded-md border bg-background p-3 text-sm outline-none focus:ring-2 focus:ring-ring"
          placeholder="Ex.: quais pedidos estão atrasados agora?"
        />
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{pergunta.length}/4000</span>
          <button
            type="submit"
            disabled={!pergunta.trim() || carregando}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          >
            {carregando ? "Processando..." : "Enviar"}
          </button>
        </div>
      </form>

      {erro ? (
        <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {erro}
        </div>
      ) : null}

      {resposta ? (
        <article className="rounded-xl border bg-card p-5 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Resultado</p>
              <h2 className="text-lg font-semibold">{resposta.tipo}</h2>
              {resposta.nome_assistente ? (
                <p className="text-sm text-muted-foreground">Identidade: {resposta.nome_assistente}</p>
              ) : null}
            </div>
            {preview ? (
              <button
                type="button"
                onClick={confirmar}
                disabled={carregando}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
              >
                Confirmar ação governada
              </button>
            ) : null}
          </div>
          <pre className="mt-4 max-h-[32rem] overflow-auto rounded-lg bg-muted p-4 text-xs leading-relaxed">
            {JSON.stringify(resposta.resultado, null, 2)}
          </pre>
        </article>
      ) : null}
    </section>
  );
}
