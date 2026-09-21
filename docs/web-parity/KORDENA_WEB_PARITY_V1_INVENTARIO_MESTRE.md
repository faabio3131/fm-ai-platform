# Kordena V1 - Inventário Mestre de Paridade Web (WEB-PARITY-V1)

**Baseline auditada:** `main @ 5a17b0c8a1cb6dad576ce5b089166748b138900c`
**Data original:** 08/09/2026
**Reconciliação:** 20/09/2026
**Versão do inventário:** 3.9 — WP-031A→L certificados
**Status:** DOCUMENTO MESTRE DE EXECUÇÃO

## 1. Regra constitucional deste inventário

Uma capacidade só pode ser marcada como **MIGRADO** quando a cadeia necessária estiver comprovada: domínio/core preservado, application/infra utilizável, contrato HTTP Web adequado, interface Next.js, isolamento tenant/unidade + RBAC/step-up quando aplicável e teste suficiente.

Existir no backend, possuir UI candidata ou ter E2E legado **não** significa estar certificado na nova Web. Itens explicitamente marcados como **IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO** não podem ser promovidos apenas por edição documental.

## 2. Diagnóstico executivo reconciliado

- Capacidades inventariadas: **33**.
- Estado canônico atual no ledger: **32 CERTIFIED**, **0 IMPLEMENTED_UNCERTIFIED** e **1 PENDING**.
- **WP-008** está certificado em `/garcom`; após o gate de implementação no HEAD `9daaacc9ef4754558ad570bd568a316367b9260d`, recebeu certificação independente no `Kordena V1 Non-Fiscal Master Gate` run `35380670582`, HEAD `74530f13c8bd9c95b61b9b9da4192094a230c2d3`.
- **WP-018** foi certificado em `/admin/dashboard` no SHA `b7a64b2dc5a47763a86fded903a15fd2be2cc23d`.
- **WP-012**, **WP-032** e **WP-033** estão tecnicamente certificados; o único WP deliberadamente pendente nesta rodada é **WP-031 Fiscal**.
- **WP-031 Fiscal** está em execução sequencial na PR #118: WP-031A→L estão implementados/certificados. O WP-031L fechou regressão e paridade de canais no HEAD `c990d1e92f87a6eea2110f4bc3141bff4321f6c8`, gate `WP-031L Regression Channel Parity` run `35556451970` SUCCESS, com matriz completa 28/28 workflows SUCCESS. O WP-031 permanece PENDING somente até o Master Gate.
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
- **WP-008 — Atendimento do Garçom mobile/tablet**: `/garcom` — CERTIFIED pelo Master Gate não fiscal.
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
| WP-008 | Atendimento do Garçom mobile/tablet | core/garcom + application/garcom_transacoes.py + application/garcom_fechamento.py | Router session-aware + gate dedicado + certificação independente no Master Gate | `/garcom` | CERTIFIED | Preservar implementação e autoridades canônicas. |
| WP-009 | Central de Pedidos omnichannel | core/central_pedidos + application | HTTP first-class certificado | `/pedidos` | MIGRADO | Preservar e integrar canais futuros nela. |
| WP-010 | Delivery Próprio | core/delivery + application + infra/delivery | Boundary certificado | `/delivery` | CERTIFIED | Preservar. |
| WP-011 | Expedição / Entrega | core/entrega + application | Boundary certificado | `/entrega` | CERTIFIED | Preservar. |
| WP-012 | Marketplaces / pedidos externos | core/marketplaces + adapters + bridge persistente para Pedido/Central canônicos | API `/v1/marketplaces` certificada; configuração fail-closed por homologação/evidência | `/pedidos` | CERTIFIED | Preservar; homologação externa de provider só com evidência real. |
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
| WP-031 | Fiscal / NFC-e / SAT | Fiscal V1 congelado `b336def47ad4f5188307102203f4e04b98406014` vendorizado; WP-031A→L implementados/certificados | Persistência, outbound, perfis, inbound, intake, procurement, financeiro/tributário, signer/gateway governado, Web/UX funcional, Cognitive Fiscal e paridade de canais certificados; sem homologação externa presumida | `/admin/fiscal` + `/admin/integracoes` + Core canônico | PARCIAL — A→L CERTIFIED / MASTER GATE PENDING | Executar WP-031 Master Gate. |
| WP-032 | Notificações Internas | core/notificacoes_internas + application/notificacoes_internas + diretório SQL cifrado | Superfície Web administrativa certificada, session-aware e tenant/unit-safe | Backoffice administrativo | CERTIFIED | Preservar serviço canônico; sem inbox/feed/badge paralelo. |
| WP-033 | Auditoria / Histórico administrativo | core/seguranca/auditoria.py + RepositorioAuditoriaSQLAlchemy | Consulta Backoffice read-only certificada, tenant-safe, com RBAC + step-up | Backoffice administrativo | CERTIFIED | Preservar auditoria canônica e não expor metadata interna/segredos. |

