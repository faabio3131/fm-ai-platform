'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Bot,
  Boxes,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Headphones,
  MapPinned,
  MessageCircle,
  PackageCheck,
  Search,
  ShieldCheck,
  ShoppingBag,
  Truck,
  UserRoundCheck,
  Users,
  WalletCards,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { ESTADO_COLORS, ESTADO_LABELS } from '../constants';
import {
  configurarIdentidade,
  ConversaDetalhe,
  ConversaResumo,
  forcarHandoff,
  IdentidadeAssistente,
  IdentidadeAssistentePutRequest,
  listarConversas,
  obterConversa,
  obterIdentidade,
} from '../services/assistente-atendimento-api';

interface IdentidadeDialogProps {
  identidade: IdentidadeAssistente;
  onSave: (identidade: IdentidadeAssistente) => void;
}

type FiltroFila = 'todas' | 'atencao' | 'pedido' | 'checkout' | 'handoff';

const CAPACIDADES = [
  {
    titulo: 'WhatsApp multimodal',
    descricao: 'Recebe texto e áudio, mantém contexto multi-turno e responde pelo canal.',
    detalhe: 'Depende de Meta/WhatsApp homologado',
    icon: MessageCircle,
    externa: true,
  },
  {
    titulo: 'Core de IA',
    descricao: 'Interpreta intenção e transcreve áudio pelo AI Model Router do Kordena.',
    detalhe: 'Capability nativa do Core',
    icon: BrainCircuit,
    externa: false,
  },
  {
    titulo: 'Cliente e CRM',
    descricao: 'Identifica cliente, registra contexto autorizado e recupera histórico permitido.',
    detalhe: 'Contexto governado por tenant/unidade',
    icon: Users,
    externa: false,
  },
  {
    titulo: 'Catálogo real',
    descricao: 'Usa produto, preço e disponibilidade da unidade sem inventar oferta.',
    detalhe: 'Fonte canônica do Kordena',
    icon: ShoppingBag,
    externa: false,
  },
  {
    titulo: 'Pedidos e checkout',
    descricao: 'Monta carrinho, confirma pedido e entra no checkout canônico da plataforma.',
    detalhe: 'Pedido V1 + idempotência',
    icon: PackageCheck,
    externa: false,
  },
  {
    titulo: 'Pagamentos',
    descricao: 'Coleta forma de pagamento e acompanha estado financeiro sem autoconfirmar cobrança.',
    detalhe: 'Autoridade no domínio de pagamentos',
    icon: WalletCards,
    externa: false,
  },
  {
    titulo: 'Entrega inteligente',
    descricao: 'Valida endereço, rota, ETA, área, taxa e SLA usando a política real de delivery.',
    detalhe: 'Google Maps quando homologado',
    icon: MapPinned,
    externa: true,
  },
  {
    titulo: 'Estoque',
    descricao: 'Reserva estoque pelo checkout autoritativo e respeita disponibilidade operacional.',
    detalhe: 'Sem estoque paralelo da IA',
    icon: Boxes,
    externa: false,
  },
  {
    titulo: 'Handoff humano',
    descricao: 'Pausa a automação, preserva contexto e transfere a conversa para uma pessoa.',
    detalhe: 'Fail-safe auditável',
    icon: Headphones,
    externa: false,
  },
];

const ESTADOS_ATENCAO = new Set([
  'aguardando_dados_cliente',
  'aguardando_modalidade_entrega',
  'aguardando_endereco_entrega',
  'aguardando_forma_pagamento',
  'aguardando_confirmacao_cliente',
  'handoff_humano',
]);

function formatarAtualizacao(valor: string): string {
  const data = new Date(valor);
  if (Number.isNaN(data.getTime())) return 'Atualização indisponível';
  return new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(data);
}

