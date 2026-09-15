# Kordena V1 - Inventário Mestre de Paridade Web (WEB-PARITY-V1)

**Baseline auditada:** `main @ 5a17b0c8a1cb6dad576ce5b089166748b138900c`
**Data original:** 08/09/2026
**Reconciliação:** 15/09/2026
**Versão do inventário:** 2.2 — reconciliação pós-certificação WP-030
**Status:** DOCUMENTO MESTRE DE EXECUÇÃO

## 1. Regra constitucional deste inventário

Uma capacidade só pode ser marcada como **MIGRADO** quando a cadeia necessária estiver comprovada: domínio/core preservado, application/infra utilizável, contrato HTTP Web adequado, interface Next.js, isolamento tenant/unidade + RBAC/step-up quando aplicável e teste suficiente.

Existir no backend, possuir UI candidata ou ter E2E legado **não** significa estar certificado na nova Web. Itens explicitamente marcados como **IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO** não podem ser promovidos apenas por edição documental.

## 2. Diagnóstico executivo reconciliado

- Capacidades inventariadas: **33**.
- Totalmente migradas/preservadas: **17** — WP-001 a WP-007, WP-009, WP-021, WP-023 a WP-030.
- IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO: **11** — WP-010, WP-011, WP-013 a WP-020 e WP-022.
- GAP HTTP/WEB ainda sem superfície certificada: **3** — WP-008, WP-012 e WP-033.
- GAP HTTP/WEB ADMINISTRATIVO obrigatório para V1.0: **1** — WP-032.
- BACKLOG FUTURO fora da migração conservativa Web V1: **1** — WP-031.
- GAP HTTP/WEB/PÚBLICO: **0** — WP-030 foi concluído e certificado.
- A VERIFICAR: **0**.

A rota `/` usa Home/Dashboard comercial real dentro do Shell Corporativo Unificado. A Central de Pedidos está certificada em `/pedidos`. O Cardápio Digital público/autosserviço foi certificado em `/cardapio/{publicId}/{slug}`, com administração da publicação por unidade em `/admin/empresa`.

A Arquitetura Visual Premium permanece bloqueada até a paridade funcional/certificação das capacidades obrigatórias remanescentes ser encerrada.

## 3. Capacidades já migradas/preservadas

- **WP-001 — Login / SSO corporativo**: `/login`.
- **WP-002 — Escopo tenant/unidade + troca de unidade**: sessão assinada + seletor no Shell.
- **WP-003 — Roteamento por perfil/permissão**: navegação corporativa central filtrada por RBAC.
- **WP-004 — Home / Dashboard / Shell corporativo**: Shell persistente + dashboard real em `/`.
- **WP-005 — PDV Touch**: `/pdv`.
- **WP-006 — Salão / Mesas / Comandas**: `/salao`.
- **WP-007 — KDS / Cozinha**: `/kds`.
- **WP-009 — Central de Pedidos omnichannel**: `/pedidos`.
- **WP-021 — Step-up administrativo / reautenticação**: guard de `/admin`.
- **WP-023 — Usuários / Papéis / Permissões**: `/admin/usuarios`.
- **WP-024 — Parâmetros Financeiros**: `/admin/configuracao`.
- **WP-025 — Impressão Operacional**: `/admin/impressao`.
- **WP-026 — Integrações e Credenciais**: `/admin/integracoes`.
- **WP-027 — Assistente de Atendimento**: `/admin/assistente-atendimento`.
- **WP-028 — Gerente IA**: `/gerente-ia`.
- **WP-029 — Pagamentos / PIX / Provedores**: `/pagamentos`.
- **WP-030 — Cardápio Digital público / Autosserviço**: `/cardapio/{publicId}/{slug}` + administração por unidade em `/admin/empresa`.

## 4. Matriz mestre de paridade reconciliada

