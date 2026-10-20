"use client";

import {
  BadgeCheck,
  CheckCircle2,
  Clock3,
  History,
  LoaderCircle,
  Megaphone,
  RefreshCw,
  Rocket,
  Save,
  Send,
  ShieldCheck,
  Users,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import {
  aprovarCampanha,
  atualizarCampanha,
  CampanhasApiError,
  criarCampanha,
  definirAudiencia,
  despacharCampanha,
  listarAudiencia,
  listarCampanhas,
  listarHistorico,
  obterCampanha,
  publicarCampanha,
  submeterCampanha,
  type AudienciaCampanha,
  type CampanhaConteudo,
  type CampanhaWeb,
  type EventoCampanha,
} from "@/features/backoffice/campanhas/services/campanhas-api";

const NOVA_CAMPANHA: CampanhaConteudo = {
  canal: "whatsapp",
  finalidade: "promocoes",
  objetivo: "Reativação de clientes",
  texto_base: "",
  midia_url: null,
};

function statusLabel(status: string): string {
  return {
    rascunho: "Rascunho",
    aguardando_aprovacao: "Aguardando aprovação",
    aprovada: "Aprovada",
    publicavel: "Pronta para execução",
  }[status] ?? status;
}

function canalLabel(canal: string): string {
  return {
    whatsapp: "WhatsApp",
    facebook: "Facebook",
    instagram: "Instagram",
  }[canal] ?? canal;
}

function dataHora(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function mensagemErro(error: unknown): string {
  if (error instanceof CampanhasApiError) {
    if (error.status === 401) return "Sua sessão expirou.";
    if (error.status === 403) return "Seu perfil ou step-up não autoriza esta operação.";
    if (error.code === "campanha_audiencia_desatualizada") {
      return "A audiência mudou após a seleção. Revise os consentimentos antes de submeter.";
    }
    if (error.code === "campanha_audiencia_contem_cliente_inelegivel") {
      return "A seleção contém cliente sem consentimento vigente ou sem canal disponível.";
    }
    if (error.code === "fingerprint_divergente") {
      return "A campanha mudou desde a última revisão. Recarregue antes de aprovar.";
    }
    if (["configuracao_indisponivel", "integracao_desabilitada", "integracao_nao_homologada", "credencial_indisponivel", "finalidade_credencial_indisponivel"].includes(error.code)) {
      return "Este canal Meta ainda não está pronto. Configure e homologue a integração correspondente em Integrações.";
    }
    if (error.code === "campanha_instagram_midia_https_obrigatoria") {
      return "Instagram exige uma URL HTTPS de imagem para a publicação orgânica.";
    }
    if (error.code === "campanha_publicacao_externa_incerta") {
      return "A Meta recebeu uma tentativa cujo resultado ficou incerto. O Kordena bloqueou novo envio automático para evitar publicação duplicada.";
    }
    return `Operação recusada: ${error.code}.`;
  }
  return "Não foi possível concluir a operação de campanha.";
}

export function CampanhasWorkspace() {
  const [campanhas, setCampanhas] = useState<CampanhaWeb[]>([]);
  const [selecionada, setSelecionada] = useState<CampanhaWeb | null>(null);
  const [audiencia, setAudiencia] = useState<AudienciaCampanha[]>([]);
  const [historico, setHistorico] = useState<EventoCampanha[]>([]);
  const [conteudo, setConteudo] = useState<CampanhaConteudo>(NOVA_CAMPANHA);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const carregarDetalhe = useCallback(async (id: string) => {
    const [campanha, pessoas, eventos] = await Promise.all([
      obterCampanha(id),
      listarAudiencia(id),
      listarHistorico(id),
    ]);
    setSelecionada(campanha);
    setConteudo({
      canal: campanha.canal,
      finalidade: campanha.finalidade,
      objetivo: campanha.objetivo,
      texto_base: campanha.texto_base,
      midia_url: campanha.midia_url,
    });
    setAudiencia(pessoas);
    setSelecionados(new Set(pessoas.filter((item) => item.selecionado).map((item) => item.cliente_id)));
    setHistorico(eventos);
  }, []);

  const carregar = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const itens = await listarCampanhas();
      setCampanhas(itens);
      const params = new URL(window.location.href).searchParams;
      const solicitado = params.get("campanha");
      const alvo = solicitado && itens.some((item) => item.campanha_id === solicitado)
        ? solicitado
        : itens[0]?.campanha_id;
      if (alvo) await carregarDetalhe(alvo);
      else {
        setSelecionada(null);
        setAudiencia([]);
        setHistorico([]);
      }
    } catch (error) {
      setErro(mensagemErro(error));
    } finally {
      setLoading(false);
    }
  }, [carregarDetalhe]);

  useEffect(() => {
    const timer = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timer);
  }, [carregar]);

  const elegiveis = useMemo(() => audiencia.filter((item) => item.elegivel), [audiencia]);
  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of campanhas) counts.set(item.status, (counts.get(item.status) ?? 0) + 1);
    return counts;
  }, [campanhas]);

  async function executar(action: () => Promise<CampanhaWeb>, mensagem: string) {
    if (busy) return;
    setBusy(true);
    setErro(null);
    setAviso(null);
    try {
      const result = await action();
      setAviso(mensagem);
      const itens = await listarCampanhas();
      setCampanhas(itens);
      await carregarDetalhe(result.campanha_id);
    } catch (error) {
      setErro(mensagemErro(error));
    } finally {
      setBusy(false);
    }
  }

  async function criar(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await executar(
      () => criarCampanha(conteudo, `campaign-create-${crypto.randomUUID()}`),
      conteudo.canal === "whatsapp"
        ? "Rascunho criado. Defina a audiência antes de submeter."
        : "Rascunho orgânico criado. Revise o conteúdo antes de submeter.",
    );
  }

  async function salvarConteudo() {
    if (!selecionada) return;
    await executar(
      () => atualizarCampanha(
        selecionada.campanha_id,
        conteudo,
        `campaign-edit-${crypto.randomUUID()}`,
      ),
      "Rascunho atualizado.",
    );
  }

  async function salvarAudiencia() {
    if (!selecionada) return;
    await executar(
      () => definirAudiencia(
        selecionada.campanha_id,
        [...selecionados],
        `campaign-audience-${crypto.randomUUID()}`,
      ),
      "Audiência salva com consentimentos validados.",
    );
  }

  async function despachar() {
    if (!selecionada || busy) return;
    setBusy(true);
    setErro(null);
    setAviso(null);
    try {
      const result = await despacharCampanha(
        selecionada.campanha_id,
        selecionada.fingerprint,
        `campaign-dispatch-${crypto.randomUUID()}`,
      );
      setAviso(
        result.canal === "whatsapp"
          ? `Despacho processado: ${result.enviados} de ${result.total} destinatário(s) confirmado(s).`
          : `Publicação orgânica no ${result.canal === "facebook" ? "Facebook" : "Instagram"} confirmada pela Meta.`,
      );
      await carregarDetalhe(selecionada.campanha_id);
    } catch (error) {
      setErro(mensagemErro(error));
    } finally {
      setBusy(false);
    }
  }

  function alternarCliente(clienteId: string) {
    setSelecionados((current) => {
      const next = new Set(current);
      if (next.has(clienteId)) next.delete(clienteId);
      else next.add(clienteId);
      return next;
    });
  }

  return (
    <main className="kordena-page min-h-full px-4 py-4 text-slate-100 sm:px-5 lg:px-6">
      <div className="kordena-enter mx-auto w-full max-w-[1500px] space-y-4">
        <header className="relative overflow-hidden rounded-[1.5rem] border border-violet-400/15 bg-[linear-gradient(145deg,rgba(15,30,51,0.98),rgba(8,20,36,0.98))] p-4 shadow-[0_24px_60px_-40px_rgba(0,0,0,0.88)] sm:p-5">
          <div className="pointer-events-none absolute -right-20 -top-24 size-64 rounded-full bg-violet-500/10 blur-3xl" />
          <div className="relative flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-[11px] font-black uppercase tracking-[0.2em] text-violet-300">WP-017 · Marketing governado</p>
              <h1 className="mt-1.5 text-2xl font-black tracking-tight">Central de Campanhas</h1>
              <p className="mt-1 max-w-3xl text-[13px] leading-5 text-slate-400">
                Campanhas orgânicas para WhatsApp, Facebook e Instagram no mesmo fluxo de revisão, aprovação humana e execução governada.
              </p>
            </div>
            <Button variant="outline" onClick={() => void carregar()} disabled={loading || busy}>
              <RefreshCw className={loading ? "animate-spin" : ""} /> Atualizar
            </Button>
          </div>
        </header>

        <section className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
          <Metric icon={<Megaphone />} label="Campanhas" value={String(campanhas.length)} />
          <Metric icon={<Clock3 />} label="Rascunhos" value={String(statusCounts.get("rascunho") ?? 0)} />
          <Metric icon={<ShieldCheck />} label="Aguardando aprovação" value={String(statusCounts.get("aguardando_aprovacao") ?? 0)} />
          <Metric icon={<Rocket />} label="Prontas para execução" value={String(statusCounts.get("publicavel") ?? 0)} />
        </section>

        {erro ? <Feedback tone="error">{erro}</Feedback> : null}
        {aviso ? <Feedback tone="success">{aviso}</Feedback> : null}

        <section className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="space-y-3">
            <form onSubmit={(event) => void criar(event)} className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-3">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-violet-300">Nova campanha</p>
              <h2 className="mt-2 text-lg font-black">Criar rascunho</h2>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Criar nunca envia. WhatsApp usa audiência CRM; Facebook e Instagram publicam organicamente somente após aprovação.
              </p>
              <CampaignFields value={conteudo} onChange={setConteudo} />
              <Button type="submit" className="mt-4 w-full" disabled={busy || !conteudo.texto_base.trim() || (conteudo.canal === "instagram" && !conteudo.midia_url?.trim())}>
                <Megaphone /> Criar rascunho
              </Button>
            </form>

            <div className="overflow-hidden rounded-3xl border border-slate-700/60 bg-slate-900/70">
              <div className="border-b border-slate-800 px-4 py-3">
                <h2 className="font-bold">Campanhas da unidade</h2>
              </div>
              {loading ? (
                <div className="flex min-h-32 items-center justify-center gap-2 text-sm text-slate-400">
                  <LoaderCircle className="size-4 animate-spin" /> Carregando…
                </div>
              ) : campanhas.length === 0 ? (
                <p className="p-5 text-sm text-slate-500">Nenhuma campanha criada.</p>
              ) : (
                <div className="max-h-[460px] divide-y divide-slate-800 overflow-y-auto">
                  {campanhas.map((item) => (
                    <button
                      key={item.campanha_id}
                      type="button"
                      onClick={() => void carregarDetalhe(item.campanha_id)}
                      className={`w-full p-3 text-left transition ${selecionada?.campanha_id === item.campanha_id ? "bg-violet-400/[0.08]" : "hover:bg-white/[0.03]"}`}
                    >
                      <p className="truncate text-sm font-bold text-white">{item.objetivo}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {statusLabel(item.status)} · {canalLabel(item.canal)}{item.canal === "whatsapp" ? ` · ${item.audiencia_elegivel} pessoa(s)` : " · orgânico"}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </aside>

          {!selecionada ? (
            <div className="flex min-h-[360px] items-center justify-center rounded-2xl border border-dashed border-slate-700 bg-slate-900/35 p-6 text-center text-sm text-slate-500">
              Selecione uma campanha ou crie o primeiro rascunho.
            </div>
          ) : (
            <div className="space-y-3">
              <section className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p className="text-xs font-black uppercase tracking-[0.16em] text-sky-300">Lifecycle governado</p>
                    <h2 className="mt-2 text-2xl font-black">{selecionada.objetivo}</h2>
                    <p className="mt-1 text-sm text-slate-500">{statusLabel(selecionada.status)} · criada em {dataHora(selecionada.criado_em)}</p>
                  </div>
                  <span className="rounded-full border border-violet-300/15 bg-violet-400/[0.08] px-3 py-1.5 text-xs font-bold text-violet-200">
                    {statusLabel(selecionada.status)}
                  </span>
                </div>

                {selecionada.status === "rascunho" ? (
                  <>
                    <CampaignFields value={conteudo} onChange={setConteudo} />
                    <Button variant="outline" className="mt-4" onClick={() => void salvarConteudo()} disabled={busy || !conteudo.texto_base.trim() || (conteudo.canal === "instagram" && !conteudo.midia_url?.trim())}>
                      <Save /> Salvar conteúdo
                    </Button>
                  </>
                ) : (
                  <div className="mt-5 rounded-2xl border border-slate-800 bg-slate-950/50 p-4">
                    <p className="text-sm leading-6 text-slate-300">{selecionada.texto_base}</p>
                  </div>
                )}
              </section>

              {selecionada.canal === "whatsapp" ? (
                <section className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <p className="text-xs font-black uppercase tracking-[0.16em] text-sky-300">Audiência e consentimento</p>
                      <h2 className="mt-2 text-xl font-black">Destinatários elegíveis</h2>
                      <p className="mt-1 text-sm text-slate-500">
                        {elegiveis.length} elegível(is) agora · {selecionados.size} selecionado(s).
                      </p>
                    </div>
                    {selecionada.status === "rascunho" ? (
                      <Button variant="outline" onClick={() => void salvarAudiencia()} disabled={busy || selecionados.size === 0}>
                        <Users /> Salvar audiência
                      </Button>
                    ) : null}
                  </div>
                  <div className="mt-4 grid gap-2 md:grid-cols-2">
                    {audiencia.length === 0 ? (
                      <p className="text-sm text-slate-500">Nenhum cliente CRM disponível.</p>
                    ) : audiencia.map((item) => (
                      <label key={item.cliente_id} className={`flex items-start gap-3 rounded-2xl border p-3 ${item.elegivel ? "border-slate-700/60 bg-slate-950/45" : "border-amber-400/10 bg-amber-400/[0.03]"}`}>
                        <input
                          type="checkbox"
                          checked={selecionados.has(item.cliente_id)}
                          disabled={selecionada.status !== "rascunho" || !item.elegivel}
                          onChange={() => alternarCliente(item.cliente_id)}
                          className="mt-1"
                        />
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-semibold text-white">{item.nome}</span>
                          <span className="mt-1 block text-xs text-slate-500">
                            {item.elegivel ? "Consentimento vigente" : `Indisponível · ${item.consentimento}`}
                          </span>
                        </span>
                      </label>
                    ))}
                  </div>
                </section>
              ) : (
                <section className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4">
                  <p className="text-xs font-black uppercase tracking-[0.16em] text-sky-300">Publicação orgânica</p>
                  <h2 className="mt-2 text-xl font-black">{canalLabel(selecionada.canal)}</h2>
                  <p className="mt-1 text-sm leading-6 text-slate-500">
                    Esta campanha publica organicamente na conta configurada em Integrações. Não usa audiência CRM, orçamento de mídia ou tráfego pago.
                  </p>
                  {selecionada.canal === "instagram" && selecionada.midia_url ? (
                    <p className="mt-3 truncate rounded-xl border border-slate-800 bg-slate-950/45 px-3 py-2 text-xs text-slate-400">
                      Mídia aprovada: {selecionada.midia_url}
                    </p>
                  ) : null}
                </section>
              )}

              <section className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4">
                <p className="text-xs font-black uppercase tracking-[0.16em] text-emerald-300">Aprovação e execução</p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <ActionCard
                    title="Submeter"
                    detail="Congela o rascunho para revisão humana."
                    enabled={selecionada.status === "rascunho" && (selecionada.canal !== "whatsapp" || selecionados.size > 0)}
                    busy={busy}
                    onClick={() => void executar(
                      () => submeterCampanha(selecionada.campanha_id, `campaign-submit-${crypto.randomUUID()}`),
                      "Campanha submetida para aprovação.",
                    )}
                    icon={<Clock3 />}
                  />
                  <ActionCard
                    title="Aprovar"
                    detail="Exige autorização humana e step-up ativo."
                    enabled={selecionada.status === "aguardando_aprovacao"}
                    busy={busy}
                    onClick={() => void executar(
                      () => aprovarCampanha(selecionada.campanha_id, selecionada.fingerprint, `campaign-approve-${crypto.randomUUID()}`),
                      "Campanha aprovada por identidade humana.",
                    )}
                    icon={<BadgeCheck />}
                  />
                  <ActionCard
                    title="Preparar publicação"
                    detail="Gera a referência publicável sem executar o efeito externo."
                    enabled={selecionada.status === "aprovada"}
                    busy={busy}
                    onClick={() => void executar(
                      () => publicarCampanha(selecionada.campanha_id, selecionada.fingerprint, `campaign-publish-${crypto.randomUUID()}`),
                      "Campanha tornou-se publicável. Nenhum efeito externo foi executado automaticamente.",
                    )}
                    icon={<Rocket />}
                  />
                  <ActionCard
                    title={selecionada.canal === "whatsapp" ? "Despachar" : "Publicar agora"}
                    detail={selecionada.canal === "whatsapp" ? "Revalida consentimento e usa Outbox at-most-once." : "Publica organicamente na Meta com proteção at-most-once."}
                    enabled={selecionada.status === "publicavel"}
                    busy={busy}
                    onClick={() => void despachar()}
                    icon={<Send />}
                  />
                </div>
                <p className="mt-4 rounded-2xl border border-amber-400/15 bg-amber-400/[0.04] p-3 text-xs leading-5 text-slate-400">
                  Canais Meta permanecem fail-closed: sem configuração e homologação válidas, o Kordena não envia nem publica e explica o bloqueio. A V1 não executa mídia paga.
                </p>
              </section>

              <section className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4">
                <div className="flex items-center gap-2">
                  <History className="size-5 text-sky-300" />
                  <h2 className="text-lg font-black">Histórico auditável</h2>
                </div>
                {historico.length === 0 ? (
                  <p className="mt-4 text-sm text-slate-500">Nenhuma transição registrada.</p>
                ) : (
                  <div className="mt-4 space-y-2">
                    {[...historico].reverse().map((evento) => (
                      <div key={evento.event_id} className="rounded-2xl border border-slate-800 bg-slate-950/45 p-3">
                        <div className="flex items-center justify-between gap-3">
                          <p className="text-sm font-bold text-white">{evento.event_type}</p>
                          <p className="text-xs text-slate-500">{dataHora(evento.ocorrido_em)}</p>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">Evento {evento.event_id}</p>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function CampaignFields({
  value,
  onChange,
}: {
  value: CampanhaConteudo;
  onChange: (next: CampanhaConteudo) => void;
}) {
  return (
    <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
      <label className="text-xs font-semibold text-slate-400">
        Canal
        <select
          value={value.canal}
          onChange={(event) => {
            const canal = event.target.value;
            onChange({
              ...value,
              canal,
              midia_url: canal === "instagram" ? (value.midia_url ?? "") : null,
            });
          }}
          className="mt-1 h-9 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white"
        >
          <option value="whatsapp">WhatsApp</option>
          <option value="facebook">Facebook</option>
          <option value="instagram">Instagram</option>
        </select>
      </label>
      <label className="text-xs font-semibold text-slate-400">
        Finalidade
        <select
          value={value.finalidade}
          onChange={(event) => onChange({ ...value, finalidade: event.target.value })}
          className="mt-1 h-9 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white"
        >
          <option value="promocoes">Promoções</option>
        </select>
      </label>
      <label className="text-xs font-semibold text-slate-400 sm:col-span-2">
        Objetivo
        <input
          value={value.objetivo}
          onChange={(event) => onChange({ ...value, objetivo: event.target.value })}
          maxLength={240}
          required
          className="mt-1 h-9 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white"
        />
      </label>
      <label className="text-xs font-semibold text-slate-400 sm:col-span-2">
        {value.canal === "instagram" ? "Legenda" : "Mensagem"}
        <textarea
          value={value.texto_base}
          onChange={(event) => onChange({ ...value, texto_base: event.target.value })}
          maxLength={2000}
          rows={4}
          required
          className="mt-1 w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm leading-6 text-white"
          placeholder={value.canal === "instagram" ? "Escreva a legenda da publicação." : "Escreva ou cole a mensagem da campanha."}
        />
      </label>
      {value.canal === "instagram" ? (
        <label className="text-xs font-semibold text-slate-400 sm:col-span-2">
          URL HTTPS da imagem
          <input
            type="url"
            value={value.midia_url ?? ""}
            onChange={(event) => onChange({ ...value, midia_url: event.target.value })}
            maxLength={2048}
            required
            placeholder="https://..."
            className="mt-1 h-9 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-white"
          />
          <span className="mt-1 block text-[11px] font-normal leading-4 text-slate-500">
            A imagem faz parte do conteúdo aprovado e será publicada organicamente no Instagram Business.
          </span>
        </label>
      ) : null}
    </div>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-700/60 bg-slate-900/70 p-4">
      <span className="text-violet-300">{icon}</span>
      <p className="mt-2 text-[10px] font-bold uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-black text-white">{value}</p>
    </div>
  );
}

function ActionCard({
  title,
  detail,
  icon,
  enabled,
  busy,
  onClick,
}: {
  title: string;
  detail: string;
  icon: ReactNode;
  enabled: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={!enabled || busy}
      onClick={onClick}
      className="rounded-xl border border-slate-700/60 bg-slate-950/45 p-3 text-left transition enabled:hover:border-violet-400/25 enabled:hover:bg-violet-400/[0.05] disabled:opacity-45"
    >
      <span className="text-violet-300">{busy && enabled ? <LoaderCircle className="animate-spin" /> : icon}</span>
      <span className="mt-3 block text-sm font-black text-white">{title}</span>
      <span className="mt-1 block text-xs leading-5 text-slate-500">{detail}</span>
    </button>
  );
}

function Feedback({
  tone,
  children,
}: {
  tone: "error" | "success";
  children: string;
}) {
  return (
    <div
      role="status"
      className={`rounded-2xl border p-4 text-sm ${tone === "error" ? "border-red-400/20 bg-red-400/[0.08] text-red-100" : "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-100"}`}
    >
      {tone === "success" ? <CheckCircle2 className="mr-2 inline size-4" /> : null}
      {children}
    </div>
  );
}
