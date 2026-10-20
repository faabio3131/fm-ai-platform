# Ciclo WP-025 + WP-026 — Encerramento documental do WP-025

## Autoridade e pré-flight

Ordem explícita do proprietário: ciclo conservativo WP-025/WP-026, Application/Core/Infra read-only; sem correções funcionais ou alteração de política tenant/unidade. Aplicam-se as seções 6.3, 9 e 12 da ordem para interromper diante de bloqueador de anti-escalada preexistente.

- Worktree: `C:\fm-ai-platform-pr118-web-parity`.
- Branch: `feat/web-parity-v1-total-original-migration`.
- SHA inicial local/remoto, após fetch: `a14a67239acd1e4e6c40b7d318cd1c14320f54b2`.
- Working tree inicial: limpa. PR #118 confirmada OPEN/DRAFT no mesmo SHA.
- Continuidade consultada: Inventário Mestre, Checklist Operacional, `WP023_WP024_CICLO_2X2.md`, pendências pós-migração e instruções/skills de governança do projeto já lidas nesta sessão.

## Autoridade original encontrada

`AplicacaoImpressaoV1` já oferece `listar()`, `processar()` e `reimprimir()`. O spool é persistido sob Application + UnitOfWorkV1. O adapter físico é uma porta injetada (`PortaImpressora`): esta camada não conhece Fake, driver, rede ou spool do SO. A integração KDS -> impressão existe em `application/impressao_kds.py` (`IntegracaoImpressaoKDSV1`) e composição root em `application/impressao_composicao.py`. O Core expõe contratos imutáveis (`JobImpressao`, `DestinoImpressao`, `StatusImpressao`, `ResultadoProcessamento`), repositório, serviço de spool, adapters (`ImpressoraTCPRaw`, `ImpressoraFake`), flags e renderização de ticket. Nenhuma alteração de implementação ocorreu antes da reprodução.

Auditoria que confirmou ausência de bloqueadores: `core/impressao/**`, `application/impressao_transacoes.py`, `application/impressao_kds.py`, `application/impressao_composicao.py`, `infra/impressao/**`, UI Streamlit em `core/impressao/ui_comercial.py`, testes de unidade/integração/fitness existentes. A autoridade é estável e completa.

## Bloqueadores

**NENHUM BLOQUEADOR ENCONTRADO.** A autoridade Application/Core/Infra já implementa todas as capacidades necessárias:

- listar jobs do spool (escopo tenant/unidade)
- processar impressão (retry, contingência, idempotência)
- reimprimir (permissão `impressao.reimprimir`, idempotência, auditoria)
- destinos configurados na administração (`ResolverDestinosImpressaoSQLAlchemy`)
- adapter físico default `ImpressoraTCPRaw`
- adapter de teste `ImpressoraFake` (exportado por `core.impressao.adapters`)

A migração Web consistiu exclusivamente em expor essa autoridade via HTTP fino + UI React, sem duplicar regra de negócio.

## Migração Web WP-025 — Concluída

- **Rota Web**: `/admin/impressao`
- **Posição no Shell/Backoffice**: Item "Impressão Operacional" na seção Proprietário (após "Parâmetros Financeiros")
- **Nav item criado**: `id="impressao"` com ícone `impressao` (Printer), `allPermissions: ["admin.acessar"]`, `anyPermissions: ["producao.visualizar", "impressao.reimprimir"]`
- **Permissões utilizadas**: `admin.acessar` (gate administrativo) + `producao.visualizar` OU `impressao.reimprimir` (operação de visualizar/imprimir/reimprimir)
- **APIs/fachadas utilizadas**:
  - `GET /v1/admin/impressao/jobs` → `AplicacaoImpressaoV1.listar()`
  - `POST /v1/admin/impressao/jobs/{job_id}/processar` → `AplicacaoImpressaoV1.processar()`
  - `POST /v1/admin/impressao/jobs/{job_id}/reimprimir` → `AplicacaoImpressaoV1.reimprimir()`
