# Inventário — Fase 8 — KDS — Cutover Comercial Integrado

**Status:** F8-B EM VALIDAÇÃO — composition/RBAC/fitness comercial candidato  
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
`app.py` já inclui a aba KDS quando `kds_v1_enabled()`.

`core/kds/flags.py` exige adapters:
- `orders`;
- `kds`;
- `auth`.

`core/kds/ui_runtime.py`:
- deriva contexto da `IdentidadeUsuario` autenticada no caminho comercial;
- só permite contexto/schema E2E injetado com `FM_AI_TEST_MODE=1`;
- usa `ServicoKDSCanonico` e `transicionar_kds_v1`;
- permite simulação offline somente em E2E isolado;
- em degradação real, a leitura é somente leitura e comandos não são liberados.

`core/kds/ui_roteamento.py`:
- usa identidade autenticada;
- só mostra roteamento para quem possui `PRODUCAO_ATUALIZAR`;
- lê itens pendentes do Pedido canônico;
- escreve por Application/UoW.

## 3. Evidência já existente

### PR10 histórico
O PR10 já prova:
- domínio;
- multi-setor;
- SLA;
- transições;
- idempotência;
- concorrência;
- modo degradado;
- mini-app Playwright.

Limite: o E2E específico de KDS sobe `tests/e2e-kds/app_kds.py` com
`FM_AI_TEST_MODE=1`. Ele é regressão válida, mas não é homologação comercial.

### Fase 7
F7-E provou a cadeia real de serviços:
`Pedido -> KDS -> pronta -> alerta Garçom -> conta`.

F7-F provou KDS persistido em PostgreSQL no runtime comercial como parte da
jornada Salão/Garçom.

Limite: a Fase 7 **não operou a aba KDS como usuário de cozinha autenticado**,
nem executou pelo browser comercial toda a sequência de roteamento/transições.

### Readiness atual
`kds = COMMERCIAL_CANDIDATE`

- `code_blockers = []`;
- blocker de evidência: `commercial_runtime_physical_gate_pending`;
- `commercial_runtime_e2e = null`;
- `physical_test = null`.

## 4. Gaps Current → Target

### B8-01 — ausência de Commercial Runtime E2E específico do KDS — CRÍTICO
Current:
- E2E KDS dedicado usa mini-app/test mode;
- PR10 com `app.py` habilita KDS, mas é smoke/regressão geral e não executa a
  jornada operacional completa do cozinheiro.

Target:
- PostgreSQL 16;
- migrations oficiais;
- `FM_AI_TEST_MODE` ausente;
- `app.py` real;
- login real;
- usuário COZINHA/GERENTE real;
- roteamento e transições no browser;
- pós-condições conferidas no PostgreSQL.

### B8-02 — prova comercial de RBAC incompleta — ALTO
Current:
- serviços falham fechado;
- COZINHA possui `PRODUCAO_VISUALIZAR`, `PRODUCAO_ACEITAR`,
  `PRODUCAO_ATUALIZAR`;
- EXPEDICAO possui `PRODUCAO_VISUALIZAR` + `EXPEDICAO_OPERAR`;
- GARCOM não possui permissões KDS.

Target:
- provar navegador com perfil correto;
- provar negativo para perfil sem `PRODUCAO_VISUALIZAR`;
- COZINHA não pode registrar retirada;
- EXPEDICAO não recebe capacidade de preparo por conveniência;
- se necessário, ocultar/recusar a aba no composition root sem ampliar RBAC.

### B8-03 — operação browser de roteamento não homologada — ALTO
Current:
- `ui_roteamento` já usa Pedido canônico e Application/UoW.

Target:
- Pedido confirmado aparece como pendente;
- operador autorizado seleciona setor;
- roteamento cria produção `aguardando`;
- replay não duplica produção;
- outro tenant/unidade não aparece.

### B8-04 — sincronização Pedido/Estoque/Eventos não provada pela UI comercial — ALTO
Target:
- roteamento: Pedido -> `ENVIADO_PRODUCAO`;
- iniciar: Pedido -> `EM_PREPARO`;
- início consome reserva de estoque uma vez;
- todos os itens prontos: Pedido -> `PRONTO`;
- outbox/auditoria persistidos;
- replay não duplica consumo/eventos.

### B8-05 — degradação/fail-closed precisa de gate comercial — MÉDIO
Current:
- `listar_fila_tolerante` usa último snapshot;
- write indisponível gera `kds_offline_somente_leitura`;
- checkbox de simulação é restrito ao E2E.

