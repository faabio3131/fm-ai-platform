# Inventário — Fase 8 — KDS — Cutover Comercial Integrado

**Status:** F8-C FECHADA — F8-D LIBERADA  
**Issue:** #73  
**Base sequencial:** `f883f898e27c27f01af8930303a13e7f548d7397`  
**Branch:** `recovery/v1-fase8-kds-commercial-cutover`

## 1. Autoridade e objetivo

Autoridades:
- Documento Mestre — FASE 8;
- Programa RECOVERY #62;
- Auditoria anti-retrabalho #61;
- fechamento formal da Fase 7;
- AGENTS.md e System Design Master.

A Fase 8 **não reimplementa o KDS**. O domínio e a maior parte da composition
já são canônicos. O objetivo é fechar o cutover operacional e a evidência
comercial do operador KDS no runtime real.

Gate funcional:

`Pedido confirmado -> roteamento/setor -> aguardando -> aceita -> em_preparo -> pronta -> Pedido macro PRONTO -> downstream`

executado com PostgreSQL, identidade autenticada, RBAC e browser comercial.

## 2. Patrimônio válido já existente — preservar

### Domínio e persistência
- `core.kds.ServicoKDS`;
- `RepositorioKDSSQLAlchemy`;
- estados normativos e precondições de produção;
- prioridade, setor, SLA, pausa, retomada e retirada;
- CAS por versão;
- idempotency key + fingerprint;
- auditoria e métricas;
- cache de último snapshot para degradação somente leitura;
- `KDSBase` persistente.

### Migration oficial
O runner comercial já contém:
- `0010_kds_authoritative_runtime_v1`;
- `KDSBase.metadata.create_all(..., checkfirst=True)`.

Portanto **nenhuma migration F8 nova é prevista**. Só será criada migration
forward se um teste fresh/upgrade demonstrar schema drift objetivo.

### Application / UoW
Já existem:
- `application.kds_runtime.ServicoKDSCanonico`;
- `application.kds_transacoes.rotear_item_kds_v1`;
- `application.kds_transacoes.transicionar_kds_v1`;
- `application.kds_roteamento.listar_itens_pendentes`.

Os writes entram por `UnitOfWorkV1`; a Application é dona do commit.
UI/repository/service não devem assumir ownership de commit.

### Integração canônica
`ServicoKDSCanonico` já:
- valida Pedido do mesmo tenant/unidade;
- roteia item de Pedido canônico;
- promove Pedido `CONFIRMADO -> ENVIADO_PRODUCAO`;
- ao iniciar produção, promove Pedido para `EM_PREPARO`;
- consome reserva canônica de Estoque no início real da produção;
- quando todos os itens ficam prontos, promove Pedido para `PRONTO`;
- publica eventos/outbox;
- registra auditoria;
- preserva projeção legada somente como compatibilidade posterior ao efeito canônico.

### UI comercial
`app.py` inclui a aba KDS apenas quando a feature está comercialmente habilitada
e, após o F8-B, quando a identidade ativa possui `PRODUCAO_VISUALIZAR`.

`core/kds/flags.py` exige adapters:
- `orders`;
- `kds`;
- `auth`.

`core/kds/ui_runtime.py`:
- deriva contexto da `IdentidadeUsuario` autenticada no caminho comercial;
- só permite contexto/schema E2E injetado com `FM_AI_TEST_MODE=1`;
- usa `ServicoKDSCanonico` e `transicionar_kds_v1`;
- permite simulação offline somente em E2E isolado;
- em degradação real, a leitura é somente leitura e comandos não são liberados;
- trata `permissao_insuficiente` como recusa explícita de acesso.

`core/kds/ui_roteamento.py`:
- usa identidade autenticada;
- só mostra roteamento para quem possui `PRODUCAO_ATUALIZAR`;
- lê itens pendentes do Pedido canônico;
- escreve por Application/UoW.

## 3. Evidência já existente

### PR10 histórico
O PR10 prova domínio, multi-setor, SLA, transições, idempotência, concorrência,
modo degradado e mini-app Playwright. O E2E específico histórico permanece
regressão válida, não substituto do Commercial Runtime E2E final.

### Fase 7
F7-E provou `Pedido -> KDS -> pronta -> alerta Garçom -> conta`.
F7-F provou KDS persistido em PostgreSQL no runtime comercial como parte da
jornada Salão/Garçom.

### Readiness atual
`kds = COMMERCIAL_CANDIDATE`

- `code_blockers = []`;
- blocker final de evidência: `commercial_runtime_physical_gate_pending`;
- Commercial Runtime E2E específico do F8 e physical gate permanecem para F8-E.

## 4. Gaps Current → Target