function IdentidadeDialog({ identidade, onSave }: IdentidadeDialogProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [formData, setFormData] = useState<{
    nome_publico: string;
    atributos: Record<string, unknown>;
  }>({
    nome_publico: identidade.nome_publico,
    atributos: identidade.atributos || {},
  });
  const [versao, setVersao] = useState(identidade.versao);

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const payload: IdentidadeAssistentePutRequest = {
        nome_publico: formData.nome_publico,
        atributos: formData.atributos,
        versao_esperada: versao,
      };
      const resultado = await configurarIdentidade(payload);
      setVersao(resultado.versao);
      setFormData({
        nome_publico: resultado.nome_publico,
        atributos: resultado.atributos || {},
      });
      onSave(resultado);
      setIsOpen(false);
    } catch (err: unknown) {
      const mensagem = err instanceof Error ? err.message : 'Erro ao salvar identidade';
      setError(mensagem);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="max-w-2xl border-sky-300/10 bg-[#071321] text-slate-100">
        <DialogHeader>
          <DialogTitle className="text-lg">Configuração administrativa da Atendente IA</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 p-6">
          <div>
            <Label htmlFor="nome_publico">Nome público da Atendente</Label>
            <Input
              id="nome_publico"
              value={formData.nome_publico}
              onChange={(event) =>
                setFormData((prev) => ({ ...prev, nome_publico: event.target.value }))
              }
              placeholder="Ex.: Ana, Lia, Sofia..."
              maxLength={80}
              className="mt-2 border-sky-300/10 bg-white/[0.04]"
            />
            <p className="mt-2 text-xs leading-5 text-slate-400">
              Nome apresentado ao cliente. A identidade é configurável por tenant e unidade.
            </p>
          </div>
          <div>
            <Label htmlFor="atributos">Atributos adicionais (JSON)</Label>
            <textarea
              id="atributos"
              value={JSON.stringify(formData.atributos, null, 2)}
              onChange={(event) => {
                try {
                  setFormData((prev) => ({
                    ...prev,
                    atributos: JSON.parse(event.target.value) || {},
                  }));
                  setError('');
                } catch {
                  setError('JSON inválido');
                }
              }}
              className="mt-2 flex min-h-[120px] w-full rounded-xl border border-sky-300/10 bg-white/[0.04] px-3 py-2 font-mono text-xs text-slate-200 outline-none focus:border-sky-400/30"
              placeholder='{"tom": "acolhedor"}'
            />
            {error ? <p className="mt-2 text-sm text-red-300">{error}</p> : null}
          </div>
          <div className="flex gap-3 border-t border-white/[0.06] pt-4">
            <Button onClick={handleSave} disabled={saving} className="flex-1">
              {saving ? 'Salvando...' : 'Salvar configuração'}
            </Button>
            <Button variant="outline" onClick={() => setIsOpen(false)} disabled={saving}>
              Cancelar
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface ConversaDetailDialogProps {
  conversa: ConversaResumo;
}

function ConversaDetailDialog({ conversa }: ConversaDetailDialogProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detalhe, setDetalhe] = useState<ConversaDetalhe | null>(null);
  const [handoffLoading, setHandoffLoading] = useState(false);
  const [handoffError, setHandoffError] = useState('');
  const [handoffMotivo, setHandoffMotivo] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const data = await obterConversa(conversa.conversa_id);
        if (!cancelled) setDetalhe(data);
      } catch (err: unknown) {
        if (!cancelled) {
          const mensagem = err instanceof Error ? err.message : 'Erro ao carregar conversa';
          setError(mensagem);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [conversa.conversa_id]);

  const handleHandoff = async () => {
    if (!handoffMotivo.trim()) {
      setHandoffError('Informe o motivo do handoff');
      return;
    }
    setHandoffLoading(true);
    setHandoffError('');
    try {
      await forcarHandoff(conversa.conversa_id, handoffMotivo);
      setIsOpen(false);
    } catch (err: unknown) {
      const mensagem = err instanceof Error ? err.message : 'Erro ao forçar handoff';
      setHandoffError(mensagem);
    } finally {
      setHandoffLoading(false);
    }
  };

  if (!isOpen) return null;

  const estadoLabel = ESTADO_LABELS[conversa.estado] || conversa.estado;
  const estadoColor =
    ESTADO_COLORS[conversa.estado] || 'border-slate-600 bg-slate-700/30 text-slate-300';

  function renderContent() {
    if (error) {
      return (
        <div className="rounded-xl border border-red-400/20 bg-red-400/[0.08] p-3 text-sm text-red-200">
          {error}
        </div>
      );
    }
    if (loading) {
      return (
        <div className="flex justify-center py-8">
          <div className="size-6 animate-spin rounded-full border-2 border-sky-300/20 border-b-sky-300" />
        </div>
      );
    }
    if (!detalhe) return null;

    return (
      <div className="space-y-5">
        <div className="grid gap-3 md:grid-cols-2">
          {[
            ['Conversa', detalhe.conversa_id],
            ['Pedido', detalhe.pedido_id],
            ['Pagamento', detalhe.pagamento_id],
            ['Entrega', detalhe.entrega_id],
            ['Último inbound', detalhe.ultimo_inbound_id],
            ['Último outbound', detalhe.ultimo_outbound_id],
          ].map(([label, value]) =>
            value ? (
              <div key={label} className="rounded-xl border border-white/[0.06] bg-white/[0.03] p-3">
                <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
                  {label}
                </p>
                <p className="mt-1 break-all font-mono text-xs text-slate-300">{value}</p>
              </div>
            ) : null,
          )}
        </div>

        {detalhe.handoff_contexto && Object.keys(detalhe.handoff_contexto).length > 0 ? (
          <div className="rounded-xl border border-amber-400/15 bg-amber-400/[0.06] p-4">
            <p className="text-xs font-bold text-amber-200">Contexto preservado para o humano</p>
            <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-slate-300">
              {JSON.stringify(detalhe.handoff_contexto, null, 2)}
            </pre>
          </div>
        ) : null}

        <div className="space-y-3 border-t border-white/[0.06] pt-4">
          <div>
            <p className="text-sm font-bold text-slate-100">Transferir para atendimento humano</p>
            <p className="mt-1 text-xs leading-5 text-slate-400">
              A automação será pausada e o contexto da conversa será preservado para continuidade.
            </p>
          </div>
          <Input
            value={handoffMotivo}
            onChange={(event) => {
              setHandoffMotivo(event.target.value);
              setHandoffError('');
            }}
            placeholder="Motivo do handoff"
            disabled={handoffLoading}
            className="border-sky-300/10 bg-white/[0.04]"
          />
          {handoffError ? <p className="text-sm text-red-300">{handoffError}</p> : null}
          <div className="flex gap-3">
            <Button
              onClick={handleHandoff}
              disabled={handoffLoading || !handoffMotivo.trim()}
              variant="destructive"
              className="flex-1"
            >
              {handoffLoading ? 'Encaminhando...' : 'Fazer handoff humano'}
            </Button>
            <Button variant="outline" onClick={() => setIsOpen(false)} disabled={handoffLoading}>
              Cancelar
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto border-sky-300/10 bg-[#071321] text-slate-100">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            Atendimento {conversa.conversa_id.slice(0, 8)}…
            <Badge className={estadoColor}>{estadoLabel}</Badge>
          </DialogTitle>
        </DialogHeader>
        <div className="p-6">{renderContent()}</div>
      </DialogContent>
    </Dialog>
  );
}

export function AssistenteAtendimentoWorkspace() {
  const pathname = usePathname();
  const adminSurface = pathname.startsWith('/admin/');
  const [identidade, setIdentidade] = useState<IdentidadeAssistente | null>(null);
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [loadingIdentidade, setLoadingIdentidade] = useState(true);
  const [loadingConversas, setLoadingConversas] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<FiltroFila>('todas');
  const [busca, setBusca] = useState('');

  useEffect(() => {
    let cancelled = false;
    async function loadIdentidade() {
      setLoadingIdentidade(true);
      try {
        const data = await obterIdentidade();
        if (!cancelled) setIdentidade(data);
      } catch (err: unknown) {
        if (!cancelled) {
          const mensagem = err instanceof Error ? err.message : 'Erro ao carregar identidade';
          setError(mensagem);
        }
      } finally {
        if (!cancelled) setLoadingIdentidade(false);
      }
    }
    void loadIdentidade();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function loadConversas() {
      setLoadingConversas(true);
      try {
        const response = await listarConversas();
        if (!cancelled) setConversas(response.conversas);
      } catch (err: unknown) {
        if (!cancelled) {
          const mensagem = err instanceof Error ? err.message : 'Erro ao carregar conversas';
          setError(mensagem);
        }
      } finally {
        if (!cancelled) setLoadingConversas(false);
      }
    }
    void loadConversas();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSaveIdentidade = useCallback((novaIdentidade: IdentidadeAssistente) => {
    setIdentidade(novaIdentidade);
  }, []);

  const metricas = useMemo(() => {
    const comPedido = conversas.filter((item) => Boolean(item.pedido_id)).length;
    const comPagamento = conversas.filter((item) => Boolean(item.pagamento_id)).length;
    const comEntrega = conversas.filter((item) => Boolean(item.entrega_id)).length;
    const handoffs = conversas.filter((item) => item.estado === 'handoff_humano').length;
    const aguardandoConfirmacao = conversas.filter(
      (item) => item.estado === 'aguardando_confirmacao_cliente',
    ).length;
    const checkout = conversas.filter((item) => item.estado === 'checkout_registrado').length;

    return {
      total: conversas.length,
      comPedido,
      comPagamento,
      comEntrega,
      handoffs,
      aguardandoConfirmacao,
      checkout,
    };
  }, [conversas]);

  const conversasFiltradas = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    return conversas.filter((item) => {
      const passaFiltro =
        filtro === 'todas' ||
        (filtro === 'atencao' && ESTADOS_ATENCAO.has(item.estado)) ||
        (filtro === 'pedido' && Boolean(item.pedido_id)) ||
        (filtro === 'checkout' && item.estado === 'checkout_registrado') ||
        (filtro === 'handoff' && item.estado === 'handoff_humano');

      if (!passaFiltro) return false;
      if (!termo) return true;

      return [item.conversa_id, item.pedido_id, item.pagamento_id, item.entrega_id, item.estado]
        .filter(Boolean)
        .some((valor) => String(valor).toLowerCase().includes(termo));
    });
  }, [busca, conversas, filtro]);

  const funil = [
    {
      label: 'Atendimentos',
      valor: metricas.total,
      descricao: 'conversas carregadas',
      icon: MessageCircle,
    },
    {
      label: 'Com pedido',
      valor: metricas.comPedido,
      descricao: 'pedido já associado',
      icon: ShoppingBag,
    },
    {
      label: 'Com pagamento',
      valor: metricas.comPagamento,
      descricao: 'pagamento associado',
      icon: CircleDollarSign,
    },
    {
      label: 'Com entrega',
      valor: metricas.comEntrega,
      descricao: 'entrega associada',
      icon: Truck,
    },
  ];

  return (
    <div className="min-h-full bg-[#06101d] px-4 py-5 text-slate-100 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1600px] space-y-6">
        <section className="relative overflow-hidden rounded-[28px] border border-sky-300/[0.09] bg-[radial-gradient(circle_at_15%_10%,rgba(37,99,235,0.22),transparent_32%),linear-gradient(135deg,rgba(8,24,42,0.98),rgba(5,14,26,0.98))] p-6 shadow-[0_28px_80px_-48px_rgba(0,0,0,0.95)] lg:p-8">
          <div className="absolute right-[-80px] top-[-90px] size-72 rounded-full bg-cyan-400/[0.05] blur-3xl" />
          <div className="relative grid gap-6 xl:grid-cols-[1.3fr_0.7fr] xl:items-end">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="border border-cyan-300/20 bg-cyan-300/[0.08] text-cyan-200">
                  <Bot className="mr-1.5 size-3.5" />
                  Agente operacional e comercial
                </Badge>
                <Badge className="border border-emerald-300/15 bg-emerald-300/[0.07] text-emerald-200">
                  <ShieldCheck className="mr-1.5 size-3.5" />
                  Governado pelo Core
                </Badge>
              </div>
              <h1 className="mt-5 text-3xl font-black tracking-tight text-white sm:text-4xl">
                Central de Atendimento IA
              </h1>
              <p className="mt-3 text-base font-semibold text-sky-100 sm:text-lg">
                Agente operacional e comercial conectado ao Kordena
              </p>
              <p className="mt-2 max-w-3xl text-sm leading-7 text-slate-300 sm:text-base">
                Atendimento inteligente conectado ao fluxo real do Kordena: cliente, catálogo,
                pedido, estoque, pagamento, produção e entrega, com handoff humano quando a
                automação precisa devolver o controle à equipe.
              </p>
              <div className="mt-5 flex flex-wrap gap-2 text-xs text-slate-300">
                {['WhatsApp', 'Texto e áudio', 'Core IA', 'CRM', 'Pedidos', 'Pagamentos', 'Delivery'].map(
                  (item) => (
                    <span
                      key={item}
                      className="rounded-full border border-white/[0.07] bg-white/[0.035] px-3 py-1.5"
                    >
                      {item}
                    </span>
                  ),
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-white/[0.07] bg-black/15 p-4 backdrop-blur">
              <p className="text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
                Identidade pública
              </p>
              <div className="mt-3 flex items-center gap-3">
                <span className="flex size-11 items-center justify-center rounded-2xl border border-sky-300/15 bg-sky-400/[0.08]">
                  <UserRoundCheck className="size-5 text-sky-300" />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-lg font-black text-white">
                    {loadingIdentidade
                      ? 'Carregando…'
                      : identidade?.nome_publico || 'Atendente não configurada'}
                  </p>
                  <p className="text-xs text-slate-400">Nome apresentado ao cliente</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {error ? (
          <div className="flex items-start gap-3 rounded-2xl border border-red-400/20 bg-red-400/[0.07] p-4 text-red-200">
            <AlertTriangle className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="text-sm font-bold">Há uma indisponibilidade na leitura operacional</p>
              <p className="mt-1 text-sm text-red-200/80">{error}</p>
            </div>
          </div>
        ) : null}

        <section>
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.2em] text-cyan-300">
                Pulso operacional
              </p>
              <h2 className="mt-1 text-2xl font-black text-white">Fila e conversão em tempo de operação</h2>
              <p className="mt-1 text-sm text-slate-400">
                Indicadores calculados somente a partir das conversas atualmente carregadas pela API.
              </p>
            </div>
            <Badge className="w-fit border border-white/[0.08] bg-white/[0.04] text-slate-300">
              <Activity className="mr-1.5 size-3.5" />
              Snapshot atual
            </Badge>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {funil.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.label}
                  className="rounded-2xl border border-sky-300/[0.08] bg-[linear-gradient(145deg,rgba(13,31,53,0.86),rgba(7,20,35,0.9))] p-4 shadow-[inset_0_1px_rgba(255,255,255,0.025)]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold text-slate-400">{item.label}</p>
                      <p className="mt-2 text-3xl font-black tabular-nums text-white">
                        {loadingConversas ? '—' : item.valor}
                      </p>
                    </div>
                    <span className="flex size-10 items-center justify-center rounded-xl border border-sky-300/10 bg-sky-400/[0.07]">
                      <Icon className="size-5 text-sky-300" />
                    </span>
                  </div>
                  <p className="mt-3 text-xs text-slate-500">{item.descricao}</p>
                </div>
              );
            })}
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <div className="rounded-2xl border border-amber-400/15 bg-amber-400/[0.055] p-4">
              <p className="text-xs font-bold text-amber-200">Aguardando confirmação</p>
              <p className="mt-2 text-2xl font-black tabular-nums text-white">
                {loadingConversas ? '—' : metricas.aguardandoConfirmacao}
              </p>
              <p className="mt-1 text-xs text-slate-400">clientes na etapa anterior ao checkout</p>
            </div>
            <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.055] p-4">
              <p className="text-xs font-bold text-emerald-200">Checkout registrado</p>
              <p className="mt-2 text-2xl font-black tabular-nums text-white">
                {loadingConversas ? '—' : metricas.checkout}
              </p>
              <p className="mt-1 text-xs text-slate-400">conversas com fluxo comercial concluído</p>
            </div>
            <div className="rounded-2xl border border-red-400/15 bg-red-400/[0.055] p-4">
              <p className="text-xs font-bold text-red-200">Handoff humano</p>
              <p className="mt-2 text-2xl font-black tabular-nums text-white">
                {loadingConversas ? '—' : metricas.handoffs}
              </p>
              <p className="mt-1 text-xs text-slate-400">atendimentos que exigem intervenção da equipe</p>
            </div>
          </div>
        </section>

        <section>
          <div className="mb-4">
            <p className="text-xs font-black uppercase tracking-[0.2em] text-sky-300">
              Capacidades do agente
            </p>
            <h2 className="mt-1 text-2xl font-black text-white">O que a Central de Atendimento IA realmente faz</h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-400">
              Estas capacidades refletem o runtime já implementado. Cartões marcados como dependência
              externa exigem configuração e homologação válidas no Control Plane; esta tela não
              apresenta credencial externa como online sem healthcheck real.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {CAPACIDADES.map((item) => {
              const Icon = item.icon;
              return (
                <div
                  key={item.titulo}
                  className="group rounded-2xl border border-sky-300/[0.08] bg-[linear-gradient(145deg,rgba(12,29,50,0.82),rgba(6,18,32,0.92))] p-4 transition hover:border-sky-300/20"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-sky-300/10 bg-sky-400/[0.07]">
                      <Icon className="size-5 text-sky-300" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-bold text-slate-100">{item.titulo}</p>
                        <span
                          className={[
                            'rounded-full px-2 py-0.5 text-[9px] font-black uppercase tracking-[0.12em]',
                            item.externa
                              ? 'bg-amber-400/[0.08] text-amber-200 ring-1 ring-amber-400/15'
                              : 'bg-emerald-400/[0.07] text-emerald-200 ring-1 ring-emerald-400/15',
                          ].join(' ')}
                        >
                          {item.externa ? 'depende de integração' : 'capacidade nativa'}
                        </span>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-400">{item.descricao}</p>
                      <p className="mt-3 text-xs font-semibold text-slate-500">{item.detalhe}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.45fr_0.55fr]">
          <div className="rounded-[24px] border border-sky-300/[0.08] bg-[linear-gradient(145deg,rgba(10,27,47,0.9),rgba(5,16,29,0.96))] p-5">
            <div className="flex flex-col gap-4 border-b border-white/[0.06] pb-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.2em] text-cyan-300">
                  Fila operacional
                </p>
                <h2 className="mt-1 text-xl font-black text-white">Conversas e intervenções</h2>
                <p className="mt-1 text-sm text-slate-400">
                  Priorize handoffs, acompanhe conversão e abra o contexto completo de cada atendimento.
                </p>
              </div>
              <div className="relative w-full lg:w-72">
                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-500" />
                <Input
                  value={busca}
                  onChange={(event) => setBusca(event.target.value)}
                  placeholder="Buscar conversa ou pedido"
                  className="border-sky-300/10 bg-white/[0.04] pl-9"
                />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {[
                ['todas', 'Todas'],
                ['atencao', 'Exigem atenção'],
                ['pedido', 'Com pedido'],
                ['checkout', 'Checkout'],
                ['handoff', 'Handoff'],
              ].map(([valor, label]) => (
                <button
                  key={valor}
                  type="button"
                  onClick={() => setFiltro(valor as FiltroFila)}
                  className={[
                    'rounded-full px-3 py-1.5 text-xs font-bold transition',
                    filtro === valor
                      ? 'bg-sky-400 text-slate-950'
                      : 'border border-white/[0.07] bg-white/[0.035] text-slate-400 hover:text-white',
                  ].join(' ')}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="mt-4 space-y-2">
              {loadingConversas ? (
                <div className="flex justify-center py-12">
                  <div className="size-7 animate-spin rounded-full border-2 border-sky-300/20 border-b-sky-300" />
                </div>
              ) : conversasFiltradas.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-sky-300/10 bg-white/[0.02] p-8 text-center">
                  <CheckCircle2 className="mx-auto size-7 text-emerald-300" />
                  <p className="mt-3 font-bold text-slate-200">Nenhuma conversa neste filtro</p>
                  <p className="mt-1 text-sm text-slate-500">
                    A fila atual não possui atendimentos correspondentes.
                  </p>
                </div>
              ) : (
                conversasFiltradas.map((conversa) => {
                  const estadoColor =
                    ESTADO_COLORS[conversa.estado] ||
                    'border-slate-600 bg-slate-700/30 text-slate-300';

                  return (
                    <div
                      key={conversa.conversa_id}
                      className="rounded-2xl border border-white/[0.06] bg-white/[0.025] p-4 transition hover:border-sky-300/15 hover:bg-white/[0.035]"
                    >
                      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <p className="font-mono text-xs font-bold text-slate-300">
                              {conversa.conversa_id.slice(0, 12)}…
                            </p>
                            <Badge className={estadoColor}>
                              {ESTADO_LABELS[conversa.estado] || conversa.estado}
                            </Badge>
                          </div>
                          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                            {conversa.pedido_id ? <span>Pedido associado</span> : null}
                            {conversa.pagamento_id ? <span>Pagamento associado</span> : null}
                            {conversa.entrega_id ? <span>Entrega associada</span> : null}
                            <span>Atualizado {formatarAtualizacao(conversa.atualizado_em)}</span>
                          </div>
                        </div>

                        <Dialog>
                          <DialogTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              className="shrink-0 border-sky-300/10 bg-white/[0.03] text-slate-200"
                            >
                              Abrir atendimento
                              <ChevronRight className="ml-1.5 size-4" />
                            </Button>
                          </DialogTrigger>
                          <ConversaDetailDialog conversa={conversa} />
                        </Dialog>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-[24px] border border-sky-300/[0.08] bg-[linear-gradient(145deg,rgba(11,29,50,0.9),rgba(5,16,29,0.96))] p-5">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-slate-500">
                Configuração administrativa
              </p>
              <h3 className="mt-2 text-lg font-black text-white">Identidade da Atendente</h3>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                Nome público e atributos de identidade ficam separados do trabalho operacional do agente.
              </p>

              <div className="mt-4 rounded-2xl border border-white/[0.06] bg-white/[0.025] p-4">
                <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
                  Nome atual
                </p>
                <p className="mt-1 truncate font-bold text-slate-100">
                  {loadingIdentidade
                    ? 'Carregando…'
                    : identidade?.nome_publico || 'Não configurado'}
                </p>
                {identidade ? (
                  <p className="mt-1 text-xs text-slate-500">Versão {identidade.versao}</p>
                ) : null}
              </div>

              {!loadingIdentidade && identidade ? (
                adminSurface ? (
                  <Dialog>
                    <DialogTrigger asChild>
                      <Button variant="outline" className="mt-4 w-full border-sky-300/10 bg-white/[0.03]">
                        Configurar identidade
                      </Button>
                    </DialogTrigger>
                    <IdentidadeDialog identidade={identidade} onSave={handleSaveIdentidade} />
                  </Dialog>
                ) : (
                  <Button asChild variant="outline" className="mt-4 w-full border-sky-300/10 bg-white/[0.03]">
                    <Link href="/admin/assistente-atendimento">
                      Abrir configuração protegida
                    </Link>
                  </Button>
                )
              ) : null}
            </div>

            <div className="rounded-[24px] border border-amber-400/12 bg-amber-400/[0.045] p-5">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-300" />
                <div>
                  <p className="font-bold text-amber-100">Integrações externas</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">
                    Meta/WhatsApp, Google Maps e o provider de IA só operam quando a configuração do
                    tenant/unidade está habilitada e homologada. Esta central mostra capacidade e fluxo;
                    credenciais continuam sob o Control Plane.
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-[24px] border border-emerald-400/12 bg-emerald-400/[0.04] p-5">
              <div className="flex items-start gap-3">
                <ShieldCheck className="mt-0.5 size-5 shrink-0 text-emerald-300" />
                <div>
                  <p className="font-bold text-emerald-100">Operação governada</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">
                    A Atendente não inventa preço, produto, pagamento ou disponibilidade e usa serviços
                    canônicos do Kordena para executar efeitos comerciais.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
