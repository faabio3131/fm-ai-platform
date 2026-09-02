# Inventário — Fase 7 — Salão / Garçom — Cutover Comercial Canônico

**Status:** FASE 7 FECHADA TECNICAMENTE / COMMERCIAL_CANDIDATE — FASE 8 LIBERADA  
**Issue:** #71  
**Base:** `main@0feb5594655f30e0c26fc72754bdaa03c3e88ddd`  
**Branch:** `recovery/v1-fase7-salao-garcom-commercial-cutover`

## 1. Autoridade e gate

Autoridades consultadas:
- Documento Mestre — FASE 7, §§2, 3, 3.0.1, 3.0.2 e 3.0.3;
- System Design Master;
- Programa RECOVERY #62;
- AGENTS.md e skills de System Design/Validation/Git.

Gate funcional obrigatório:
`mesa -> comanda -> pedido/itens -> produção/KDS -> fechamento -> pagamento`
executado no runtime comercial, em navegador/dispositivo, com identidade e
permissões reais.

## 2. Patrimônio válido já existente

### Salão
Já existem e devem ser reutilizados:
- domínio de Mesa/Comanda/Participante/Plano de Fechamento/Eventos;
- `RepositorioSalaoSQLAlchemy`;
- `ServicoSalao`;
- `AplicacaoSalaoV1` com UoW externo;
- optimistic locking/CAS;
- idempotência por evento;
- vínculo com Pedido canônico;
- validação de Pagamento canônico antes de projetar pagamento na comanda;
- tabelas `mesas_v1`, `comandas_v1`,
  `comanda_participantes_v1`, `comanda_pedidos_v1`,
  `comanda_parcelas_fechamento_v1`,
  `comanda_pagamentos_confirmados_v1` e `eventos_salao_v1`.

### Garçom
Já existem e devem ser reutilizados:
- `ServicoGarcom`;
- `AplicacaoGarcomV1` com `UnitOfWorkV1`;
- painel mobile/tablet;
- filtro por responsável;
- bloqueio `comanda_fora_alcada`;
- avisos de pedido pronto derivados do KDS;
- abertura de comanda, participante, vínculo de Pedido e solicitação de conta.

### Persistência
A migration oficial `0012_restaurant_operations_runtime_v1` já cria
`SalaoBase` no runner canônico e é executável no runtime comercial,
inclusive PostgreSQL.

Portanto:
- **não criar migration F7 nova sem descoberta de schema drift real**;
- `migrations/salao_v1.py` permanece harness histórico de SQLite/teste e não
  deve ser chamado no runtime comercial.

## 3. Blockers atuais confirmados no código de main

### B7-01 — contexto artificial no Salão — CRÍTICO
`core/salao/ui_streamlit.py`:
- importa `contexto_salao_teste`;
- cria contexto com papel fixo `gerente`;
- ignora a identidade autenticada do runtime.

**Target:** contexto vindo exclusivamente de `IdentidadeUsuario.contexto()`
no runtime comercial. Contexto injetado só em E2E quando
`FM_AI_TEST_MODE=1`.

### B7-02 — schema de teste no Salão — CRÍTICO
`render_salao()` chama `preparar_schema_teste(engine)` sempre.

**Target:** runtime comercial exige schema oficial via
`assert_schema_current`/runner. Test schema somente em E2E explicitamente
injetado.

### B7-03 — pagamento fake/test no fechamento — CRÍTICO
A UI chama `AplicacaoSalaoV1.registrar_pagamento_confirmado_teste_v1()`, que
materializa pagamento artificial antes de projetá-lo na comanda.

**Target:** remover esse helper do caminho comercial. A projeção do Salão só
aceita um `PagamentoORM` canônico realmente `PAGO`, no mesmo tenant,
unidade e `comanda_id`, com método/valor/saldo compatíveis.

### B7-04 — contexto/schema de teste no Garçom — CRÍTICO
`core/garcom/ui_streamlit.py` chama `preparar_schema_teste(engine)` e cria
`contexto_garcom_teste()`.

**Target:** mesma composição segura usada pela Central/KDS: identidade
autenticada por default; contexto/schema de teste apenas por injeção E2E.

### B7-05 — Garçom não possui superfície comercial — ALTO
`app.py` expõe Salão quando a flag libera, mas não renderiza Garçom e não há
página comercial dedicada.

