# Kordena V1 - Inventário Mestre de Paridade Web (WEB-PARITY-V1)

**Baseline auditada:** `main @ 5a17b0c8a1cb6dad576ce5b089166748b138900c`
**Data original:** 08/09/2026
**Reconciliação:** 18/09/2026
**Versão do inventário:** 2.6 — WP-018 certificado + sequência final de fechamento da V1
**Status:** DOCUMENTO MESTRE DE EXECUÇÃO

## 1. Regra constitucional deste inventário

Uma capacidade só pode ser marcada como **MIGRADO** quando a cadeia necessária estiver comprovada: domínio/core preservado, application/infra utilizável, contrato HTTP Web adequado, interface Next.js, isolamento tenant/unidade + RBAC/step-up quando aplicável e teste suficiente.

Existir no backend, possuir UI candidata ou ter E2E legado **não** significa estar certificado na nova Web. Itens explicitamente marcados como **IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO** não podem ser promovidos apenas por edição documental.

## 2. Diagnóstico executivo reconciliado

- Capacidades inventariadas: **33**.
- Estado canônico atual no ledger: **28 CERTIFIED**, **1 IMPLEMENTED_UNCERTIFIED** e **4 PENDING**.
- **WP-008** está implementado em `/garcom`; o gate de implementação do HEAD `9daaacc9ef4754558ad570bd568a316367b9260d` concluiu SUCCESS. Permanece `IMPLEMENTED_UNCERTIFIED` até certificação integral posterior.
- **WP-018** foi certificado em `/admin/dashboard` no SHA `b7a64b2dc5a47763a86fded903a15fd2be2cc23d`.
- **WP-012**, **WP-032** e **WP-033** são os gaps Web funcionais restantes.
- **WP-031 Fiscal** permanece PENDING na PR #118; o módulo já pronto deve ser localizado, provado como autoridade e apenas implantado/integrado, sem reconstrução.
- GAP HTTP/WEB/PÚBLICO: **0** — WP-030 foi concluído e certificado.
- A VERIFICAR: **0**.

A rota `/` usa Home/Dashboard comercial real dentro do Shell Corporativo Unificado. A Central de Pedidos está certificada em `/pedidos`. O Cardápio Digital público/autosserviço foi certificado em `/cardapio/{publicId}/{slug}`, com administração da publicação por unidade em `/admin/empresa`.

A retaguarda WP-013 a WP-017 está agora formalmente certificada. O WP-031 Fiscal integra oficialmente a Kordena V1 e deve ser concluído em fase própria antes da Arquitetura Visual Premium. A Arquitetura Visual Premium permanece bloqueada até a paridade funcional, a certificação das capacidades obrigatórias e o bloco fiscal da V1 serem encerrados.

## 3. Capacidades já migradas/preservadas