### B8-01 — Commercial Runtime E2E específico do KDS — CRÍTICO
Permanece para F8-E: PostgreSQL 16, migrations oficiais, `app.py`, login real,
operador KDS real, jornada browser completa e pós-condições no banco.

### B8-02 — prova comercial de RBAC — FECHADA NO F8-B
A composition só expõe a superfície KDS a identidades com
`PRODUCAO_VISUALIZAR`, sem ampliar a matriz de permissões. O domínio/Application
continuam como defesa final e o renderer converte negação em acesso recusado.

### B8-03 — cadeia de roteamento Application/UoW — FECHADA NO F8-C
O patrimônio já implementa a cadeia; F8-C consolida a prova dedicada de:
- Pedido `CONFIRMADO -> ENVIADO_PRODUCAO` no roteamento;
- Produção criada em `aguardando`;
- idempotência sem duplicação de produção/evento;
- rollback integral se o roteamento falhar.

### B8-04 — sincronização Pedido/Estoque/Eventos — FECHADA NO F8-C
O gate dedicado prova:
- `aceita -> em_preparo` promove Pedido para `EM_PREPARO`;
- início real consome a reserva canônica de Estoque exatamente uma vez;
- `pronta` promove Pedido para `PRONTO` quando todos os itens terminam;
- Outbox e Auditoria permanecem persistidos;
- ownership de commit/rollback permanece na Application/UoW.

### B8-05 — degradação/fail-closed — MÉDIO
Target F8-D:
- manter simulação fora do commercial default;
- provar leitura degradada e bloqueio de write;
- nenhuma falha de persistência pode inventar estado ou produzir commit parcial.

### B8-06 — readiness final — ALTO
Target F8-E:
- preencher Commercial Runtime E2E/physical evidence;
- remover blocker somente após evidência no mesmo candidato.

## 5. Current → Target por boundary

| Boundary | Current | Target F8 |
|---|---|---|
| Domínio KDS | canônico | preservar |
| Schema | migration 0010 oficial | preservar; sem migration nova sem drift |
| Identidade | autenticada + exposição RBAC | provar browser real no F8-E |
| Feature flag | orders+kds+auth + permissão | preservar |
| Pedido | sincronização canônica | gate dedicado F8-C |
| Estoque | consumo no início de produção | gate dedicado F8-C + replay F8-D |
| Eventos/auditoria | implementados | gate dedicado F8-C |
| Roteamento | Application/UoW | gate dedicado F8-C |
| Transições | Application/UoW + CAS | F8-C/F8-D |
| Multi-setor | provado | preservar + resiliência F8-D |
| Offline | cache/read-only | gate fail-closed F8-D |
| E2E | histórico + navegador Wave2 | Commercial Runtime E2E F8-E |
| Readiness | candidate | candidate com evidência final F8-E |

## 6. RBAC normativo

### COZINHA
Pode visualizar, aceitar e atualizar/preparar/pausar/retomar/pronto.
Não recebe `EXPEDICAO_OPERAR`, financeiro ou administração.

### EXPEDICAO
Pode visualizar produção e registrar retirada quando pronta.
Não recebe capacidade de preparo.

### GERENTE/ADMIN
Mantêm alçada elevada existente.

### Outros perfis
Falham fechado conforme a matriz vigente. F8 não amplia permissões para facilitar UI.

## 7. Sequência de execução

### F8-A — FECHADA
- inventário Current → Target;
- fontes autoritativas;
- migration 0010;
- RBAC;
- estratégia Commercial Runtime E2E.

### F8-B — FECHADA
- composition/RBAC commercial boundary;
- fitness contra test harness no default;
- nenhuma ampliação de permissão;
- 29/29 workflows verdes no SHA técnico e 29/29 na revalidação documental.

### F8-C — FECHADA
- prova dedicada da cadeia canônica consolidada;
- Pedido confirmado -> roteamento/setor -> aceite -> preparo -> pronto;
- consumo de reserva de Estoque exatamente uma vez;
- Eventos/Outbox/Auditoria persistidos;
- ownership transacional e rollback preservados;
- 30/30 workflows verdes no SHA técnico.

### F8-D — resiliência
- multi-setor;
- CAS/replay;
- falha de persistência;
- cache somente leitura;
- isolamento tenant/unidade.

### F8-E — Commercial Runtime E2E / fechamento
- PostgreSQL;
- login real;
- `app.py`;
- browser;
- pós-condições no banco;
- matriz transversal;
- readiness/inventário/checkpoint reconciliados.

## 8. F8-B — Composition / RBAC / fitness comercial — FECHADA

### Gate de entrada
- F8-A validada no SHA `2aef66932ae9824bf16134f48baf302a7cceaea5`;
- 24/24 workflows verdes.