**Target:** superfície mobile/tablet acessível somente a identidade com
permissões adequadas, sem permitir seleção de papel/usuário pela UI.

### B7-06 — feature flags mais seguras que a UI — ALTO
As flags atuais já exigem adapters reais (`orders/payments/salao/auth`), mas
as UIs ainda usam internamente os helpers de teste.

**Target:** alinhar implementation com o contrato da registry. Flag ligada em
runtime comercial nunca pode ativar test harness.

## 4. Current -> Target por boundary

| Boundary | Current | Target F7 |
|---|---|---|
| Identidade Salão | contexto de teste / gerente fixo | identidade autenticada |
| Identidade Garçom | papel/usuario parametrizável + contexto teste | identidade autenticada |
| Schema | `preparar_schema_teste` na UI | migration oficial 0012 |
| Pedido | canônico | preservar |
| KDS | canônico | preservar |
| Salão | canônico no domínio, UI test-only | composition comercial |
| Pagamento | domínio canônico existe, UI injeta fake | somente pagamento canônico confirmado |
| Garçom | domínio + mini-app E2E | superfície comercial |
| Tenant/unidade | correto no domínio | derivado do Active Execution Scope |
| RBAC Garçom | MESA_ABRIR + COMANDA_ALTERAR, sem financeiro | preservar |
| Fechamento financeiro | UI de Salão gera confirmação test | Caixa/Gerente/Admin via Pagamentos canônicos |
| Migration | test helper + 0012 oficial | apenas 0012 oficial |
| E2E | mini-apps históricos | Commercial Runtime E2E + mobile/tablet |

## 5. RBAC e separação de funções

A matriz atual do papel `GARCOM` contém:
- `PEDIDO_CRIAR`;
- `PEDIDO_VISUALIZAR`;
- `PEDIDO_ALTERAR`;
- `MESA_ABRIR`;
- `COMANDA_ALTERAR`.

Não contém:
- `COMANDA_FECHAR`;
- `PAGAMENTO_CONFIRMAR`;
- `MESA_TRANSFERIR`.

**Decisão:** não ampliar a matriz por conveniência de UI. O Garçom opera
consumo e solicita conta. Pagamento/fechamento financeiro permanece com perfis
financeiros/gerenciais autorizados.

## 6. Persistência/migration

`0012_restaurant_operations_runtime_v1` executa:
- `SalaoBase.metadata.create_all(..., checkfirst=True)`;
- DeliveryBase;
- ImpressaoBase.

Logo o F7 não cria migration por default. O gate deve provar:
- schema current;
- fresh PostgreSQL;
- upgrade PostgreSQL;
- presença das tabelas/constraints de Salão;
- ausência de chamadas a `migrations.salao_v1.upgrade` no commercial path.

## 7. Riscos principais

1. permitir contexto injetado fora de teste;
2. papel/usuário escolhido por parâmetro de UI;
3. duplicar Pagamento para fechar comanda;
4. criar commit escondido no service/repository;
5. misturar tenant/unidade;
6. fechar comanda antes de Pedido/KDS/financeiro estarem resolvidos;
7. reabilitar `create_all` silencioso no runtime;
8. expor UI de Garçom a perfil não autorizado.

## 8. Sequência de execução

### F7-A — Inventário + System Design — CONCLUÍDA
Este documento + System Design + ADR.

### F7-B — Commercial Composition Root / Identity / Schema — FECHADA
- test schema/context removidos do commercial default dos dois renderers;
- contexto autenticado adotado; injeção artificial falha fora de TEST_MODE;
- runtime_teste removido das APIs públicas e das superfícies comerciais; helpers E2E ficam exclusivamente nos entrypoints de teste;
- Salão deixou de fabricar pagamento de teste e só projeta pagamento canônico confirmado;
- página comercial mobile/tablet do Garçom criada com auth/RBAC/flag/schema current;
- migration oficial 0012 reutilizada, sem migration nova;
- fitness anti-test-runtime + PostgreSQL dedicado adicionados;
- readiness global atualizado de TEST_RUNTIME para COMMERCIAL_CANDIDATE em Salão/Garçom; gate físico/comercial final permanece pendente;
- PR11/PR12 preservados por contextos e seeds explícitos nos entrypoints E2E, fora do import graph comercial.
- fechamento depende do gate F7-B e regressões PR11/PR12 no mesmo SHA.
- **Fechamento técnico aprovado em 02/09/2026 no SHA `b56e11695f43b253b339953e5072908b00eec7ca`.**
- Matriz final do checkpoint técnico: **19/19 workflows verdes** no mesmo SHA.
- Gates críticos: Fase 7B Commercial Composition Gate = success; PR11 Salão = success; PR12 Garçom = success; Commercial Runtime Readiness V1 = success.
- A primeira tentativa do PR11 apresentou timeout transversal em PDV/CRM cashback; o job foi reexecutado no mesmo SHA e passou integralmente, enquanto o E2E próprio de Salão já estava verde.
- Nenhuma migration nova foi criada; `0012_restaurant_operations_runtime_v1` permanece a migration oficial do Salão.
- Nenhum merge/deploy foi realizado neste bloco.