- **WP-001 — Login / SSO corporativo**: `/login`.
- **WP-002 — Escopo tenant/unidade + troca de unidade**: sessão assinada + seletor no Shell.
- **WP-003 — Roteamento por perfil/permissão**: navegação corporativa central filtrada por RBAC.
- **WP-004 — Home / Dashboard / Shell corporativo**: Shell persistente + dashboard real em `/`.
- **WP-005 — PDV Touch**: `/pdv`.
- **WP-006 — Salão / Mesas / Comandas**: `/salao`.
- **WP-007 — KDS / Cozinha**: `/kds`.
- **WP-008 — Atendimento do Garçom mobile/tablet**: `/garcom` — implementação concluída, aguardando certificação integral.
- **WP-009 — Central de Pedidos omnichannel**: `/pedidos`.
- **WP-013 — Catálogo administrativo básico**: `/admin/catalogo`.
- **WP-014 — Engenharia de Cardápio + Ficha Técnica**: `/admin/catalogo`.
- **WP-015 — Estoque / Almoxarifado / Validades**: `/admin/estoque`.
- **WP-016 — CRM / Clientes / Cashback**: `/admin/crm`.
- **WP-017 — Marketing / Resgate / Campanhas**: `/admin/crm`.
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
| WP-008 | Atendimento do Garçom mobile/tablet | core/garcom + application/garcom_transacoes.py + application/garcom_fechamento.py | Router session-aware implementado e gate dedicado SUCCESS | `/garcom` | IMPLEMENTED_UNCERTIFIED | Preservar implementação; certificação integral posterior sem reconstrução. |
| WP-009 | Central de Pedidos omnichannel | core/central_pedidos + application | HTTP first-class certificado | `/pedidos` | MIGRADO | Preservar e integrar canais futuros nela. |
| WP-010 | Delivery Próprio | core/delivery + application + infra/delivery | Boundary certificado | `/delivery` | CERTIFIED | Preservar. |
| WP-011 | Expedição / Entrega | core/entrega + application | Boundary certificado | `/entrega` | CERTIFIED | Preservar. |
| WP-012 | Marketplaces / pedidos externos | core/marketplaces + adapters | Sem superfície Web certificada | — | GAP HTTP/WEB | Migrar sem criar segunda Central de Pedidos. |
| WP-013 | Catálogo administrativo básico | catálogo existente + WP-014 | Boundary Web certificado | `/admin/catalogo` | MIGRADO | Preservar catálogo canônico, sessão e step-up. |
| WP-014 | Engenharia de Cardápio + Ficha Técnica | legacy_cardapio_transacoes + legacy_cardapio_gemini | Ficha/Gemini/preço sugerido certificados | `/admin/catalogo` | MIGRADO | Preservar regra original e aplicação explícita do preço sugerido. |
| WP-015 | Estoque / Almoxarifado / Validades | core/estoque + boundaries legados governados | HTTP/Web certificados | `/admin/estoque` | MIGRADO | Preservar; lote físico/FEFO seguem fora do escopo atual. |
| WP-016 | CRM / Clientes / Cashback | core/crm + application/crm_cashback_comercial + ledger canônico | HTTP session-aware certificado | `/admin/crm` | MIGRADO | Preservar ledger, mapping, isolamento e step-up. |
| WP-017 | Marketing / Resgate / Campanhas | application/crm_marketing_comercial + infra/crm + Outbox V1 + UnitOfWorkV1 | Boundary governado e replay-safe certificado | `/admin/crm` | MIGRADO | Preservar consentimento, escopo e proteção at-most-once do efeito externo. |
| WP-018 | Dashboard Financeiro / Indicadores | administracao_proprietario.painel_executivo | HTTP read model certificado com step-up administrativo | `/admin/dashboard` | CERTIFIED | Preservar. |
| WP-019 | AI FinOps | core/ai_finops + read model | HTTP read-only certificado | `/admin/ai-finops` | CERTIFIED | Preservar; não inventar custos. |
| WP-020 | Área Proprietário / Backoffice | registrar_acesso + registry/guards | Landing/auditoria certificadas | `/admin` | CERTIFIED | Preservar. |
| WP-021 | Step-up administrativo | auth + AdminStepUpGuard | Elevação temporária existente | `/admin` | MIGRADO | Preservar como barreira única. |
| WP-022 | Empresa / Matriz / Filiais / Unidades | core/administracao + AplicacaoAdministracaoProprietarioV1 | Consulta/edição/criação certificadas | `/admin/empresa` | CERTIFIED | Preservar; não reconstruir. |
| WP-023 | Usuários / Papéis / Permissões | AplicacaoAdministracaoProprietarioV1 + segurança | GET/POST/PUT Web concluídos | `/admin/usuarios` | MIGRADO | Preservar. |
| WP-024 | Parâmetros Financeiros | administracao_proprietario + pagamentos | GET/PUT canônicos | `/admin/configuracao` | MIGRADO | Preservar; segredos permanecem WP-026. |
| WP-025 | Impressão Operacional / Configuração | core/impressao + AplicacaoImpressaoV1 | Operação/configuração Web concluída | `/admin/impressao` | MIGRADO | Preservar KDS/PDV e adapter físico canônico. |
| WP-026 | Integrações e Credenciais | core/integracoes + AplicacaoIntegracoesAdminV1 + vault | Console session-aware concluído | `/admin/integracoes` | MIGRADO | Preservar cofre/step-up/healthcheck/homologação. |
| WP-027 | Assistente de Atendimento | core/assistente_atendimento + application/assistente_* | Administração session-aware concluída | `/admin/assistente-atendimento` | MIGRADO | Preservar identidade configurável por tenant/unidade. |
| WP-028 | Gerente IA | core/gerente_ia + runtime/tools canônicos | façade session-aware certificada | `/gerente-ia` | MIGRADO | Preservar preview/confirmação/idempotência. |
| WP-029 | Pagamentos / PIX / Provedores | core/pagamentos + PagBank/reconciliação/runtime | Observabilidade/conciliação certificadas | `/pagamentos` | MIGRADO | Preservar checkout/ledger/PIX/webhook canônicos. |
| WP-030 | Cardápio Digital público / Autosserviço | Catálogo Delivery + checkout canônico + publicação dedicada por unidade | identidade pública + catálogo + checkout públicos certificados | `/cardapio/{publicId}/{slug}` | MIGRADO | Preservar `public_id` opaco, configuração por unidade e checkout único. |
| WP-031 | Fiscal / NFC-e / SAT | módulo fiscal pronto ainda fora do tree da PR #118; autoridade de origem deve ser localizada antes da integração | Sem superfície fiscal certificada na PR #118 | — | PENDING | Localizar/provar o módulo pronto, implantar/integrar, testar, homologar e certificar; proibido reconstruir em paralelo. |
| WP-032 | Notificações Internas | core/notificacoes_internas + application/notificacoes_internas | GAP administrativo | — | OBRIGATÓRIA PARA V1.0 / PENDENTE | Expor destinatários, preferências e alertas; sem inbox/feed/badge genérico. |
| WP-033 | Auditoria / Histórico administrativo | repositórios de auditoria existentes | Sem consulta Web certificada | — | GAP HTTP/WEB | Criar consulta Backoffice read-only, tenant-safe e sem segredos. |