| ID | Capacidade | Evidência/autoridade | HTTP/Web atual | Next.js atual | Status | Próxima ação obrigatória |
|---|---|---|---|---|---|---|
| WP-001 | Login / SSO corporativo | auth/session | Contrato dedicado e cookie assinado | `/login` | MIGRADO | Preservar. |
| WP-002 | Escopo tenant/unidade + troca | auth/operational scope | Sessão assinada governa tenant/unidade | Shell | MIGRADO | Preservar em todos os módulos. |
| WP-003 | Roteamento por perfil/permissão | segurança/RBAC + registry | Navegação governada | Shell | MIGRADO | Preservar registry como fonte única. |
| WP-004 | Home / Dashboard / Shell | UnifiedAppShell + DashboardHome | Shell persistente | `/` | MIGRADO | Preservar; Visual Premium é fase posterior. |
| WP-005 | PDV Touch | core/pdv + application | Router session-aware | `/pdv` | MIGRADO | Preservar. |
| WP-006 | Salão / Mesas / Comandas | core/salão + application | Router session-aware | `/salao` | MIGRADO | Preservar. |
| WP-007 | KDS / Cozinha | core/kds + application | Router session-aware | `/kds` | MIGRADO | Preservar. |
| WP-008 | Atendimento do Garçom mobile/tablet | core/garcom + application/garcom_transacoes.py | Sem superfície Web certificada | — | GAP HTTP/WEB | Criar contrato session-aware e rota touch-first sem duplicar domínio. |
| WP-009 | Central de Pedidos omnichannel | core/central_pedidos + application | HTTP first-class certificado | `/pedidos` | MIGRADO | Preservar e integrar canais futuros nela. |
| WP-010 | Delivery Próprio | core/delivery + application + infra/delivery | Implementação candidata presente | `/delivery` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Executar certificação integrada/Smoke Mestre; não reconstruir. |
| WP-011 | Expedição / Entrega | core/entrega + application | Implementação candidata presente | `/entrega` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Executar certificação integrada/Smoke Mestre; não reconstruir. |
| WP-012 | Marketplaces / pedidos externos | core/marketplaces + adapters | Sem superfície Web certificada | — | GAP HTTP/WEB | Migrar sem criar segunda Central de Pedidos. |
| WP-013 | Catálogo administrativo básico | catálogo existente + WP-014 | Capacidades presentes em `/admin/catalogo` | `/admin/catalogo` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada; reconciliação comportamental de preço já registrada. |
| WP-014 | Engenharia de Cardápio + Ficha Técnica | legacy_cardapio_transacoes + legacy_cardapio_gemini | Boundary Web presente | `/admin/catalogo` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificar sem alterar regra original. |
| WP-015 | Estoque / Almoxarifado / Validades | core/estoque + boundaries legados governados | HTTP/Web presentes | `/admin/estoque` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificar; lote físico/FEFO seguem fora do escopo atual. |
| WP-016 | CRM / Clientes / Cashback | core/crm + application/crm_cashback_comercial | HTTP session-aware presente | `/admin/crm` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada. |
| WP-017 | Marketing / Resgate / Campanhas | application/crm_marketing_comercial + infra/crm | Boundary governado presente | `/admin/crm` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada; preservar consentimento/idempotência. |
| WP-018 | Dashboard Financeiro / Indicadores | administracao_proprietario.painel_executivo | HTTP read model presente | `/admin/dashboard` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada. |
| WP-019 | AI FinOps | core/ai_finops + read model | HTTP read-only presente | `/admin/ai-finops` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada; não inventar custos. |
| WP-020 | Área Proprietário / Backoffice | registrar_acesso + registry/guards | Landing/auditoria presentes | `/admin` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada/Smoke Mestre. |
| WP-021 | Step-up administrativo | auth + AdminStepUpGuard | Elevação temporária existente | `/admin` | MIGRADO | Preservar como barreira única. |
| WP-022 | Empresa / Matriz / Filiais / Unidades | core/administracao + AplicacaoAdministracaoProprietarioV1 | Consulta/edição/criação presentes | `/admin/empresa` | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Certificação integrada/Smoke Mestre; não reconstruir. |
| WP-023 | Usuários / Papéis / Permissões | AplicacaoAdministracaoProprietarioV1 + segurança | GET/POST/PUT Web concluídos | `/admin/usuarios` | MIGRADO | Preservar. |
| WP-024 | Parâmetros Financeiros | administracao_proprietario + pagamentos | GET/PUT canônicos | `/admin/configuracao` | MIGRADO | Preservar; segredos permanecem WP-026. |
| WP-025 | Impressão Operacional / Configuração | core/impressao + AplicacaoImpressaoV1 | Operação/configuração Web concluída | `/admin/impressao` | MIGRADO | Preservar KDS/PDV e adapter físico canônico. |
| WP-026 | Integrações e Credenciais | core/integracoes + AplicacaoIntegracoesAdminV1 + vault | Console session-aware concluído | `/admin/integracoes` | MIGRADO | Preservar cofre/step-up/healthcheck/homologação. |
| WP-027 | Assistente de Atendimento | core/assistente_atendimento + application/assistente_* | Administração session-aware concluída | `/admin/assistente-atendimento` | MIGRADO | Preservar identidade configurável por tenant/unidade. |
| WP-028 | Gerente IA | core/gerente_ia + runtime/tools canônicos | façade session-aware certificada | `/gerente-ia` | MIGRADO | Preservar preview/confirmação/idempotência. |
| WP-029 | Pagamentos / PIX / Provedores | core/pagamentos + PagBank/reconciliação/runtime | Observabilidade/conciliação certificadas | `/pagamentos` | MIGRADO | Preservar checkout/ledger/PIX/webhook canônicos. |
| WP-030 | Cardápio Digital público / Autosserviço | Catálogo Delivery + checkout canônico + publicação dedicada por unidade | identidade pública + catálogo + checkout públicos certificados | `/cardapio/{publicId}/{slug}` | MIGRADO | Preservar `public_id` opaco, configuração por unidade e checkout único. |
| WP-031 | Fiscal / NFC-e / SAT | decisão do proprietário | Fora do escopo | — | BACKLOG FUTURO | Não implementar nesta migração; sem novo domínio fiscal. |
| WP-032 | Notificações Internas | core/notificacoes_internas + application/notificacoes_internas | GAP administrativo | — | OBRIGATÓRIA PARA V1.0 / PENDENTE | Expor destinatários, preferências e alertas; sem inbox/feed/badge genérico. |
| WP-033 | Auditoria / Histórico administrativo | repositórios de auditoria existentes | Sem consulta Web certificada | — | GAP HTTP/WEB | Criar consulta Backoffice read-only, tenant-safe e sem segredos. |