### Fechamento técnico
**SHA candidato:** `34ff1cef4199d5be21c37a3224303c7f79b64061`

Implementado/confirmado:
- `app.py` só cria a aba KDS se `kds_v1_access_allowed(CURRENT_IDENTITY.permissoes)`;
- `kds_v1_access_allowed` exige feature habilitada e `PRODUCAO_VISUALIZAR`;
- nenhuma permissão/papel foi alterado;
- renderer mantém defesa em profundidade e recusa `permissao_insuficiente`;
- contexto/schema E2E continuam restritos a `FM_AI_TEST_MODE=1`;
- simulação offline não entra no commercial default;
- UI não assume commit; writes permanecem em Application + `UnitOfWorkV1`;
- migration oficial permanece `0010_kds_authoritative_runtime_v1`;
- nenhuma migration F8 foi criada.

### Evidência
- `Fase 8B KDS Commercial Boundary Gate` run 2 / `33675298080`: **PASS**;
- compile, Ruff, mypy, fitness commercial boundary e regressões KDS/RBAC: **PASS**;
- `V1 Wave2 KDS` run 144 / `33675298045`: **PASS**;
- `PR10 KDS Gates` run 369 / `33675298031`: **PASS**;
- `V1 Wave0 Production Foundation` run 209 / `33675298074`: **PASS**;
- **matriz transversal final: 29/29 workflows verdes no mesmo SHA**.

### Reconciliação documental
HEAD `07bf2b07f7e5db8c93f6b029a5722ffd7f1f1d09`:
- inventário F8-B fechado;
- readiness reconciliado sem retirar o blocker final indevidamente;
- checkpoint dedicado criado;
- PR/Issue sincronizadas;
- **29/29 workflows verdes no HEAD documental**.

**Decisão:** F8-B fechada e F8-C liberada.

## 9. F8-C — Cadeia operacional canônica — FECHADA

### Descoberta pré-código
Não foi encontrado gap funcional que justifique reescrever `ServicoKDSCanonico`.
As provas históricas de Wave2 já demonstram individualmente:
- sincronização do Pedido macro;
- consumo de reserva no início real;
- idempotência de roteamento/evento;
- rollback de roteamento;
- ownership transacional da Application.

O problema era de **evidência fragmentada**, não de domínio ausente.

### Candidato F8-C
Foi criado o gate dedicado `.github/workflows/fase8c-kds-canonical-chain.yml`
para consolidar como requisito explícito da Fase 8:
1. compile/Ruff/mypy da cadeia KDS/Pedido/Estoque/Eventos;
2. Pedido `CONFIRMADO -> ENVIADO_PRODUCAO` via roteamento canônico;
3. `aceita -> em_preparo` e Pedido `EM_PREPARO`;
4. consumo da reserva de Estoque no início real;
5. `pronta` e Pedido macro `PRONTO`;
6. Outbox/Auditoria;
7. idempotência sem duplicar evento core;
8. rollback sem persistência parcial;
9. ownership transacional por `UnitOfWorkV1`;
10. regressão do domínio KDS.

### Regra
Nenhum código de domínio, RBAC ou migration foi alterado para este candidato.
### Fechamento técnico
**SHA candidato:** `f2669cd9ab857bf03e498b1c0218e8eafb77a103`

Evidência no mesmo SHA:
- `Fase 8C KDS Canonical Chain Gate` run 1 / `33677790860`: **PASS**;
- compile, Ruff e mypy: **PASS**;
- cadeia Pedido + KDS + Estoque + Outbox + Auditoria: **PASS**;
- ownership transacional e rollback: **PASS**;
- regressão do domínio KDS: **PASS**;
- `V1 Wave2 KDS`, PR10, Wave0/Wave1 e demais regressões transversais: **PASS**;
- **matriz transversal final: 30/30 workflows verdes no mesmo SHA**.

Nenhum código de domínio, RBAC ou migration foi alterado no F8-C. O bloco fechou um gap de evidência, não um gap de domínio.

**Decisão:** F8-C fechada e **F8-D — resiliência/fail-closed — liberada**.

## 10. STOP

A Fase 8 não fecha se:
- houver Fake/Mock/runtime_teste no caminho comercial;
- o browser dedicado não usar `app.py` e login real;
- perfil sem permissão puder operar KDS;
- COZINHA puder registrar retirada sem alçada;
- transição KDS divergir do Pedido macro;
- início de produção duplicar consumo de Estoque;
- falha/degradação permitir write;
- houver schema drift não tratado;
- qualquer gate crítico estiver vermelho.

Nenhum merge/deploy decorre deste inventário.