### F7-C — Salão comercial + Pagamento — FECHADA
- confirmação financeira de teste permanece fora do caminho comercial;
- composição usa `criar_obrigacao_pagamento`, `confirmar_pagamento` (dinheiro)
  e `confirmar_pagamento_presencial` (crédito/débito) sem criar façade financeira paralela;
- criação respeita `PAGAMENTO_REGISTRAR`; confirmação/projeção respeitam
  `PAGAMENTO_CONFIRMAR`; fechamento respeita `COMANDA_FECHAR`;
- PIX pode criar obrigação, porém não recebe confirmação humana artificial:
  permanece pendente até webhook/provider financeiramente validado;
- Salão continua projetando somente `PagamentoORM` realmente `PAGO`,
  do mesmo tenant/unidade/comanda, método e valor;
- IDs comerciais gerenciados pela UI são estáveis por parcela/Pedido para replay seguro;
- testes dedicados cobrem dinheiro, cartão presencial, PIX fail-closed,
  alçada, idempotência e conflito de versão;
- **fechamento técnico aprovado em 02/09/2026 no SHA
  `7f6014c489bce15127f76b6c70576931699acc25`;**
- matriz final do checkpoint técnico: **20/20 workflows verdes no mesmo SHA**;
- gates críticos verdes: Fase 7C Salao Canonical Payment Gate, PR11 Salão,
  PR12 Garçom, Fase 7B Commercial Composition Gate, Commercial Runtime Readiness V1,
  V1 Wave1 Authoritative Transactions e PR10 KDS;
- a primeira tentativa do E2E principal do PR10 expirou no teste transversal
  `pdv-cashback.spec.ts` ao selecionar opção de CRM/PDV; o job falho foi reexecutado
  no mesmo SHA e passou, enquanto os jobs específicos do KDS já estavam verdes;
- nenhuma migration nova foi criada; `0012_restaurant_operations_runtime_v1`
  permanece a migration oficial do Salão;
- nenhum merge/deploy foi realizado neste bloco.

### F7-D — Garçom mobile/tablet — FECHADA
- auditoria confirmou que domínio, UoW, identidade comercial e filtro de alçada já
  estavam corretos após F7-B; não houve reescrita do domínio Garçom;
- identidade GARCOM e composition comercial permanecem fail-closed;
- browser dedicado prova **390x844** e **820x1180**;
- celular e tablet provam somente a própria comanda/alerta e ocultação da comanda
  pertencente a outro garçom;
- ambos os viewports provam ausência de ações de pagamento e fechamento;
- mobile prova a mutação autorizada `Solicitar conta` e a transição para
  `conta_solicitada` sem liberar ação financeira;
- prova de serviço continua recusando mutação de comanda alheia com
  `comanda_fora_alcada`, sem commit parcial;
- Gerente permanece como regressão separada, sem transformar a UI do Garçom em
  superfície financeira;
- página comercial continua usando identidade autenticada e não aceita papel/usuário
  via query/widget no caminho comercial; parâmetros do mini-app E2E permanecem isolados
  sob o harness de teste;
- nenhum domínio, permissão ou migration foi ampliado neste bloco;
- **fechamento técnico aprovado em 02/09/2026 no SHA
  `433c524ea1610b3da68e6b305faa5034361bd26a`;**
- **21/21 workflows verdes no mesmo SHA**, incluindo Fase 7D Garcom Mobile Tablet
  Gate, PR12 Garçom, PR11 Salão, PR10 KDS, F7-B, F7-C, Readiness e Wave1;