- **Arquivos criados/alterados**:
  - `http_api/admin_impressao.py` (novo) — DTOs e router HTTP (3 endpoints, sem GET individual redundante)
  - `http_api/frontend_app.py` — registro do router
  - `tests/api/test_admin_impressao_http_contract.py` (novo) — 16 testes de contrato HTTP
  - `web/src/app/admin/impressao/page.tsx` (novo)
  - `web/src/features/backoffice/impressao/services/impressao-api.ts` (novo) — cliente tipado (padrão canônico de `empresa-api.ts`, bug recursivo corrigido)
  - `web/src/features/backoffice/impressao/components/ImpressaoWorkspace.tsx` (novo) — UI tabela + dialog
  - `web/src/features/backoffice/impressao/components/ImpressaoJobDialog.tsx` (novo) — detalhes + ações
  - `web/src/features/backoffice/impressao/constants.ts` (novo) — `STATUS_LABELS`, `STATUS_COLORS` compartilhados
  - `web/src/components/ui/textarea.tsx` (novo) — componente Textarea reutilizável
  - `web/src/features/shell/module-registry.ts` — módulo `impressao`
  - `web/src/features/shell/components/DashboardHome.tsx` — ícone Printer
  - `web/src/features/shell/components/UnifiedAppShell.tsx` — ícone Printer
  - `infra/impressao/__init__.py` — restaurado ao baseline (exporta apenas `ImpressoraTCPRaw`, `ResolverDestinosImpressaoSQLAlchemy`)
- **Testes executados**:
  - 16 testes HTTP novos (`test_admin_impressao_http_contract.py`): 16/16 passam
  - Ruff: clean
  - ESLint: clean para arquivos WP-025 (arquivos pré-existentes fora do escopo com erros conhecidos mantidos)
  - TypeScript: `npx tsc --noEmit` passa
  - Build: `npm run build` sucesso (rota `/admin/impressao` incluída)
  - `git diff --check`: clean (apenas avisos CRLF Windows)
- **Core/Application/Infra**: **sem alteração funcional** — reutilização total de `AplicacaoImpressaoV1`, `ServicoSpoolImpressao`, `ImpressoraTCPRaw`, `ResolverDestinosImpressaoSQLAlchemy`, contratos `core.impressao`, idempotência, retry, contingência, auditoria
- **Enxugamento cirúrgico aplicado**:
  - Removidos 42 linhas de helpers duplicados (`_job_out`, `_processar_out`, `_erro_impressao` duplicados no final do arquivo)
  - Removidos 19 linhas de DTO/helper não usados (`DestinoOut`, `_destino_out`)
  - Removida detecção automática SQLite→Fake do código de produção; Fake injetado explicitamente nos testes via parâmetro `impressora=ImpressoraFake()`
  - Removido endpoint GET `/v1/admin/impressao/jobs/{job_id}` (redundante: `GET /jobs` já retorna todos os campos)
  - Removido `obterJob()` do cliente TypeScript
  - `selectedJob` preservado: recebe objeto da lista diretamente, sem nova chamada HTTP
  - `STATUS_LABELS`/`STATUS_COLORS` centralizados em `constants.ts` compartilhado
  - Validação de negócio `motivo.length < 5` removida do frontend (mantido apenas UX: botão desabilitado); autoridade permanece no Core
  - Bug recursivo em `impressao-api.ts:65` corrigido (padrão canônico de `empresa-api.ts`)
  - Tipos TypeScript unificados: `JobResponse` removido, usa `JobImpressao`
- **Redução de linhas**: ~1276 → ~994 (aprox. 22%)
- **Commits funcionais**: `82de065eca51c95a16b5a1eaeb7eb38030c76345` (head funcional WP-025)
- **CI**: Workflow "Assistente Fase 4 Gate V1" permanece vermelho por `tests/unit/integracoes/test_whatsapp_control_plane_runtime_v1.py::test_crm_so_declara_sucesso_apos_confirmacao_do_envio`. Essa falha é **preexistente** ao WP-025 e já ocorria no commit `40127b77a2ec14625310517df17f3af282e70eec` (anterior ao WP-025). Não atribuída ao WP-025; não corrigida nesta tarefa.
- **PR #118**: mantida OPEN/DRAFT

## WP-026 — Integrações/Credenciais

**STATUS: CONCLUÍDO / MIGRADO**

### Autoridade original encontrada