## 5. Capacidades históricas comprovadas na UI Streamlit

O `app.py` legado comprova abas para Engenharia de Cardápio, CRM/Resgate/Cashback, PDV/Pix, Estoque/Validades, Dashboard Financeiro, Assistente de Atendimento e AI FinOps, com abas condicionais para Central de Pedidos, KDS, Mesas/Comandas, Delivery Próprio e Impressão Operacional. As páginas separadas comprovam ainda Administração/Proprietário, Integrações e Credenciais, Atendimento do Garçom e Expedição/Entrega.

## 6. Gaps e pendências que ainda devem ser fechados

1. **WP-008 — Garçom:** implementação e gate dedicado concluídos; permanece `IMPLEMENTED_UNCERTIFIED` até certificação integral posterior.
2. **WP-018 — Dashboard Financeiro:** CERTIFIED; step-up HTTP corrigido e gate integral verde.
3. **WP-012 — Marketplaces:** backend/adapters/testes existem; falta implantação HTTP/Web integrada à Central de Pedidos WP-009.
4. **WP-032 — Notificações Internas:** Core/Application/Infra existentes; falta superfície administrativa Web.
5. **WP-033 — Auditoria/Histórico:** autoridade de auditoria existe; falta consulta Backoffice read-only tenant-safe.
6. **WP-031 — Fiscal:** módulo pronto deve ser localizado fora do tree atual, importado/implantado e integrado; não reconstruir. A V1 não fecha sem teste, homologação e certificação fiscal.
7. **Ledger histórico:** WP-001 a WP-007 possuem estados CERTIFIED sem campos de evidência exigidos pelo validador atual; reconciliar somente com evidência histórica real.