## 5. Capacidades históricas comprovadas na UI Streamlit

O `app.py` legado comprova abas para Engenharia de Cardápio, CRM/Resgate/Cashback, PDV/Pix, Estoque/Validades, Dashboard Financeiro, Assistente de Atendimento e AI FinOps, com abas condicionais para Central de Pedidos, KDS, Mesas/Comandas, Delivery Próprio e Impressão Operacional. As páginas separadas comprovam ainda Administração/Proprietário, Integrações e Credenciais, Atendimento do Garçom e Expedição/Entrega.

## 6. Gaps e pendências que ainda devem ser fechados

1. **Implementados mas não certificados integralmente:** WP-010, WP-011, WP-013 a WP-020 e WP-022. Não reconstruir; executar ciclo de certificação/Smoke Mestre e corrigir apenas gaps comprovados.
2. **Ainda sem superfície Web certificada:** WP-008, WP-012 e WP-033.
3. **Obrigatório V1.0 ainda pendente:** WP-032 — Notificações Internas.
4. **Backlog futuro deliberado:** WP-031 — Fiscal/NFC-e/SAT, fora desta migração.
5. **Dados de homologação:** escopos sem vínculo seguro com loja legada devem continuar fail-closed; o provisionamento é requisito de ambiente, não motivo para enfraquecer isolamento.
6. **Identidade do assistente:** permanece configurável por tenant/unidade; nenhum nome fixo histórico deve virar identidade de produto.

## 7. Ordem Mestre reconciliada

### Onda 1 — Shell Corporativo Unificado
**CERTIFICADA.**

### Onda 2 — Coração operacional
WP-009 certificado. WP-010 e WP-011 possuem implementação candidata e aguardam certificação integrada. WP-012 e WP-008 ainda requerem migração Web.

### Onda 3 — Retaguarda
WP-013 a WP-020 e WP-022 possuem implementação presente aguardando certificação integrada. WP-021 e WP-023 a WP-026 estão migrados.

### Onda 4 — IA e Integrações
WP-027, WP-028, WP-029 estão migrados. WP-019 possui implementação presente aguardando certificação integrada.

