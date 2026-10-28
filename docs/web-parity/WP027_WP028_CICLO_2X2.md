# Ciclo WP-027 + WP-028 — Encerramento documental

## Autoridade e pré-flight

O WP-027 foi executado como migração conservativa da superfície Web do Assistente de Atendimento, preservando as autoridades existentes de domínio, runtime de canal, identidade configurável, handoff e segurança. Em seguida, o WP-028 foi executado como migração conservativa da superfície Web operacional do Gerente IA, reutilizando integralmente o runtime, tools, previews, confirmação humana, fingerprint, idempotência, RBAC e demais autoridades canônicas já existentes.

- Branch oficial: `feat/web-parity-v1-total-original-migration`.
- PR: `#118`, mantida OPEN/DRAFT e não mergeada.
- Head funcional final do WP-027: `80a38497d7bf969c7e94b286f43349e1d383ff26`.
- Snapshot de handoff local preservado em `1347a6aacc2870921dc3ad65b5f73d0b7d57378a`.
- Correção estrutural principal WP-027: `8ecf05bf54928465ce8f9d63bcdfab025ae8513f`.
- Correções finais de certificação WP-027: `80a38497d7bf969c7e94b286f43349e1d383ff26`.
- Commit de integração do Gerente IA ao shell operacional: `1db1b8295dc796079af581b29e46bc9e87aa4ce1`.
- Teste HTTP assinado do WP-028: `4926ed313f58c23b0d5dea772f091c3c211d932c`.
- Gate dedicado WP-028: `1861eb26e6682368994e3c2e6a034c1060769602`.
- Correções de contrato/CI do WP-028: `4762407afff9e35882e6c982e176269baf31cf01`, `619b02f96a839247d1f0633d01c6bf33967ba2c2`, `5255b13e35c55ddd53d38d8dce886503fe68d114`, `4818af8b9a5e958b83e3ba236a3028d55685bea8`.
- Correção final de whitespace que bloqueava `git diff --check`: `04bcfe31cf4c46d3dabf6e341747ed7a0b8cb96d`.

## WP-027 — Assistente de Atendimento

### Autoridade original encontrada

O domínio já possuía runtime operacional do Assistente de Atendimento, estado de canal WhatsApp cifrado, identidade configurável por tenant/unidade, handoff auditável e integração com os fluxos operacionais existentes. A migração não criou um segundo Assistente, segundo webhook, segunda memória de conversa ou segunda política de atendimento.

A identidade pública permanece configurável por tenant/unidade; nenhum nome fixo de bot foi introduzido na Web.

### Migração Web WP-027 — Concluída

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

### Certificação WP-027

- `python -m py_compile`: aprovado.
- Ruff dirigido: aprovado.
- HTTP WP-027: **6/6 PASS**.
- regressão Assistente/RBAC: **75/75 PASS**.
- ESLint: aprovado.
- TypeScript: aprovado.
- Next production build: aprovado.
- `git diff --check`: aprovado.

**STATUS WP-027: MIGRADO / CONCLUÍDO.**

## Gate Zero antes do WP-028

A dívida histórica `tests/unit/integracoes/test_whatsapp_control_plane_runtime_v1.py::test_crm_so_declara_sucesso_apos_confirmacao_do_envio` foi reavaliada antes do WP-028. O teste ainda verificava presença textual do boundary legado, enquanto o fluxo já delegava ao boundary canônico da Application. O teste foi atualizado para validar a autoridade correta, preservando consentimento, despacho governado e comportamento comercial. Após a correção, o workflow **Assistente Fase 4 Gate V1** voltou a SUCCESS e deixou de existir exceção de CI preexistente para este ciclo.

## WP-028 — Gerente IA

### Autoridade canônica preservada

O WP-028 reutiliza o Gerente IA existente, incluindo:

- `ServicoGerenteIA` e runtime canônico;
- allowlist de tools já existente;
- `PreviewAcao` para operações mutáveis;
- confirmação humana explícita;
- fingerprint do preview;
- idempotency key;
- RBAC `gerente_ia.consultar` e `gerente_ia.executar_acao`;
- tenant/unidade obtidos exclusivamente da sessão assinada;
- identidade pública configurável do assistente.

Não foi criado segundo motor IA, segundo roteador, segundo sistema de tools, prompt alternativo ou política paralela de autonomia.

### Superfície Web implementada

- **Rota Web**: `/gerente-ia`.
- **Posição**: shell operacional, não área `/admin`, preservando o fato de que Gerente não recebe automaticamente `admin.acessar`.
- **HTTP**:
  - `POST /v1/gerente-ia/perguntar`;
  - `POST /v1/gerente-ia/tools`;
  - `POST /v1/gerente-ia/confirmar`.
- **Application Web**: façade sobre as autoridades existentes; nenhuma inteligência ou política crítica foi reconstruída no HTTP/React.
- **Sessão**: `fm_ai_session` / `AuthSessionRuntime` permanecem autoridade do contexto.
- **Anti-spoofing**: `X-Tenant-ID` e `X-Unit-ID` enviados pelo cliente não substituem tenant/unidade da sessão.
- **Tools mutáveis**: retornam preview; a ação só é efetivada no endpoint de confirmação com permissão apropriada, fingerprint e idempotência preservados.
- **Frontend**: página Next, workspace conversacional, cliente tipado e registro no Shell operacional.

### Arquivos principais WP-028

- `application/gerente_ia_web.py`
- `http_api/gerente_ia_web.py`
- `tests/api/test_gerente_ia_web_http_contract.py`
- `web/src/app/gerente-ia/page.tsx`
- `web/src/features/gerente-ia/components/GerenteIAWorkspace.tsx`
- `web/src/features/gerente-ia/services/gerente-ia-api.ts`
- `web/src/features/shell/module-registry.ts`
- `.github/workflows/web-parity-wp028-wp030-gate.yml`

### Certificação final WP-028

No head `04bcfe31cf4c46d3dabf6e341747ed7a0b8cb96d`:

- `py_compile`: PASS;
- Ruff: **All checks passed**;
- mypy: **Success: no issues found**;
- testes HTTP + regressão Gerente IA: **15/15 PASS**;
- ESLint: PASS;
- TypeScript: PASS;
- Next production build: PASS, incluindo rota `/gerente-ia`;
- `git diff --check`: PASS após remoção dos dois trailing whitespaces preexistentes em `ConfiguracaoWorkspace.tsx`;
- **Commercial Runtime Readiness V1**: SUCCESS;
- **Assistente Fase 4 Gate V1**: SUCCESS;
- **PR Superseded Runs Cleanup**: SUCCESS;
- **Web Parity WP028-WP030 Gate**: SUCCESS.

Não restou gate vermelho no WP-028.

**STATUS WP-028: MIGRADO / CONCLUÍDO / 100% VERDE.**

## Próximo bloco

O próximo bloco autorizado é **WP-029 — Pagamentos / PIX / Provedores**. Ele só deve avançar preservando o checkout, webhook, reconciliação, ledger, idempotência e demais autoridades financeiras já existentes, sem criar segundo fluxo de pagamentos.