`CATALOGO_V1` (core/integracoes/catalogo.py), `AplicacaoIntegracoesAdminV1` (application/integracoes_admin_transacoes.py), `ServicoConfiguracoesExternas` (core/integracoes/servicos.py), `FabricaAdaptersExternos` + healthchecks canônicos (infra/integracoes/). As autoridades Application/Core/Infra existentes fornecem as capacidades canônicas necessárias ao escopo efetivamente migrado no WP-026:
- listar integrações do catálogo + configurações salvas (escopo tenant/unidade)
- salvar/atualizar configuração com concorrência otimista (versão esperada)
- healthchecks por provedor (Gemini, Google Maps, Mercado Pago, Meta)
- homologação restrita a Administrador
- cofre de segredos criptografado (`EncryptedSQLAlchemySecretStore`)
- auditoria canônica

Nenhuma alteração de implementação ocorreu antes da reprodução.

### Migração Web WP-026 — Concluída

- **Rota Web**: `/admin/integracoes`
- **Posição no Shell/Backoffice**: Item "Integrações" na seção Proprietário
- **Nav item**: `id="integracoes"` com ícone de integração
- **Permissões**: `admin.acessar` (gate administrativo) + `integracao.gerenciar` (operações)
- **APIs/fachadas utilizadas** (exatamente 4 endpoints):
  - `GET /v1/admin/integracoes` → lista catálogo + configurações + prontidão
  - `PUT /v1/admin/integracoes/{config_id}` → `AplicacaoIntegracoesAdminV1.salvar_configuracao()` com `versao_esperada=payload.versao`
  - `POST /v1/admin/integracoes/{config_id}/healthcheck` → healthcheck por provedor canônico
  - `POST /v1/admin/integracoes/{config_id}/homologar` → `AplicacaoIntegracoesAdminV1.homologar()` (somente Administrador + step-up)
- **Arquivos criados/alterados**:
  - `http_api/admin_integracoes.py` (novo) — DTOs e router HTTP (4 endpoints)
  - `http_api/frontend_app.py` — registro do router
  - `tests/api/test_admin_integracoes_http_contract.py` (novo) — 19 testes de contrato HTTP
  - `web/src/app/admin/integracoes/page.tsx` (novo)
  - `web/src/features/backoffice/integracoes/services/integracoes-api.ts` (novo)
  - `web/src/features/backoffice/integracoes/components/IntegracoesWorkspace.tsx` (novo)
  - `web/src/features/shell/module-registry.ts` — módulo `integracoes`
  - `web/src/features/shell/components/DashboardHome.tsx` — ícone
  - `web/src/features/shell/components/UnifiedAppShell.tsx` — ícone
- **Testes executados**:
  - 19 testes HTTP (`test_admin_integracoes_http_contract.py`): 19/19 passam (inclui `test_concorrencia_versionamento_preservados` provando 409 `versao_configuracao_divergente` com stale version)
  - Ruff: clean
  - ESLint: 0 errors / 0 warnings nos arquivos WP-026
  - TypeScript: `npx tsc --noEmit` passa
  - Build: `npm run build` sucesso (rota `/admin/integracoes` incluída)
  - `git diff --check`: clean
- **Core/Application/Infra**: **sem alteração funcional** — reutilização total das autoridades canônicas
- **Enxugamento cirúrgico aplicado**:
  - Removido helper morto `_configuracao_salva_out` (instanciava `ServicoConfiguracoesExternas` com `None` + `type: ignore`)
  - Extraído helper local `_criar_servico_e_vault(session, master_key)` para eliminar repetição nos 4 endpoints
  - Bug de concorrência otimista corrigido: PUT agora usa `payload.versao` do contrato do cliente (era recalculado do DB, invalidando proteção)
- **Redução de complexidade**: eliminação de código morto + DRY local sem nova abstração arquitetural
- **Commit funcional**: `8f10f42da90b19eb3dd82962f2327ebb9c417e82` (head funcional WP-026)
- **CI**: Workflow "Assistente Fase 4 Gate V1" permanece vermelho por `tests/unit/integracoes/test_whatsapp_control_plane_runtime_v1.py::test_crm_so_declara_sucesso_apos_confirmacao_do_envio`. Essa falha é **preexistente** ao WP-026 e já ocorria antes do WP-026. Não atribuída ao WP-026; não corrigida nesta tarefa.
- **PR #118**: mantida OPEN/DRAFT

## Gate final documental

```bash
git diff --check
git status --short
git diff -- docs/web-parity/KORDENA_WEB_PARITY_V1_CHECKLIST_OPERACIONAL.md
git diff -- docs/web-parity/WP025_WP026_CICLO_2X2.md
```

NÃO commit.
NÃO push.

PARE para auditoria humana.