## 7. Ordem Mestre reconciliada

### Onda 1 — Shell Corporativo Unificado
**CERTIFICADA.**

### Onda 2 — Coração operacional
WP-009 certificado. WP-010 e WP-011 permanecem em reconciliação/certificação mestre própria. WP-012 e WP-008 ainda requerem migração Web.

### Onda 3 — Retaguarda
WP-013, WP-014, WP-015, WP-016 e WP-017 estão **MIGRADOS / CERTIFICADOS / 100% VERDES**. WP-018, WP-019, WP-020 e WP-022 possuem implementação presente aguardando certificação integrada. WP-021 e WP-023 a WP-026 estão migrados.

### Onda 4 — IA e Integrações
WP-027, WP-028 e WP-029 estão migrados. WP-019 possui implementação presente aguardando certificação integrada.

### Onda pública
WP-030 **CERTIFICADO / 100% VERDE** no HEAD funcional `c74595637deb6e31a578e95975445d34064a6b07`.

### Onda Fiscal — obrigatória na V1
WP-031 — Fiscal / NFC-e / SAT integra oficialmente a Kordena V1. Deve possuir fase própria de implementação, integração, testes e certificação depois do fechamento das pendências funcionais obrigatórias e **antes da Arquitetura Visual Premium**. A V1 não pode ser declarada 100% concluída enquanto o WP-031 estiver pendente.

### Sequência final oficial de execução

1. **WP-008 → fechar gate** — gate dedicado de implementação já concluiu SUCCESS no HEAD `9daaacc9ef4754558ad570bd568a316367b9260d`; certificação integral permanece posterior.
2. **WP-018 → certificar** — CONCLUÍDO/CERTIFIED no SHA `b7a64b2dc5a47763a86fded903a15fd2be2cc23d`.
3. **WP-012 → implantar Web** sobre a Central de Pedidos existente.
4. **WP-032 → implantar Web** reutilizando Notificações Internas canônicas.
5. **WP-033 → implantar Web** read-only sobre auditoria canônica.
6. **WP-031 → implantar Fiscal pronto**, após localizar e provar a autoridade do módulo existente.
7. **Auditoria Mestre V1 completa**.
8. **Gate 100% funcional**.
9. **Visual Premium final**, somente após os gates anteriores.

Cada bloco só autoriza o seguinte quando seus testes e gates aplicáveis estiverem 100% verdes; falhas devem ser corrigidas antes de avançar.

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
- `docs/web-parity/WP010_WP011_CERTIFICACAO_INTEGRADA.md`
- `docs/web-parity/WP013_WP014_CERTIFICACAO_INTEGRADA.md`
- `docs/web-parity/WP015_CERTIFICACAO_INTEGRADA.md`
- `docs/web-parity/WP016_CRM_CASHBACK_CERTIFICACAO.md`
- `docs/web-parity/WP017_MARKETING_RESGATE_CERTIFICACAO.md`
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
- WP-008, WP-012, WP-032 e WP-033 permaneceram funcionalmente pendentes na Web.
- Na reconciliação de 15/09/2026, WP-031 ainda constava como BACKLOG FUTURO; essa classificação foi posteriormente substituída pela decisão formal de incluí-lo na V1.
- PR #118 permaneceu OPEN/DRAFT e não mergeada; sem deploy/produção.

## 12. Registro de reconciliação de 16/09/2026