## 5. Capacidades históricas comprovadas na UI Streamlit

O `app.py` legado comprova abas para Engenharia de Cardápio, CRM/Resgate/Cashback, PDV/Pix, Estoque/Validades, Dashboard Financeiro, Assistente de Atendimento e AI FinOps, com abas condicionais para Central de Pedidos, KDS, Mesas/Comandas, Delivery Próprio e Impressão Operacional. As páginas separadas comprovam ainda Administração/Proprietário, Integrações e Credenciais, Atendimento do Garçom e Expedição/Entrega.

## 6. Gaps e pendências que ainda devem ser fechados

1. **WP-031 — Fiscal:** baseline V1 localizado, congelado e vendorizado. WP-031A→L estão implementados/certificados; o WP-031L foi certificado no gate `WP-031L Regression Channel Parity` run `35556451970`, HEAD `c990d1e92f87a6eea2110f4bc3141bff4321f6c8`, com 28/28 workflows SUCCESS. Somente o WP-031 Master Gate permanece pendente.
2. **Ledger histórico:** WP-001 a WP-007 possuem estados CERTIFIED sem campos de evidência exigidos pelo validador atual; reconciliar somente com evidência histórica real.

WP-008, WP-012, WP-018, WP-032 e WP-033 já possuem certificação posterior registrada neste documento e não são gaps CURRENT.

## 7. Ordem Mestre reconciliada

### Onda 1 — Shell Corporativo Unificado
**CERTIFICADA.**

### Onda 2 — Coração operacional
WP-008, WP-009, WP-010, WP-011 e WP-012 estão migrados/certificados conforme seus gates e o Master Gate não fiscal. Preservar as autoridades canônicas existentes.

### Onda 3 — Retaguarda
WP-013 a WP-026 estão migrados/certificados conforme os gates específicos e o Master Gate não fiscal; preservar Core/Application, sessão, RBAC, step-up, isolamento e autoridades existentes.

### Onda 4 — IA e Integrações
WP-027, WP-028 e WP-029 estão migrados/certificados no ciclo não fiscal; WP-019 também está certificado. Preservar governança, confirmações e observabilidade existentes.

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
6. **WP-031 → continuar sequência fiscal congelada**: A→L concluídos/certificados; Master Gate → Visual Premium permanecem na ordem vinculante.
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


## 15. Registro de certificação WP-012 — 18/09/2026

- Autoridades preservadas: `core/marketplaces`, `core/central_pedidos`, Pedido canônico, Outbox/Auditoria e Control Plane de integrações.
- Migration oficial: `0042_marketplace_orders_web_v1`; schema baseline e histórico reconciliados.
- Segurança: sessão assinada, tenant/unidade, RBAC, step-up administrativo para sincronização sensível e privilégios técnicos mínimos para criação/transição de Pedido.
- Transaction ownership reconciliado com `UnitOfWorkV1`; nenhuma segunda Central/Pedido/Pagamento foi criada.
- Gate `Web Parity WP012 Marketplaces` run `35369209616`: **SUCCESS** no SHA `e4ce2c1e2e315811425535c5ca74b5a56570050b`.
- Compile, Ruff, mypy, manifest, matriz dirigida, regressão Python completa, ESLint, TypeScript, testes Web, Next build e diff check: **SUCCESS**.
- Certificação é técnica/interna da integração Web. Nenhuma homologação real de iFood, Keeta, 99Food ou outro provider é declarada sem evidência externa.
- Próximo bloco autorizado neste ciclo não fiscal: **WP-032 — Notificações Internas Web**.