Target:
- manter simulação fora do commercial default;
- teste integrado prova leitura degradada e bloqueio de write;
- nenhuma falha de persistência pode inventar estado ou produzir commit parcial.

### B8-06 — readiness sem evidência final — ALTO
Target:
- preencher SHA;
- Commercial Runtime E2E;
- browser/physical gate;
- remover blocker somente após evidência no mesmo candidato.

## 5. Current → Target por boundary

| Boundary | Current | Target F8 |
|---|---|---|
| Domínio KDS | canônico | preservar |
| Schema | migration 0010 oficial | preservar; sem migration nova sem drift |
| Identidade | autenticada no renderer | provar no browser real |
| Feature flag | orders+kds+auth reais | preservar |
| Pedido | sincronização canônica | provar ponta a ponta |
| Estoque | consumo no início de produção | provar exatamente uma vez |
| Eventos/auditoria | implementados | provar persistência |
| Roteamento | Application/UoW | homologar no `app.py` |
| Transições | Application/UoW + CAS | homologar no `app.py` |
| Multi-setor | provado em mini-app | preservar + prova comercial mínima |
| Offline | cache/read-only | preservar + gate fail-closed |
| E2E | histórico test-mode | Commercial Runtime E2E real |
| Readiness | candidate sem evidência | candidate com evidência e blockers 0 |

## 6. RBAC normativo

### COZINHA
Pode:
- visualizar produção;
- aceitar;
- atualizar/preparar/pausar/retomar/pronto.

Não recebe por F8:
- `EXPEDICAO_OPERAR`;
- permissões financeiras;
- permissões administrativas.

### EXPEDICAO
Pode:
- visualizar produção;
- registrar retirada quando a produção estiver pronta.

Não recebe capacidade de preparo.

### GERENTE/ADMIN
Mantêm alçada elevada já existente.

### Outros perfis
Falham fechado conforme a matriz vigente. F8 não ampliará permissões para
facilitar teste/UI.

## 7. Sequência de execução

### F8-A — inventário + System Design
- Current → Target;
- fontes autoritativas;
- migrations;
- RBAC;
- concorrência/idempotência;
- estratégia Commercial Runtime E2E.

### F8-B — composition/RBAC/fitness
- eliminar gaps de exposição/feedback de acesso, se confirmados;
- fitness contra test harness no commercial default;
- negativos de RBAC.

### F8-C — cadeia operacional canônica
- Pedido confirmado;
- roteamento/setor;
- aceite;
- preparo;
- pronto;
- Pedido macro;
- Estoque/eventos/auditoria.

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
- matriz transversal no mesmo SHA;
- readiness/inventário/checkpoint reconciliados.

## 8. F8-B — Composition / RBAC / fitness comercial — EM VALIDAÇÃO

### Gate de entrada
- F8-A validada no SHA `2aef66932ae9824bf16134f48baf302a7cceaea5`;
- **24/24 workflows verdes** após abertura da PR draft #74;
- PR10 KDS completo, Wave0/Wave1, F7-F e regressões transversais: PASS;
- nenhum schema drift foi encontrado.

### Gap confirmado
A flag KDS era comercialmente segura quanto a adapters, e o domínio já negava
ações por RBAC, porém o `app.py` criava a aba KDS para qualquer identidade
quando a flag global estava ligada. Perfis sem `PRODUCAO_VISUALIZAR` podiam
receber uma superfície que terminava em erro genérico, embora não conseguissem
operar o domínio.

### Candidato F8-B
- composition root só cria a aba KDS quando:
  - `kds_v1_enabled()` está verdadeiro; e
  - a identidade ativa possui `PRODUCAO_VISUALIZAR`;
- nenhuma permissão é adicionada ou alterada;
- o renderer mantém defesa em profundidade e converte
  `permissao_insuficiente` em recusa explícita de acesso;
- contexto/schema E2E permanecem permitidos somente sob
  `FM_AI_TEST_MODE=1`;
- simulação offline continua inacessível no commercial default;
- UI continua sem ownership de commit; writes permanecem em
  `application.kds_transacoes` + `UnitOfWorkV1`;
- migration oficial continua `0010_kds_authoritative_runtime_v1`;
- fitness dedicado e workflow F8-B adicionados.

### Critério de fechamento
F8-B só será marcada FECHADA após:
- gate dedicado verde;
- regressões KDS/RBAC verdes;
- matriz transversal do SHA candidato sem regressão crítica;
- reconciliação documental do resultado.

## 9. STOP

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