- gate F7-D fechou os dois jobs: `GARCOM 390x844 + 820x1180` e
  `Identity + RBAC + transaction boundary` integralmente verdes;
- nenhum merge/deploy foi realizado neste bloco.

### F7-E — Produção/KDS integrada — FECHADA
- o bloco não reescreveu Pedido, KDS, Salão ou Garçom; adicionou prova integrada
  sobre as autoridades já existentes;
- Pedido canônico com item real é vinculado à comanda pelo `ServicoGarcom`, sem
  cópia ou segunda verdade do Pedido;
- `ServicoKDS.criar_setor` e `ServicoKDS.rotear_item` criam o roteamento real no
  setor correto, iniciando a produção em `aguardando`;
- a produção percorre as transições oficiais
  `aguardando -> aceita -> em_preparo -> pronta` com as precondições do KDS,
  sem semear diretamente um `ProducaoItemORM` em estado final;
- o painel do Garçom deriva o alerta `pronta` exclusivamente do KDS para a própria
  comanda; outro GARCOM no mesmo tenant/unidade não recebe o alerta alheio;
- após a produção pronta, o GARCOM solicita a conta e a comanda transita para
  `conta_solicitada`, mantendo o saldo financeiro intacto e sem ganhar alçada de
  pagamento ou fechamento;
- gate dedicado também executa regressões completas de Garçom + KDS;
- **fechamento técnico aprovado em 02/09/2026 no SHA
  `bc1609397ffec66a9384a2867d85869eb2fe796f`;**
- **22/22 workflows verdes no mesmo SHA**, incluindo Fase 7E Producao KDS
  Integrada Gate, PR10 KDS, PR11 Salão, PR12 Garçom, F7-D, F7-C, F7-B,
  Commercial Runtime Readiness V1, Fase 6D Commercial Runtime E2E Gate,
  V1 Wave1 Authoritative Transactions e Hardening Gate E;
- nenhuma migration nova foi criada e nenhum domínio/RBAC foi ampliado;
- nenhum merge/deploy foi realizado neste bloco.

### F7-F — Commercial Runtime E2E / fechamento — FECHADA
- PostgreSQL 16 comercial/staging foi preparado pelo gate dedicado;
- Salão executou login real, jornada desktop e fechamento com Pagamento canônico;
- Garçom executou login real nas superfícies comerciais mobile/tablet, preservando
  própria alçada, alerta KDS e ausência de ação financeira;
- a evidência pós-browser confirmou no PostgreSQL a comanda gerencial `fechada`,
  pagamento `pago` com saldo zero e produção KDS `pronta`;
- o contrato de alvo de toque do Garçom foi corrigido para mínimo de 44 px em
  todos os controles acionáveis da área principal;
- o helper E2E de selectbox Streamlit foi estabilizado contra rerenderização,
  reacquirindo o widget a cada tentativa sem alterar regra de negócio;
- **checkpoint técnico final: `2191b45df395005b006072a98ea323500ff46e72`;**
- **24/24 workflows verdes no mesmo SHA**;
- `Fase 7F Commercial Runtime E2E Gate` run 4 / `33662970167`: **PASS**;
- `PR10 KDS Gates` run 365 / `33662970046`: **PASS** após a estabilização
  definitiva do helper E2E no candidato final;
- `PR16 Delivery Gates` run 237 / `33662970069`: **PASS**; a primeira tentativa
  do E2E de CEP fora da área não exibiu a mensagem dentro do timeout e o rerun do
  job no mesmo SHA passou sem mudança de código;
- Salão e Garçom permanecem `COMMERCIAL_CANDIDATE`, agora com evidência de
  Commercial Runtime E2E/browser preenchida e sem blockers internos conhecidos;
- nenhuma migration nova foi criada na Fase 7; `0012_restaurant_operations_runtime_v1`
  permanece a migration oficial de Salão/Garçom;
- nenhum merge e nenhum deploy foram executados;
- **Fase 7 fechada tecnicamente; Fase 8 — KDS comercial integrado — liberada
  para inventário Current → Target e execução sequencial.**

## 9. STOP

Nenhum domínio será reescrito nesta etapa.
Nenhuma migration nova é autorizada sem schema drift provado.
Nenhum merge/deploy decorre deste inventário.
