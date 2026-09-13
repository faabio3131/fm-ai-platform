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
  listarIntegracoes,
  salvarIntegracao,
  executarHealthcheck,
  homologarIntegracao,
  Integracao,
  ConfiguracaoSalva,
  IntegracoesPutRequest,
  HealthcheckResponse,
} from '../services/integracoes-api';
import {
  PARAMETRO_LABELS,
  CREDENCIAL_LABELS,
  AMBIENTE_LABELS,
  PRONTIDAO_LABELS,
  PRONTIDAO_COLORS,
} from '../constants';

interface IntegracaoDetailDialogProps {
  integracao: Integracao;
  onSave: (config: ConfiguracaoSalva) => void;
  onHealthcheck: (configId: string) => Promise<HealthcheckResponse>;
  onHomologar: (configId: string, evidenciaRef: string) => Promise<void>;
}

function IntegracaoDetailDialog({
  integracao,
  onSave,
  onHealthcheck,
  onHomologar,
}: IntegracaoDetailDialogProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [activeTab, setActiveTab] = useState<'config' | 'healthcheck' | 'homologacao'>('config');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [homologating, setHomologating] = useState(false);
  const [healthcheckResult, setHealthcheckResult] = useState<{
    sucesso: boolean;
    mensagem: string;
    detalhes?: Record<string, unknown>;
    evidenciaRef?: string;
  } | null>(null);
  const [homologacaoEvidencia, setHomologacaoEvidencia] = useState('');
  const [homologacaoError, setHomologacaoError] = useState('');
  const [formData, setFormData] = useState<{
    conta_externa: string;
    ambiente: string;
    habilitada: boolean;
    parametros: Record<string, string | number | boolean | null>;
    credenciais: Record<string, string>;
  }>({
    conta_externa: integracao.configuracao?.conta_externa || 'principal',
    ambiente: integracao.configuracao?.ambiente || 'sandbox',
    habilitada: integracao.configuracao?.habilitada || false,
    parametros: integracao.configuracao?.parametros || {},
    credenciais: {},
  });
  const [versao, setVersao] = useState(integracao.configuracao?.versao || 0);

  const handleParametroChange = (nome: string, valor: string) => {
    setFormData((prev) => ({
      ...prev,
      parametros: { ...prev.parametros, [nome]: valor || null },
    }));
  };

  const handleCredencialChange = (papel: string, valor: string) => {
    setFormData((prev) => ({
      ...prev,
      credenciais: { ...prev.credenciais, [papel]: valor },
    }));
  };

  const handleSave = async () => {
    setSaving(true);
    setHealthcheckResult(null);
    try {
      const payload: IntegracoesPutRequest = {
        servico: integracao.catalogo.servico,
        provedor: integracao.catalogo.provedor,
        conta_externa: formData.conta_externa,
        ambiente: formData.ambiente as 'sandbox' | 'homologacao' | 'producao',
        parametros: Object.entries(formData.parametros).map(([nome, valor]) => ({
          nome,
          valor,
        })),
        credenciais: Object.entries(formData.credenciais)
          .filter(([, valor]) => valor.trim() !== '')
          .map(([papel, valor]) => ({ papel, valor })),
        habilitada: formData.habilitada,
        versao,
      };

      const resultado = await salvarIntegracao(integracao.catalogo.servico + '--' + integracao.catalogo.provedor, payload);
      setVersao(resultado.versao);
      setFormData((prev) => ({ ...prev, credenciais: {} }));
      setHealthcheckResult({ sucesso: true, mensagem: 'Configuração salva com sucesso' });
      onSave(resultado);
    } catch (err: unknown) {
      const mensagem = err instanceof Error ? err.message : 'Erro ao salvar configuração';
      setHealthcheckResult({ sucesso: false, mensagem });
    } finally {
      setSaving(false);
    }
  };

  const handleHealthcheck = async () => {
    setTesting(true);
    setHealthcheckResult(null);
    try {
      await onHealthcheck(integracao.catalogo.servico + '--' + integracao.catalogo.provedor);
    } catch {
      // error handled in parent
    } finally {
      setTesting(false);
    }
  };

  const handleHomologar = async () => {
    if (!homologacaoEvidencia.trim()) {
      setHomologacaoError('Informe a referência da evidência de homologação');
      return;
    }
    setHomologating(true);
    setHomologacaoError('');
    try {
      await onHomologar(integracao.catalogo.servico + '--' + integracao.catalogo.provedor, homologacaoEvidencia);
      setHomologacaoError('');
      setHealthcheckResult({ sucesso: true, mensagem: 'Homologação registrada com sucesso' });
    } catch (err: unknown) {
      const mensagem = err instanceof Error ? err.message : 'Erro ao homologar';
      setHomologacaoError(mensagem);
    } finally {
      setHomologating(false);
    }
  };

  if (!isOpen) return null;

  const config = integracao.configuracao;
  const spec = integracao.catalogo;

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto p-0">
        <DialogHeader className="p-6 border-b">
          <DialogTitle className="text-lg flex items-center gap-2">
            {spec.label}
            <Badge variant="secondary" className="ml-2">
              {PRONTIDAO_LABELS[config?.prontidao.estado || 'desativado']}
            </Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="border-b px-6 py-3">
          <div className="flex gap-4" role="tablist">
            <button
              role="tab"
              aria-selected={activeTab === 'config'}
              onClick={() => setActiveTab('config')}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'config'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              Configuração
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'healthcheck'}
              onClick={() => setActiveTab('healthcheck')}
              disabled={!spec.healthcheck_supported}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'healthcheck'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              } ${!spec.healthcheck_supported ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              Testar Conexão
            </button>
            <button
              role="tab"
              aria-selected={activeTab === 'homologacao'}
              onClick={() => setActiveTab('homologacao')}
              disabled={!config || !config.habilitada || !config.prontidao.pronto}
              className={`px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'homologacao'
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              } ${!config || !config.habilitada || !config.prontidao.pronto ? 'opacity-50 cursor-not-allowed' : ''}`}
            >
              Homologar
            </button>
          </div>
        </div>

        <div className="p-6 space-y-6">
          {healthcheckResult && (
            <div className={`p-4 rounded-lg border ${healthcheckResult.sucesso ? 'bg-green-50 text-green-800 dark:bg-green-900/20 border-green-200' : 'bg-red-50 text-red-800 dark:bg-red-900/20 border-red-200'}`}>
              <p className="font-medium">{healthcheckResult.mensagem}</p>
              {healthcheckResult.detalhes && (
                <pre className="mt-2 text-xs overflow-auto max-h-40">{JSON.stringify(healthcheckResult.detalhes, null, 2)}</pre>
              )}
              {healthcheckResult.evidenciaRef && (
                <div className="mt-2">
                  <Label className="text-xs font-medium">Referência de evidência:</Label>
                  <div className="flex gap-2 mt-1">
                    <Input
                      value={healthcheckResult.evidenciaRef}
                      readOnly
                      className="flex-1 text-xs bg-muted"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(healthcheckResult.evidenciaRef!);
                        setHealthcheckResult((prev) => prev ? { ...prev, mensagem: prev.mensagem + ' (copiado)' } : null);
                      }}
                    >
                      Copiar
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'config' && (
            <div className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <Label htmlFor="conta_externa">Conta / identificação externa</Label>
                  <Input
                    id="conta_externa"
                    value={formData.conta_externa}
                    onChange={(e) => setFormData((prev) => ({ ...prev, conta_externa: e.target.value }))}
                    placeholder="principal"
                  />
                </div>
                <div>
                  <Label htmlFor="ambiente">Ambiente</Label>
                  <select
                    id="ambiente"
                    value={formData.ambiente}
                    onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFormData((prev) => ({ ...prev, ambiente: e.target.value }))}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="sandbox">Sandbox</option>
                    <option value="homologacao">Homologação</option>
                    <option value="producao">Produção</option>
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    id="habilitada"
                    checked={formData.habilitada}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFormData((prev) => ({ ...prev, habilitada: e.target.checked }))}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-ring peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-background peer-disabled:cursor-not-allowed peer-disabled:opacity-50 peer-data-[state=checked]:bg-primary peer-data-[state=unchecked]:bg-input peer-data-[state=checked]:bg-primary peer-data-[state=unchecked]:bg-input">
                    <span className="pointer-events-none block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-transform peer-data-[state=checked]:translate-x-5 peer-data-[state=unchecked]:translate-x-0" />
                  </div>
                </label>
                <Label htmlFor="habilitada" className="cursor-pointer">
                  Integração habilitada
                </Label>
              </div>

              <hr className="border-border" />

              <div>
                <Label className="block text-sm font-medium mb-2">Parâmetros da integração</Label>
                <div className="grid gap-4 md:grid-cols-2">
                  {spec.parametros_obrigatorios.map((param) => (
                    <div key={param}>
                      <Label htmlFor={`param_${param}`}>{PARAMETRO_LABELS[param] || param}</Label>
                      <Input
                        id={`param_${param}`}
                        value={String(formData.parametros[param] ?? '')}
                        onChange={(e) => handleParametroChange(param, e.target.value)}
                        placeholder={PARAMETRO_LABELS[param] || param}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <hr className="border-border" />

              <div>
                <Label className="block text-sm font-medium mb-2">Credenciais protegidas</Label>
                <p className="text-sm text-muted-foreground mb-3">
                  Deixe vazio para manter a credencial atual. O valor salvo nunca é reexibido.
                </p>
                <div className="grid gap-4 md:grid-cols-2">
                  {spec.credenciais_obrigatorias.map((cred) => (
                    <div key={cred}>
                      <Label htmlFor={`cred_${cred}`}>{CREDENCIAL_LABELS[cred] || cred}</Label>
                      <Input
                        id={`cred_${cred}`}
                        type="password"
                        value={formData.credenciais[cred] || ''}
                        onChange={(e) => handleCredencialChange(cred, e.target.value)}
                        placeholder={config?.credenciais_estado?.[cred] ? 'Configurada (deixe vazio para manter)' : 'Não configurada'}
                        autoComplete="new-password"
                      />
                      {config?.credenciais_estado?.[cred] && (
                        <p className="text-xs text-green-600 dark:text-green-400 mt-1">✓ Configurada</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-3 pt-4 border-t">
                <Button onClick={handleSave} disabled={saving} className="flex-1">
                  {saving ? 'Salvando...' : 'Salvar / atualizar'}
                </Button>
                <Button variant="outline" onClick={() => setIsOpen(false)} disabled={saving}>
                  Cancelar
                </Button>
              </div>
            </div>
          )}

          {activeTab === 'healthcheck' && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Executa uma chamada real ao provedor usando as credenciais já salvas.
                Não altera o estado de homologação. Requer PIN administrativo.
              </p>
              {spec.healthcheck_supported ? (
                <Button onClick={handleHealthcheck} disabled={testing || !config}>
                  {testing ? 'Testando...' : 'Executar healthcheck real'}
                </Button>
              ) : (
                <div className="p-4 rounded-lg border bg-secondary text-secondary-foreground">
                  <p className="text-sm">Este provedor não possui healthcheck canônico implementado no backend.
                    A homologação deverá ser feita por evidência externa manual.</p>
                </div>
              )}
            </div>
          )}

          {activeTab === 'homologacao' && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Registre a homologação após validação real do provedor.
                Informe uma referência verificável (ticket, log sanitizado, execução de healthcheck).
                Não cole tokens, chaves, PINs ou segredos neste campo.
                Requer papel Administrador e PIN administrativo.
              </p>
              <div>
                <Label htmlFor="evidencia_ref">Referência da evidência de homologação</Label>
                <Input
                  id="evidencia_ref"
                  value={homologacaoEvidencia}
                  onChange={(e) => {
                    setHomologacaoEvidencia(e.target.value);
                    setHomologacaoError('');
                  }}
                  placeholder="Ex.: healthcheck://meta/2026-08-17/resultado-123"
                  maxLength={512}
                />
                {homologacaoError && (
                  <p className="text-sm text-red-600 dark:text-red-400 mt-1">{homologacaoError}</p>
                )}
              </div>
              <div className="flex gap-3 pt-4 border-t">
                <Button
                  onClick={handleHomologar}
                  disabled={homologating || !config || !config.habilitada || !config.prontidao.pronto}
                  className="flex-1"
                >
                  {homologating ? 'Homologando...' : 'Homologar'}
                </Button>
                <Button variant="outline" onClick={() => setIsOpen(false)} disabled={homologating}>
                  Cancelar
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function IntegracoesWorkspace() {
  const [integracoes, setIntegracoes] = useState<Integracao[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await listarIntegracoes();
        if (!cancelled) setIntegracoes(response.integracoes);
      } catch (err: unknown) {
        if (!cancelled) {
          const mensagem = err instanceof Error ? err.message : 'Erro ao carregar integrações';
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
  }, []);

  const handleSave = useCallback((config: ConfiguracaoSalva) => {
    setIntegracoes((prev) =>
      prev.map((i) =>
        i.configuracao?.configuracao_id === config.configuracao_id
          ? { ...i, configuracao: config }
          : i
      )
    );
  }, []);

  const handleHealthcheck = useCallback(async (configId: string) => {
    try {
      const result = await executarHealthcheck(configId);
      setIntegracoes((prev) =>
        prev.map((i) => {
          if (i.catalogo.servico + '--' + i.catalogo.provedor !== configId) return i;
          if (!i.configuracao) return i;
          return {
            ...i,
            configuracao: {
              ...i.configuracao,
              prontidao: {
                ...i.configuracao.prontidao,
                estado: result.executado ? 'configurado' : i.configuracao.prontidao.estado,
              },
            },
          };
        })
      );
      const integracao = integracoes.find((i) => i.catalogo.servico + '--' + i.catalogo.provedor === configId);
      if (integracao) {
        // DialogTrigger uses integracao directly from map, no need to sync selectedIntegracao
      }
      return result;
    } catch (err: unknown) {
      throw err;
    }
  }, [integracoes]);

  const handleHomologar = useCallback(async (configId: string, evidenciaRef: string) => {
    const result = await homologarIntegracao(configId, evidenciaRef);
    setIntegracoes((prev) =>
      prev.map((i) =>
        i.configuracao?.configuracao_id === configId ? { ...i, configuracao: result } : i
      )
    );
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Integrações e Credenciais</h1>
        <p className="text-muted-foreground">
          Configure provedores externos do estabelecimento. Cada configuração é isolada pelo tenant e pela unidade autenticados.
        </p>
      </div>

      {error && (
        <div className="p-4 rounded-lg border bg-red-50 text-red-800 dark:bg-red-900/20 border-red-200">
          <p>{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : (
        <div className="grid gap-4">
          {integracoes.map((integracao) => (
            <Card key={integracao.catalogo.servico + '--' + integracao.catalogo.provedor}>
              <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-lg">{integracao.catalogo.label}</CardTitle>
                  {integracao.configuracao && (
                    <Badge className={PRONTIDAO_COLORS[integracao.configuracao.prontidao.estado] + ' text-xs'}>
                      {PRONTIDAO_LABELS[integracao.configuracao.prontidao.estado]}
                    </Badge>
                  )}
                  {!integracao.configuracao && (
                    <Badge variant="secondary" className="text-xs">
                      Não configurada
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  {integracao.configuracao && (
                    <>
                      <span>{AMBIENTE_LABELS[integracao.configuracao.ambiente]}</span>
                      <span className="h-4 w-px bg-border mx-2" />
                      <span>{integracao.configuracao.habilitada ? 'Habilitada' : 'Desabilitada'}</span>
                      {integracao.configuracao.homologada && (
                        <>
                          <span className="h-4 w-px bg-border mx-2" />
                          <Badge variant="outline" className="text-xs">Homologada</Badge>
                        </>
                      )}
                    </>
                  )}
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <Dialog>
                  <DialogTrigger asChild>
                    <Button variant="outline" className="w-full justify-start">
                      {integracao.configuracao ? 'Ver / Editar' : 'Configurar'}
                    </Button>
                  </DialogTrigger>
                  <IntegracaoDetailDialog
                    integracao={integracao}
                    onSave={handleSave}
                    onHealthcheck={handleHealthcheck}
                    onHomologar={handleHomologar}
                  />
                </Dialog>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}