- WP-013 e WP-014 foram reconciliados como MIGRADO/CERTIFICADO conforme `WP013_WP014_CERTIFICACAO_INTEGRADA.md`; a matriz direcionada ficou 23/23 e a divergência histórica do preço sugerido foi corrigida sem criar catálogo paralelo.
- WP-015 foi reconciliado como MIGRADO/CERTIFICADO conforme `WP015_CERTIFICACAO_INTEGRADA.md`; gate técnico `3daaddf7b97236ba0b80c13f0e36c91025f22a0c`, 10/10 direcionados e 1503 PASS / 5 SKIP / 0 FAIL.
- WP-016 foi reconciliado como MIGRADO/CERTIFICADO conforme `WP016_CRM_CASHBACK_CERTIFICACAO.md`; gate técnico `d0fe8480c58449c54024c2dbb1fd9ca6b8747746`, 17/17 direcionados e 1505 PASS / 5 SKIP / 0 FAIL.
- WP-017 foi corrigido e certificado no HEAD técnico `f059abe30e69cc1981188a76c040b99dba59874a`: 22/22 direcionados, 1506 PASS / 5 SKIP / 0 FAIL, Ruff/mypy/ESLint/TypeScript/build/diff verdes.
- A idempotência de marketing passou a reutilizar a Outbox V1 como ledger durável do efeito externo, com reserva persistida antes do POST; replay e resultado externo incerto não geram retry automático perigoso.
- O ownership de commit/rollback foi mantido no `UnitOfWorkV1`; o fitness gate AF03 permaneceu intacto e verde.
- WP-018, WP-019, WP-020 e WP-022 não foram promovidos por associação; permanecem aguardando certificação própria.
- WP-008, WP-012, WP-032 e WP-033 continuam funcionalmente pendentes na Web.
- **Decisão formal do proprietário:** WP-031 deixa de ser backlog futuro e passa a integrar obrigatoriamente a Kordena V1 como bloco fiscal próprio, a ser concluído e certificado antes da Arquitetura Visual Premium.
- Nenhuma V2 foi iniciada.

---
**Regra de mudança:** este documento é vivo e versionado por baseline. Qualquer nova descoberta deve atualizar a linha correspondente antes de iniciar implementação que dependa dela. A Arquitetura Visual Premium só reabre depois do Gate de Paridade Web, da certificação das capacidades obrigatórias e da conclusão/certificação do WP-031 Fiscal da V1.
## 13. Registro de reconciliação de 18/09/2026

- WP-008 foi implementado em `/garcom` com sessão única, fechamento flexível por unidade, couvert artístico, autoridade financeira canônica, idempotência e concorrência.
- Gate `Web Parity WP008 Implementation Gates` no HEAD `9daaacc9ef4754558ad570bd568a316367b9260d`: SUCCESS após correção documental de whitespace.
- O ledger continua sendo a autoridade de estado; Inventário e Checklist foram reconciliados para remover estados narrativos antigos.
- Sequência final de fechamento da V1 congelada: WP-008 gate → WP-018 certificar → WP-012 Web → WP-032 Web → WP-033 Web → WP-031 Fiscal pronto → Auditoria Mestre → Gate 100% funcional → Visual Premium.
- Fiscal não deve ser reconstruído: localizar a implementação pronta, provar sua autoridade e executar apenas implantação/integração, testes, homologação e certificação.
- PR #118 permanece OPEN/DRAFT; nenhum merge ou deploy autorizado.

## 14. Registro de certificação WP-018 — 18/09/2026

- Gap encontrado: endpoint do painel executivo aceitava administrador sem step-up HTTP ativo.
- Correção: `/v1/admin/painel-executivo` passou a exigir elevação administrativa ativa além de `admin.acessar` e `financeiro.visualizar`.
- Matriz dirigida: **18 passed / 0 failed**.
- Regressão Python completa: **1517 passed / 5 skipped / 0 failed**.
- Ruff, mypy, ESLint, TypeScript, navegação Backoffice, Next build e diff check: **SUCCESS**.
- WP-018 promovido para **CERTIFIED** com evidência do run `35354337053`.
- Próximo bloco autorizado: **WP-012 — Marketplaces / pedidos externos**.