## 16. Certificação WP-032 e WP-033 — 18/09/2026

- **WP-032 — Notificações Internas Web:** CERTIFIED no SHA `c94d17ed85183c51ace803b5a97ecda84cbf447f`; run `35373830703` SUCCESS. Reutiliza diretório SQL cifrado e serviço canônico, sessão assinada, RBAC, step-up nas mutações, isolamento tenant/unidade e payload mascarado. Não cria inbox/feed/badge paralelo.
- **WP-033 — Auditoria Web:** CERTIFIED no SHA `01d5f7695cd72ab67cb7107c13c9e004de74f3d1`; run `35376561635` SUCCESS. Reutiliza `RepositorioAuditoriaSQLAlchemy`, consulta read-only scoped à unidade ativa, exige `admin.acessar` + `auditoria.visualizar` + step-up e não expõe metadata interna/segredos.
- Próxima etapa autorizada: **Auditoria Mestre V1 não fiscal + Audit & Fix + Gate Mestre Final**.


## 17. Auditoria Mestre V1 não fiscal — 18/09/2026

A Auditoria Mestre reconciliou código, rotas, ledger, checklist, evidências, gates de segurança e matriz integral.

### Resultado canônico

- 33 Work Packages oficiais.
- **32 CERTIFIED**.
- **0 IMPLEMENTED_UNCERTIFIED**.
- **1 PENDING deliberado nesta rodada: WP-031 Fiscal**.
- Visual Premium deliberadamente fora desta rodada.
- WP-008 recebeu certificação independente posterior no Master Gate.
- WP-023 a WP-027 receberam evidência consolidada adicional pelo Master Gate.

### Gate Mestre

Workflow: `Kordena V1 Non-Fiscal Master Gate`
Run: `35380670582`
HEAD certificado: `74530f13c8bd9c95b61b9b9da4192094a230c2d3`
Resultado: **SUCCESS**

Passaram: compile integral, Ruff auditado, mypy auditado, ledger, matriz independente WP-008, matriz WP-023–WP-027, matriz WP-032/WP-033, segurança/RBAC, regressão Python completa, ESLint Web completo, TypeScript, testes Node Web, Next production build e diff whitespace contra main.

Regressão Python completa: **1528 passed, 5 skipped, 99 warnings**.
Testes Node Web: **5 passed, 0 failed**.

Nenhum merge, deploy, force push ou alteração da main foi realizado.


## 18. WP-031A — Fiscal V1 System Design / Authority Freeze — 18/09/2026

- Baseline fiscal V1 congelado: `faabio3131/kordena-fiscal-engine@b336def47ad4f5188307102203f4e04b98406014`.
- System Design oficial: `docs/web-parity/WP031_FISCAL_V1_SYSTEM_DESIGN.md`.
- A integração não será limitada a emissão de vendas. O escopo oficial do WP-031 passa a conter **Outbound Fiscal + Inbound Fiscal + Fiscal Procurement + Fiscal Accounting/Control Bridge + Smart Fiscal Intake**.
- Autoridade outbound confirmada: `VendaFinanceira` / `venda.criada` após reconhecimento financeiro canônico.
- Estoque existente será preservado; NF-e recebida não equivale automaticamente a recebimento físico nem a pagamento.
- Leitura visual/IA existente será preservada como interpretação e sugestão, mas XML/DF-e oficial prevalece nos campos fiscais e confirmação humana governa o recebido físico.
- O Control Plane de integrações, RBAC, step-up, Secret Store/Vault, catálogo, pagamentos e auditoria existentes devem ser reutilizados; proibidas autoridades paralelas.
- A auditoria CURRENT localizou `compra.aprovar` no RBAC, mas não localizou autoridade materializada de pedido de compra/fornecedor/recebimento fiscal. WP-031G deve repetir discovery dirigido antes de criar a única autoridade de procurement necessária.
- Ordem oficial congelada: **WP-031 Fiscal completo -> Fiscal Master Gate -> Visual Premium final**.
- WP-031 permanece `PENDING` no ledger até implementação e certificação; este bloco fecha arquitetura/discovery, não promove readiness funcional.
