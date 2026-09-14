'use client';

import { useState, useCallback, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  obterIdentidade,
  configurarIdentidade,
  listarConversas,
  obterConversa,
  forcarHandoff,
  IdentidadeAssistente,
  IdentidadeAssistentePutRequest,
  ConversaResumo,
  ConversaDetalhe,
} from '../services/assistente-atendimento-api';
import { ESTADO_LABELS, ESTADO_COLORS } from '../constants';

interface IdentidadeDialogProps {
  identidade: IdentidadeAssistente;
  onSave: (identidade: IdentidadeAssistente) => void;
}

function IdentidadeDialog({
  identidade,
  onSave,
}: IdentidadeDialogProps) {
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
      setFormData({ nome_publico: resultado.nome_publico, atributos: resultado.atributos || {} });
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
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-lg">Identidade do Assistente</DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-4">
          <div>
            <Label htmlFor="nome_publico">Nome público do Assistente</Label>
            <Input
              id="nome_publico"
              value={formData.nome_publico}
              onChange={(e) => setFormData((prev) => ({ ...prev, nome_publico: e.target.value }))}
              placeholder="Ex.: Mica, Ana, João..."
              maxLength={80}
            />
            <p className="text-xs text-muted-foreground mt-1">
              Este é o nome que o Assistente usará ao se apresentar aos clientes. Configurável por tenant/unidade.
            </p>
          </div>
          <div>
            <Label htmlFor="atributos">Atributos adicionais (JSON)</Label>
            <textarea
              id="atributos"
              value={JSON.stringify(formData.atributos, null, 2)}
              onChange={(e) => {
                try {
                  setFormData((prev) => ({ ...prev, atributos: JSON.parse(e.target.value) || {} }));
                  setError('');
                } catch {
                  setError('JSON inválido');
                }
              }}
              className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono text-xs"
              placeholder='{"chave": "valor"}'
            />
            {error && <p className="text-sm text-red-600 dark:text-red-400 mt-1">{error}</p>}
          </div>
          <div className="flex gap-3 pt-4 border-t">
            <Button onClick={handleSave} disabled={saving} className="flex-1">
              {saving ? 'Salvando...' : 'Salvar'}
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

function ConversaDetailDialog({
  conversa,
}: ConversaDetailDialogProps) {
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
    load();
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
  const estadoColor = ESTADO_COLORS[conversa.estado] || 'bg-gray-500/20 text-gray-300';

  function renderContent() {
    if (error) {
      return (
        <div className="p-3 rounded-lg border bg-red-50 text-red-800 dark:bg-red-900/20 border-red-200 text-sm">
          {error}
        </div>
      );
    }
    if (loading) {
      return (
        <div className="flex justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
        </div>
      );
    }
    if (!detalhe) {
      return null;
    }

    return (
      <div className="space-y-4">
        <div className="grid gap-2 md:grid-cols-2 text-sm">
          <div>
            <Label className="text-muted-foreground">Conversa ID</Label>
            <p className="font-mono text-xs break-all">{detalhe.conversa_id}</p>
          </div>
          <div>
            <Label className="text-muted-foreground">Estado</Label>
            <Badge className={estadoColor}>{estadoLabel}</Badge>
          </div>
          {detalhe.pedido_id && (
            <div>
              <Label className="text-muted-foreground">Pedido</Label>
              <p className="font-mono text-xs">{detalhe.pedido_id}</p>
            </div>
          )}
          {detalhe.pagamento_id && (
            <div>
              <Label className="text-muted-foreground">Pagamento</Label>
              <p className="font-mono text-xs">{detalhe.pagamento_id}</p>
            </div>
          )}
          {detalhe.entrega_id && (
            <div>
              <Label className="text-muted-foreground">Entrega</Label>
              <p className="font-mono text-xs">{detalhe.entrega_id}</p>
            </div>
          )}
          {detalhe.ultimo_inbound_id && (
            <div>
              <Label className="text-muted-foreground">Último inbound</Label>
              <p className="font-mono text-xs">{detalhe.ultimo_inbound_id}</p>
            </div>
          )}
          {detalhe.ultimo_outbound_id && (
            <div>
              <Label className="text-muted-foreground">Último outbound</Label>
              <p className="font-mono text-xs">{detalhe.ultimo_outbound_id}</p>
            </div>
          )}
          <div>
            <Label className="text-muted-foreground">Versão</Label>
            <p>{detalhe.versao}</p>
          </div>
        </div>
        {detalhe.handoff_contexto && Object.keys(detalhe.handoff_contexto).length > 0 && (
          <div className="p-3 rounded-lg border bg-muted">
            <Label className="text-muted-foreground block mb-1">Contexto do handoff</Label>
            <pre className="text-xs overflow-auto max-h-40 font-mono">
              {JSON.stringify(detalhe.handoff_contexto, null, 2)}
            </pre>
          </div>
        )}
        <hr className="border-border" />
        <div className="space-y-2">
          <Label className="block text-sm font-medium">Forçar handoff humano</Label>
          <p className="text-sm text-muted-foreground">
            Encaminha esta conversa para atendimento humano. O bot pausará e registrará o motivo na auditoria.
          </p>
          <Input
            value={handoffMotivo}
            onChange={(e) => {
              setHandoffMotivo(e.target.value);
              setHandoffError('');
            }}
            placeholder="Motivo do handoff (ex.: cliente solicitou atendente)"
            disabled={handoffLoading}
          />
          {handoffError && <p className="text-sm text-red-600 dark:text-red-400">{handoffError}</p>}
          <div className="flex gap-3 pt-2">
            <Button
              onClick={handleHandoff}
              disabled={handoffLoading || !handoffMotivo.trim()}
              variant="destructive"
              className="flex-1"
            >
              {handoffLoading ? 'Encaminhando...' : 'Forçar Handoff Humano'}
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
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-lg flex items-center gap-2">
            Conversa {conversa.conversa_id.slice(0, 8)}…
            <Badge className={estadoColor + ' text-xs'}>
              {estadoLabel}
            </Badge>
          </DialogTitle>
        </DialogHeader>
        <div className="p-6 space-y-4">
          {renderContent()}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AssistenteAtendimentoWorkspace() {
  const [identidade, setIdentidade] = useState<IdentidadeAssistente | null>(null);
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [loadingIdentidade, setLoadingIdentidade] = useState(true);
  const [loadingConversas, setLoadingConversas] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
    loadIdentidade();
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
    loadConversas();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSaveIdentidade = useCallback((novaIdentidade: IdentidadeAssistente) => {
    setIdentidade(novaIdentidade);
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Assistente de Atendimento</h1>
        <p className="text-muted-foreground">
          Identidade configurável por tenant/unidade e monitoramento de conversas WhatsApp.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-lg border bg-red-50 text-red-800 dark:bg-red-900/20 border-red-200">
          <p>{error}</p>
        </div>
      )}

      {/* Seção Identidade */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
          <CardTitle className="text-lg">Identidade do Assistente</CardTitle>
          {identidade && (
            <Badge variant="secondary" className="text-xs">
              v{identidade.versao}
            </Badge>
          )}
        </CardHeader>
        <CardContent className="pt-0">
          {loadingIdentidade ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : identidade ? (
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="outline" className="w-full justify-start">
                  {identidade.nome_publico || 'Não configurado (usando fallback)'}
                </Button>
              </DialogTrigger>
              <IdentidadeDialog identidade={identidade} onSave={handleSaveIdentidade} />
            </Dialog>
          ) : (
            <p className="text-muted-foreground">Carregando...</p>
          )}
        </CardContent>
      </Card>

      {/* Seção Conversas */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
          <CardTitle className="text-lg">Conversas Ativas</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {loadingConversas ? (
            <div className="flex justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : (
            <div className="grid gap-4">
              {conversas.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground">
                  <p>Nenhuma conversa ativa no momento.</p>
                </div>
              ) : (
                conversas.map((conversa) => (
                  <Card key={conversa.conversa_id} className="border-border/50">
                    <CardHeader className="flex flex-row items-center justify-between py-2 px-4">
                      <div className="flex items-center gap-3">
                        <CardTitle className="text-base font-medium">
                          {conversa.conversa_id.slice(0, 12)}…
                        </CardTitle>
                        <Badge className={ESTADO_COLORS[conversa.estado] + ' text-xs'}>
                          {ESTADO_LABELS[conversa.estado] || conversa.estado}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        {conversa.pedido_id && (
                          <>
                            <span>Pedido: {conversa.pedido_id.slice(0, 8)}…</span>
                            <span className="h-4 w-px bg-border mx-2" />
                          </>
                        )}
                        <span className="text-xs">v{conversa.versao}</span>
                      </div>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button variant="outline" className="w-full justify-start" size="sm">
                            Ver detalhes
                          </Button>
                        </DialogTrigger>
                        <ConversaDetailDialog
                          conversa={conversa}
                        />
                      </Dialog>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}