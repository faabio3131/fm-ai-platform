"use client";

import {
  ArrowUpRight,
  Bot,
  CheckCircle2,
  LoaderCircle,
  Megaphone,
  Mic,
  Send,
  Square,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { KordenaBrainMark } from "@/components/brand/KordenaBrainMark";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAuthStore } from "@/features/auth/store/auth-store";
import { availableShellModules } from "@/features/shell/module-registry";
import {
  confirmarGerenteIA,
  GerenteIAResponse,
  perguntarGerenteIA,
  transcreverGerenteIA,
} from "../services/gerente-ia-api";

function recordOf(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function campaignDraftOf(response: GerenteIAResponse | null) {
  const result = recordOf(response?.resultado);
  if (!result) return null;
  const campanhaId = result.rascunho_id;
  if (response?.tipo !== "RascunhoCampanha" || typeof campanhaId !== "string") return null;
  return campanhaId;
}

function previewOf(response: GerenteIAResponse | null) {
  const result = recordOf(response?.resultado);
  if (!result) return null;
  const previewId = result.preview_id;
  const fingerprint = result.fingerprint;
  if (typeof previewId !== "string" || typeof fingerprint !== "string") return null;
  return { previewId, fingerprint };
}

const BARRAS_VOZ = 22;

function formatarDuracaoVoz(segundos: number): string {
  const minutos = Math.floor(segundos / 60);
  const resto = segundos % 60;
  return `${String(minutos).padStart(2, "0")}:${String(resto).padStart(2, "0")}`;
}

const PERGUNTAS_RAPIDAS = [
  "Resuma a operação da unidade agora.",
  "Quais pedidos precisam de atenção neste momento?",
  "Como estão vendas e pagamentos no período disponível?",
  "Há estoque crítico ou validade exigindo atenção?",
  "Existe algum atendimento aguardando intervenção humana?",
] as const;

export function GerenteIAWorkspace() {
  const auth = useAuthStore();
  const modulosOperacionais = useMemo(
    () => availableShellModules(auth.permissions).filter((module) => module.group === "operacao"),
    [auth.permissions],
  );
  const [pergunta, setPergunta] = useState("");
  const [resposta, setResposta] = useState<GerenteIAResponse | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [gravando, setGravando] = useState(false);
  const [transcrevendo, setTranscrevendo] = useState(false);
  const [segundosGravacao, setSegundosGravacao] = useState(0);
  const [niveisVoz, setNiveisVoz] = useState<number[]>(
    () => Array.from({ length: BARRAS_VOZ }, () => 0.08),
  );
  const gravadorRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const partesRef = useRef<BlobPart[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceAudioRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const analisadorRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const preview = useMemo(() => previewOf(resposta), [resposta]);
  const campaignDraftId = useMemo(() => campaignDraftOf(resposta), [resposta]);
  const canOpenCampaigns = useMemo(
    () => availableShellModules(auth.permissions).some((module) => module.href === "/admin/campanhas"),
    [auth.permissions],
  );

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

  useEffect(() => {
    return () => {
      if (animationRef.current !== null) {
        cancelAnimationFrame(animationRef.current);
      }
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
      }
      const recorder = gravadorRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        recorder.stop();
      }
      streamRef.current?.getTracks().forEach((track) => track.stop());
      sourceAudioRef.current?.disconnect();
      analisadorRef.current?.disconnect();
      const audioContext = audioContextRef.current;
      if (audioContext && audioContext.state !== "closed") {
        void audioContext.close();
      }
    };
  }, []);

  function pararFeedbackVoz() {
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    sourceAudioRef.current?.disconnect();
    sourceAudioRef.current = null;
    analisadorRef.current?.disconnect();
    analisadorRef.current = null;
    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext && audioContext.state !== "closed") {
      void audioContext.close();
    }
  }

  async function iniciarFeedbackVoz(stream: MediaStream) {
    const AudioContextCtor =
      window.AudioContext ??
      (window as typeof window & { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!AudioContextCtor) return;

    const audioContext = new AudioContextCtor();
    audioContextRef.current = audioContext;
    if (audioContext.state === "suspended") {
      await audioContext.resume();
    }
    const source = audioContext.createMediaStreamSource(stream);
    const analisador = audioContext.createAnalyser();
    analisador.fftSize = 256;
    analisador.smoothingTimeConstant = 0.72;
    source.connect(analisador);
    sourceAudioRef.current = source;
    analisadorRef.current = analisador;

    const dados = new Uint8Array(analisador.frequencyBinCount);
    let ultimoFrame = 0;
    const desenhar = (timestamp: number) => {
      if (timestamp - ultimoFrame >= 55) {
        analisador.getByteFrequencyData(dados);
        const largura = Math.max(1, Math.floor(dados.length / BARRAS_VOZ));
        const proximos = Array.from({ length: BARRAS_VOZ }, (_, index) => {
          const inicio = index * largura;
          const fim = Math.min(dados.length, inicio + largura);
          let total = 0;
          for (let cursor = inicio; cursor < fim; cursor += 1) {
            total += dados[cursor] ?? 0;
          }
          const media = total / Math.max(1, fim - inicio);
          return Math.max(0.08, Math.min(1, media / 150));
        });
        setNiveisVoz(proximos);
        ultimoFrame = timestamp;
      }
      animationRef.current = requestAnimationFrame(desenhar);
    };
    animationRef.current = requestAnimationFrame(desenhar);
    setSegundosGravacao(0);
    timerRef.current = setInterval(
      () => setSegundosGravacao((atual) => atual + 1),
      1000,
    );
  }

  async function alternarVoz() {
    if (gravando) {
      const gravador = gravadorRef.current;
      if (gravador?.state === "recording") {
        try {
          gravador.requestData();
        } catch {
          // Alguns navegadores móveis não suportam requestData imediatamente.
        }
        gravador.stop();
      }
      return;
    }
    if (carregando || transcrevendo) return;
    setErro(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setErro("gerente_ia.microfone_nao_suportado");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const tipos = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
      ];
      const mimeType = tipos.find((tipo) => MediaRecorder.isTypeSupported(tipo));
      const gravador = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      partesRef.current = [];
      streamRef.current = stream;
      gravadorRef.current = gravador;
      await iniciarFeedbackVoz(stream);
      gravador.ondataavailable = (event) => {
        if (event.data.size > 0) partesRef.current.push(event.data);
      };
      gravador.onstop = () => {
        const tipo = gravador.mimeType || mimeType || "audio/webm";
        const blob = new Blob(partesRef.current, { type: tipo });
        pararFeedbackVoz();
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        gravadorRef.current = null;
        partesRef.current = [];
        setGravando(false);
        if (blob.size < 512) {
          setErro("gerente_ia.audio_sem_sinal");
          setSegundosGravacao(0);
          return;
        }
        setTranscrevendo(true);
        void transcreverGerenteIA(blob)
          .then((texto) => setPergunta(texto))
          .catch((error: unknown) => {
            setErro(error instanceof Error ? error.message : "gerente_ia.transcricao_falhou");
          })
          .finally(() => {
            setTranscrevendo(false);
            setSegundosGravacao(0);
          });
      };
      gravador.onerror = () => {
        pararFeedbackVoz();
        stream.getTracks().forEach((track) => track.stop());
        setGravando(false);
        setErro("gerente_ia.microfone_indisponivel");
      };
      gravador.start(250);
      setGravando(true);
    } catch (error) {
      pararFeedbackVoz();
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      gravadorRef.current = null;
      setGravando(false);
      setErro(
        error instanceof DOMException && error.name === "NotAllowedError"
          ? "gerente_ia.microfone_permissao_negada"
          : "gerente_ia.microfone_indisponivel",
      );
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
    <section className="kordena-page-dark min-h-full px-4 py-4 text-slate-100 sm:px-5 lg:px-6">
      <div className="kordena-enter mx-auto flex w-full max-w-6xl flex-col gap-3.5">
        <header className="relative overflow-hidden rounded-[1.5rem] border border-blue-400/15 bg-[linear-gradient(135deg,rgba(37,99,235,0.18),rgba(14,165,233,0.05)_45%,rgba(8,17,31,0.96))] p-4 shadow-[0_30px_70px_-42px_rgba(37,99,235,0.75)] sm:p-5">
          <div className="kordena-grid pointer-events-none absolute inset-0 opacity-60" />
          <div className="relative flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-blue-400/20 bg-blue-400/10 px-3 py-1.5 text-xs font-bold text-blue-200">
                <Sparkles className="size-3.5" />
                Cognição operacional governada
              </div>
              <div className="mt-3 flex items-center gap-3">
                <KordenaBrainMark className="size-12" priority />
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-300">
                    Kordena Cognitive Core
                  </p>
                  <h1 className="mt-0.5 text-2xl font-black tracking-[-0.035em] sm:text-3xl">Gerente IA</h1>
                </div>
              </div>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-300 sm:text-base">
                Centro operacional cognitivo do Kordena: consulte a operação, navegue pelos módulos autorizados, prepare decisões e confirme ações governadas sem sair do escopo da unidade ativa.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs sm:min-w-72">
              <div className="kordena-glass rounded-xl p-3">
                <ShieldCheck className="size-5 text-emerald-300" />
                <p className="mt-2 font-bold text-white">Autoridade preservada</p>
                <p className="mt-1 leading-5 text-slate-500">A IA recomenda; serviços autorizados executam.</p>
              </div>
              <div className="kordena-glass rounded-xl p-3">
                <Bot className="size-5 text-sky-300" />
                <p className="mt-2 font-bold text-white">Contexto operacional</p>
                <p className="mt-1 leading-5 text-slate-500">Resposta escopada à sessão e unidade ativa.</p>
              </div>
            </div>
          </div>
        </header>

        <section className="kordena-panel-dark rounded-[1.35rem] p-4 sm:p-4">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-300">Centro operacional cognitivo</p>
            <h2 className="mt-1 text-xl font-black text-white">Toda a operação ao alcance do Gerente IA</h2>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
              Acesse os módulos liberados para sua sessão. O Gerente IA não amplia autoridade: cada destino continua obedecendo RBAC, tenant e unidade.
            </p>
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {modulosOperacionais.map((module) => (
              <Link key={module.id} href={module.href} className="group flex items-start justify-between gap-3 rounded-2xl border border-white/[0.07] bg-white/[0.025] p-3 transition hover:border-sky-300/20 hover:bg-white/[0.04]">
                <span className="min-w-0">
                  <span className="block text-sm font-bold text-slate-100">{module.label}</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">{module.description}</span>
                </span>
                <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-slate-500 transition group-hover:text-sky-300" />
              </Link>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {PERGUNTAS_RAPIDAS.map((item) => (
              <button key={item} type="button" onClick={() => setPergunta(item)} className="rounded-full border border-blue-300/15 bg-blue-400/[0.06] px-3 py-1.5 text-xs font-semibold text-blue-100 transition hover:border-blue-300/30 hover:bg-blue-400/[0.1]">
                {item}
              </button>
            ))}
          </div>
        </section>

        <form onSubmit={perguntar} className="kordena-panel-dark rounded-[1.35rem] p-4 sm:p-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <label htmlFor="gerente-pergunta" className="text-sm font-bold text-white">
                Pergunte ao Gerente IA
              </label>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Faça perguntas sobre operação, financeiro, fiscal ou indicadores disponíveis no seu escopo.
              </p>
            </div>
            <span className="rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-1 text-[10px] font-bold text-slate-500">
              {pergunta.length}/4000
            </span>
          </div>
          <Textarea
            id="gerente-pergunta"
            value={pergunta}
            onChange={(event) => setPergunta(event.target.value)}
            rows={4}
            maxLength={4000}
            className="mt-3 min-h-24 resize-y border-slate-700 bg-slate-950/70 text-base leading-7 text-white placeholder:text-slate-600"
            placeholder="Ex.: quais pedidos estão atrasados agora?"
          />
          {gravando ? (
            <div
              className="mt-3 rounded-2xl border border-sky-400/25 bg-sky-400/[0.07] px-3 py-3"
              role="status"
              aria-live="polite"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="inline-flex items-center gap-2 text-xs font-black uppercase tracking-[0.14em] text-sky-200">
                  <span className="size-2 animate-pulse rounded-full bg-red-400 shadow-[0_0_0_4px_rgba(248,113,113,0.12)]" />
                  Gravando voz
                </span>
                <span className="font-mono text-xs font-bold text-slate-300">
                  {formatarDuracaoVoz(segundosGravacao)}
                </span>
              </div>
              <div
                className="mt-3 flex h-11 items-center justify-center gap-1 overflow-hidden rounded-xl border border-white/[0.06] bg-slate-950/55 px-2"
                aria-label="Nível do áudio captado pelo microfone"
              >
                {niveisVoz.map((nivel, index) => (
                  <span
                    key={index}
                    className="w-1.5 min-w-1 rounded-full bg-gradient-to-t from-blue-500 to-cyan-300 transition-[height] duration-75"
                    style={{ height: `${Math.max(4, nivel * 40)}px` }}
                  />
                ))}
              </div>
              <p className="mt-2 text-center text-xs text-slate-400">
                Estou ouvindo. Fale normalmente e toque em <strong className="text-slate-200">Parar</strong> para transcrever.
              </p>
            </div>
          ) : transcrevendo ? (
            <div className="mt-3 flex items-center gap-2 rounded-xl border border-blue-400/20 bg-blue-400/[0.06] px-3 py-2 text-xs font-semibold text-blue-100" role="status">
              <LoaderCircle className="size-4 animate-spin" />
              Processando o áudio e preparando a transcrição…
            </div>
          ) : null}
          <div className="mt-3 flex flex-col-reverse gap-2.5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-slate-500">
              {gravando
                ? "Gravando voz… clique em Parar quando terminar."
                : transcrevendo
                  ? "Transcrevendo sua pergunta com a rota de áudio governada."
                  : "Ações sensíveis continuam sujeitas a preview, confirmação e idempotência."}
            </p>
            <div className="grid w-full grid-cols-2 gap-2 sm:flex sm:w-auto sm:items-center">
              <Button
                type="button"
                size="lg"
                variant="outline"
                onClick={() => void alternarVoz()}
                disabled={carregando || transcrevendo}
                aria-pressed={gravando}
                aria-label={gravando ? "Parar gravação de voz" : "Falar com o Gerente IA"}
              >
                {transcrevendo ? (
                  <LoaderCircle className="animate-spin" />
                ) : gravando ? (
                  <Square />
                ) : (
                  <Mic />
                )}
                {transcrevendo ? "Transcrevendo..." : gravando ? "Parar" : "Falar"}
              </Button>
              <Button type="submit" size="lg" disabled={!pergunta.trim() || carregando || gravando || transcrevendo}>
                {carregando ? <LoaderCircle className="animate-spin" /> : <Send />}
                {carregando ? "Processando..." : "Enviar"}
              </Button>
            </div>
          </div>
        </form>

        {erro ? (
          <div role="alert" className="rounded-2xl border border-red-400/25 bg-red-500/10 p-4 text-sm text-red-100">
            {erro}
          </div>
        ) : null}

        {resposta ? (
          <article className="kordena-panel-dark rounded-[1.35rem] p-4 sm:p-4">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-start gap-3">
                <span className="flex size-10 items-center justify-center rounded-xl bg-emerald-400/10 text-emerald-300 ring-1 ring-emerald-400/15">
                  <CheckCircle2 className="size-5" />
                </span>
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">Resultado</p>
                  <h2 className="mt-1 text-lg font-bold text-white">{resposta.tipo}</h2>
                  {resposta.nome_assistente ? (
                    <p className="mt-1 text-sm text-slate-500">Identidade: {resposta.nome_assistente}</p>
                  ) : null}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {campaignDraftId && canOpenCampaigns ? (
                  <Button asChild variant="outline">
                    <Link href={`/admin/campanhas?campanha=${encodeURIComponent(campaignDraftId)}`}>
                      <Megaphone className="size-4" />
                      Abrir rascunho em Campanhas
                    </Link>
                  </Button>
                ) : null}
                {preview ? (
                  <Button type="button" onClick={confirmar} disabled={carregando}>
                    <ShieldCheck />
                    Confirmar ação governada
                  </Button>
                ) : null}
              </div>
            </div>
            <pre className="mt-5 max-h-[34rem] overflow-auto rounded-2xl border border-white/[0.07] bg-[#06101d] p-4 text-xs leading-6 text-slate-300 shadow-inner">
              {JSON.stringify(resposta.resultado, null, 2)}
            </pre>
          </article>
        ) : null}
      </div>
    </section>
  );
}
