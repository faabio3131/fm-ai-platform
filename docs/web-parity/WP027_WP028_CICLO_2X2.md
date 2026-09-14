# Ciclo WP-027 + WP-028 — Encerramento documental do WP-027

## Autoridade e pré-flight

O WP-027 foi executado como migração conservativa da superfície Web do Assistente de Atendimento, preservando as autoridades existentes de domínio, runtime de canal, identidade configurável, handoff e segurança. O WP-028 permaneceu fora de execução durante todo o ciclo.

- Branch oficial: `feat/web-parity-v1-total-original-migration`.
- PR: `#118`, mantida OPEN/DRAFT e não mergeada.
- Head funcional final do WP-027: `80a38497d7bf969c7e94b286f43349e1d383ff26`.
- Snapshot de handoff local preservado em `1347a6aacc2870921dc3ad65b5f73d0b7d57378a`.
- Correção estrutural principal: `8ecf05bf54928465ce8f9d63bcdfab025ae8513f`.
- Correções finais de certificação: `80a38497d7bf969c7e94b286f43349e1d383ff26`.

## Autoridade original encontrada

O domínio já possuía runtime operacional do Assistente de Atendimento, estado de canal WhatsApp cifrado, identidade configurável por tenant/unidade, handoff auditável e integração com os fluxos operacionais existentes. A migração não criou um segundo Assistente, segundo webhook, segunda memória de conversa ou segunda política de atendimento.

A identidade pública permanece configurável por tenant/unidade; nenhum nome fixo de bot foi introduzido na Web.

## Migração Web WP-027 — Concluída

- **Rota Web**: `/admin/assistente-atendimento`.
- **Posição no Shell/Backoffice**: módulo "Assistente de Atendimento" na área Proprietário.
- **Permissões introduzidas**: `atendimento.visualizar` e `atendimento.gerenciar`.
- **Gate administrativo**: `admin.acessar` + sessão assinada + step-up administrativo existente.
- **Escopo**: tenant/unidade exclusivamente derivados da sessão autenticada; consultas de conversa permanecem escopadas por `tenant_id + unidade_id + conversa_id`.
- **HTTP**: adaptador fino em `http_api/admin_assistente_atendimento.py`, sem import de `infra.*`, sem SQL direto e sem UnitOfWork no handler.
- **Application Web**: `application/assistente_atendimento_admin.py` concentra leitura/configuração de identidade, listagem/detalhe de conversas e handoff administrativo reutilizando as autoridades existentes do projeto.
- **Estado de canal**: `EncryptedSQLAlchemyChannelStateStore.obter_por_conversa()` foi adicionado como leitura escopada para a superfície administrativa.
- **Identidade**: GET/PUT Web reutilizam `ServicoIdentidadeAssistente` e `RepositorioIdentidadeAssistenteSQLAlchemy`, com bootstrap do fallback e concorrência otimista preservados.
- **Handoff forçado**: registra handoff auditável, persiste `HANDOFF_HUMANO` também no estado cifrado do runtime e preserva IDs de pedido, pagamento, entrega e marcadores inbound/outbound/status.
- **Segurança HTTP**: erros de segurança voltam ao tratador canônico antes do tratamento genérico de `ValueError`, preservando `401/403` em vez de degradar para `400`.
- **Frontend**: cliente tipado, workspace React, página Next, constantes de estado e integração no Shell; nenhuma regra de negócio crítica foi movida para React.

## Arquivos principais do WP-027

- `application/assistente_atendimento_admin.py`
- `core/seguranca/permissoes.py`
- `http_api/admin_assistente_atendimento.py`
- `http_api/frontend_app.py`
- `infra/assistente_atendimento/canal_estado_sqlalchemy.py`
- `tests/api/test_admin_assistente_atendimento_http_contract.py`
- `web/src/app/admin/assistente-atendimento/page.tsx`
- `web/src/features/backoffice/assistente-atendimento/constants.ts`
- `web/src/features/backoffice/assistente-atendimento/services/assistente-atendimento-api.ts`
- `web/src/features/backoffice/assistente-atendimento/components/AssistenteAtendimentoWorkspace.tsx`
- `web/src/features/shell/module-registry.ts`
- `web/src/features/shell/components/DashboardHome.tsx`
- `web/src/features/shell/components/UnifiedAppShell.tsx`

## Certificação local

Executada no worktree `C:\fm-ai-platform-pr118-web-parity` sobre o head funcional `80a38497d7bf969c7e94b286f43349e1d383ff26`:

- `python -m py_compile` dos arquivos Python do WP-027: aprovado.
- Ruff dirigido aos arquivos WP-027: **All checks passed**.
- `tests/api/test_admin_assistente_atendimento_http_contract.py`: **6/6 PASS**.
- regressão `tests/unit/assistente_atendimento/` + AF-09 RBAC + Assistente Commercial Cutover: **75/75 PASS**.
- ESLint dirigido aos arquivos Web do WP-027: aprovado.
- `npx tsc --noEmit`: aprovado.
- `npm run build`: aprovado; rota `/admin/assistente-atendimento` presente no build Next.js.
- `git diff --check`: aprovado.
- resíduo local `WP027_HANDOFF_COMPLETO.md`: mantido propositalmente fora do Git.

## CI da PR #118 no head funcional

No head `80a38497d7bf969c7e94b286f43349e1d383ff26`:

- **Commercial Runtime Readiness V1**: SUCCESS.
- **PR Superseded Runs Cleanup**: SUCCESS.
- **Assistente Fase 4 Gate V1**: compile PASS; Ruff PASS; suíte alvo terminou com **151 PASS / 1 FAIL / 58 warnings**.

A única falha é `tests/unit/integracoes/test_whatsapp_control_plane_runtime_v1.py::test_crm_so_declara_sucesso_apos_confirmacao_do_envio`, que exige a presença textual de `despachar_resgate_whatsapp_legado(` em um trecho do CRM legado. Esta falha é preexistente ao WP-027 e já estava presente nos checkpoints anteriores; não foi introduzida nem corrigida pelo WP-027 para evitar contaminação de escopo.

## Estado final do WP-027

**STATUS: MIGRADO / CONCLUÍDO.**

A superfície Web administrativa do Assistente de Atendimento está implementada, escopada, governada e certificada nos gates específicos do WP-027. A falha global remanescente do workflow Assistente Fase 4 é dívida preexistente e registrada, não bloqueador atribuído ao WP-027.

## WP-028 — Gerente IA

**STATUS: NÃO INICIADO NESTE CICLO.**

Nenhuma façade Web, UI, regra, prompt, política, permissão ou inteligência do Gerente IA foi alterada durante o fechamento do WP-027. O WP-028 deverá começar somente a partir de novo pré-flight e auditoria da autoridade existente.