### Onda pública
WP-030 **CERTIFICADO / 100% VERDE** no HEAD funcional `c74595637deb6e31a578e95975445d34064a6b07`.

### Próximos blocos formais
- WP-031: somente auditoria/no-op de backlog futuro; não implementar Fiscal.
- WP-032: implementar superfície administrativa de Notificações Internas.
- WP-033: implementar consulta administrativa de Auditoria/Histórico sem segredos.

Antes de declarar a Web V1 100%, executar auditoria/certificação das implementações históricas ainda marcadas como aguardando certificação e concluir WP-008/WP-012/WP-032/WP-033 conforme o inventário.

## 8. Gate obrigatório por PR

Cada PR do WEB-PARITY-V1 deve: (a) citar IDs WP afetados; (b) atualizar este inventário; (c) preservar regras de negócio no Core/Application; (d) usar sessão assinada e RBAC/step-up; (e) adicionar/atualizar testes; (f) manter lint, typecheck/build e regressão verdes; (g) não promover para MIGRADO sem evidências da cadeia inteira.

## 9. Definition of Done de uma capacidade

- Domínio/core identificado e preservado.
- Application/infra reutilizada, sem duplicar regra de negócio no React.
- HTTP first-class session-aware ou boundary público governado quando aplicável.
- Tenant/unit safe e idempotente quando aplicável.
- RBAC e step-up aplicados conforme risco.
- Rota Next.js completa com estados necessários.
- Testes unitários/HTTP/integrados suficientes.
- Gates de lint/typecheck/build/regressão verdes.
- Smoke funcional/manual quando exigido pelo ciclo.
- Linha WP atualizada para MIGRADO somente após evidência.

## 10. Evidências principais auditadas

- `web/src/app/`
- `web/src/features/`
- `web/src/app/admin/`
- `http_api/`
- `core/`
- `application/`
- `infra/`
- `migrations/`
- `tests/`
- `docs/web-parity/WP020_WP022_CICLO_2X2.md`
- `docs/web-parity/WP023_WP024_CICLO_2X2.md`
- `docs/web-parity/WP025_WP026_CICLO_2X2.md`
- `docs/web-parity/WP027_WP028_CICLO_2X2.md`
- `docs/web-parity/WP029_WP030_CICLO_2X2.md`

## 11. Registro de reconciliação de 15/09/2026

- WP-030 saiu do bloqueio após decisão explícita do proprietário: estrutura de cliente/matriz/filial/unidade deve ser totalmente configurável, sem mudança de código por contratação.
- Foi implementada identidade pública dedicada por unidade com `public_id` opaco, slug configurável, publicação/despublicação, migration oficial `0041`, resolução tenant-safe e administração em `/admin/empresa`.
- O autosserviço reutiliza `ComandoCheckoutV1 -> executar_checkout_v1`; não existe segundo Pedido/Checkout/Pagamento/Catálogo.
- Certificação funcional WP-030 no HEAD `c74595637deb6e31a578e95975445d34064a6b07`: **61 passed, 0 failed**, Ruff PASS, mypy PASS, ESLint PASS, TypeScript PASS, Next production build PASS, `git diff --check` PASS.
- No mesmo HEAD: `Web Parity WP028-WP030 Gate`, `Commercial Runtime Readiness V1`, `PR Superseded Runs Cleanup` e `Assistente Fase 4 Gate V1` concluíram SUCCESS.
- A auditoria retrospectiva encontrou estados mestres antigos para WP-024 a WP-029; eles foram reconciliados como MIGRADO conforme checklist/documentos posteriores.
- A auditoria também confirmou pendência legítima de certificação para WP-010, WP-011, WP-013 a WP-020 e WP-022. Esses itens **não** foram promovidos artificialmente.
- WP-008, WP-012, WP-032 e WP-033 permanecem funcionalmente pendentes na Web.
- WP-031 permanece BACKLOG FUTURO, sem implementação Fiscal autorizada.
- PR #118 permanece OPEN/DRAFT e não mergeada; sem deploy/produção.

---
**Regra de mudança:** este documento é vivo e versionado por baseline. Qualquer nova descoberta deve atualizar a linha correspondente antes de iniciar implementação que dependa dela. A arquitetura visual premium só reabre depois do Gate de Paridade Web e da certificação das capacidades obrigatórias.