# INVENTÁRIO FASE 10 — EXPEDIÇÃO / ENTREGADOR — CUTOVER COMERCIAL V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Autoridade:** Documento Mestre + RECOVERY Issue #62  
**Issue da fase:** #80  
**Fase:** 10 — Expedição / Entregador  
**Branch:** `recovery/v1-fase10-expedicao-entregador-cutover`  
**Base auditada:** `main` @ `2e8c4cb6efe0563e6ea705d99de8a77b411b2b05`  
**Data:** 04/09/2026  
**Status:** INVENTÁRIO CURRENT → TARGET CONCLUÍDO — implementação ainda não iniciada

## 1. Objetivo

Promover o patrimônio já existente de Entrega/Expedição para um runtime comercial real, preservando domínio, persistência, UoW, RBAC e idempotência já canônicos.

A Fase 10 não deve reescrever o módulo de Entrega. O trabalho é fechar as lacunas de composição comercial entre identidade real, Pedido/KDS, expedição, atribuição de entregador e jornada operacional.

A pendência física da impressora da Fase 9 permanece registrada separadamente para a homologação final da V1 e não autoriza apagar nem mascarar qualquer gate da Fase 10.

## 2. Current — patrimônio que deve ser preservado

### 2.1 Domínio e persistência

Já existem em `core/entrega`:
- `Entrega`, eventos e estados operacionais;
- persistência SQLAlchemy em `entregas_v1` e `eventos_entrega_v1`;
- escopo obrigatório por tenant/unidade/pedido;
- unicidade por pedido e idempotência de eventos;
- controle de versão/CAS;
- transições para produção pronta, checklist, atribuição, coleta, saída em rota, tentativa falha e confirmação de entrega;
- RBAC através de `Permissao.EXPEDICAO_OPERAR`;
- isolamento do entregador para visualizar/operar apenas as próprias entregas quando aplicável.

O schema comercial dessas estruturas já pertence à migration oficial de Restaurant Operations Runtime. **Não criar migration F10 por padrão.** Migration nova só será admitida se um gate de schema demonstrar drift objetivo que não possa ser atendido pelo patrimônio existente.

### 2.2 Application / UoW

`application/entrega_transacoes.py` já fornece `AplicacaoEntregaV1` sobre `UnitOfWorkV1` e mantém ownership transacional correto:
- Application abre/usa a Session ativa;
- serviço/repository não escondem `commit()`;
- UoW é dona do commit;
- operações existentes: checklist, atribuição, coleta, saída em rota, confirmação e tentativa falha.

Esse boundary deve ser preservado e ampliado somente quando necessário.

### 2.3 Integrações canônicas já existentes

`core/entrega/integracoes_sqlalchemy.py` já lê fontes canônicas para:
- situação financeira do Pedido via pagamentos oficiais;
- cancelamento do Pedido via `PedidoORM`.

`application/assistente_delivery_convergence.py` já cria `Entrega` canônica para pedidos de delivery originados no Assistente, usando tenant/unidade/pedido reais, id determinístico e estado inicial `AGUARDANDO_PRODUCAO`.

### 2.4 Segurança e identidade

A autenticação canônica já possui:
- `IdentidadeUsuario` e `ContextoExecucao` reais;
- papéis `EXPEDICAO` e `ENTREGADOR`;
- permissão `EXPEDICAO_OPERAR`;
- repositório SQLAlchemy capaz de listar usuários do tenant.

Portanto a Fase 10 **não deve criar cadastro paralelo de entregadores**, identidade fake, tenant fixo nem `driver-1` comercial. Entregadores devem ser usuários canônicos do tenant com papel/permissão elegível.

### 2.5 Gates históricos

`PR13 Entrega Gates` já cobre domínio, persistência, Ruff, mypy, testes Python e E2E histórico.

Esse E2E, porém, roda em `FM_AI_TEST_MODE=1`, com runtime/contexto de teste e banco temporário. Ele permanece útil como regressão, mas **não é evidência de Commercial Runtime**.

## 3. Current — gaps objetivos

### B10-01 — Contexto comercial de Expedição/Entregador ausente

**ABERTO.**

`core/entrega/ui_streamlit.py` importa e utiliza `core.entrega.runtime_teste.contexto_entrega_teste` para construir o contexto operacional. A UI aceita papel/usuário fornecidos externamente em vez de receber `ContextoExecucao` derivado da identidade autenticada real.

Target:
- nenhum `runtime_teste`, `contexto_entrega_teste`, tenant demo/e2e ou identidade artificial no caminho comercial;
- UI recebe identidade/contexto canônico injetado;
- roles/permissões são validadas pelo RBAC real.

### B10-02 — Superfície comercial ausente

**ABERTO.**

A `main` auditada não expõe uma página comercial real de Expedição/Entregador em `app.py` ou em `pages/`. O E2E atual usa um entrypoint exclusivo de testes.

Target:
- superfície comercial autenticada para Expedição;
- superfície comercial autenticada/mobile-friendly para Entregador;
- fail-closed para usuários sem papel/permissão;
- sem query string de teste para escolher papel/usuário.

### B10-03 — Handoff KDS/Pedido PRONTO → Entrega não composto no runtime comercial

**ABERTO.**

O domínio de Entrega já possui a transição sistêmica de pedido pronto para expedição, e o KDS canônico já promove o Pedido para `PRONTO` quando a Produção termina. Na auditoria do runtime atual **não foi localizada composição comercial** que, após o commit autoritativo do KDS, avance a Entrega vinculada de `AGUARDANDO_PRODUCAO` para `AGUARDANDO_EXPEDICAO`.

Target:
- handoff idempotente e tenant/unidade scoped após confirmação autoritativa do KDS;
- replay seguro;
- falha do handoff não pode desfazer o commit do KDS;
- falha deve ser observável/retriável e jamais criar segunda Entrega para o mesmo Pedido.

### B10-04 — Atribuição de entregador não governada pela identidade canônica

**ABERTO.**

A UI histórica aceita identificador de driver livre/hardcoded (`driver-1`). Isso é aceitável em teste, mas não em runtime comercial.

Target:
- Expedição seleciona apenas usuários reais do mesmo tenant elegíveis como `ENTREGADOR`;
- nenhum ID livre digitado pelo operador;
- nenhum cadastro paralelo;
- usuário de outro tenant/inativo/sem papel elegível deve ser rejeitado;
- entregador autenticado opera apenas entregas atribuídas a si quando a regra de domínio exigir.

### B10-05 — Commercial Runtime E2E ausente

**ABERTO.**

Os gates históricos não provam no mesmo SHA:
- PostgreSQL 16;
- migrations oficiais;
- `app.py`/page comercial sem `FM_AI_TEST_MODE`;
- login real de EXPEDICAO e ENTREGADOR;
- Pedido/KDS real → Entrega pronta para expedição;
- checklist e atribuição governada;
- coleta e saída em rota;
- confirmação/tentativa falha sob RBAC;
- isolamento de tenant/usuário;
- persistência final autoritativa.

Target: um gate F10 Commercial Runtime dedicado com navegador real e evidência PostgreSQL durável.

## 4. Readiness inicial da Fase 10

Estado atual esperado no manifesto:

`entrega = TEST_RUNTIME`

Code blocker já detectado pelo readiness atual:
- `entrega_uses_test_context`.

A F10 deve evoluir o gate de readiness para reconhecer também as capacidades comerciais ausentes desta fase sem remover blockers por conveniência.

Nenhum módulo poderá ser promovido para `COMMERCIAL_HOMOLOGATED` apenas porque os testes históricos estão verdes.

## 5. Target final da Fase 10

Ao final da Fase 10:
1. Expedição e Entregador usam identidade comercial real;
2. não existe test-runtime no caminho comercial;
3. KDS/Pedido `PRONTO` aciona handoff idempotente para `AGUARDANDO_EXPEDICAO`;
4. Expedição conclui checklist e atribui usuário canônico elegível;
5. Entregador autenticado vê e opera apenas o escopo permitido;
6. coleta, saída em rota, tentativa falha e confirmação passam pela Application/UoW canônica;
7. cancelamento e situação financeira continuam consultados em fontes oficiais;
8. nenhum repository recebe ownership de commit;
9. nenhuma migration nova é criada sem drift objetivo;
10. Commercial Runtime E2E prova jornada real em PostgreSQL + navegador + RBAC no mesmo SHA.

## 6. Current → Target

| Área | Current | Target |
|---|---|---|
| Domínio Entrega | Canônico e amplo | Preservado |
| Persistência | SQLAlchemy existente | Reutilizada |
| Migration | Schema oficial já existente | Reutilizar; sem nova migration por padrão |
| Application/UoW | Canônica | Preservada/ampliada seletivamente |
| Identidade UI | `contexto_entrega_teste` | `ContextoExecucao` real |
| Superfície | E2E/test entrypoint | Página/app comercial autenticado |
| KDS → Entrega | Sem composição comercial localizada | Handoff idempotente pós-commit KDS |
| Driver | ID livre/hardcoded no fluxo histórico | Usuário canônico ENTREGADOR do tenant |
| RBAC | Domínio já possui regra | Composto com login real na UI |
| E2E | Test mode + runtime de teste | PostgreSQL + app/page real + browser + auth real |

## 7. Sequência obrigatória de execução

### F10-A — Inventário Current → Target
**ESTE DOCUMENTO.**

- congelar gaps objetivos antes do código;
- preservar patrimônio existente;
- proibir reescrita e migration especulativa.

### F10-B — Commercial Boundary / Identity / Surface

- remover dependência de `contexto_entrega_teste` da UI comercial;
- compor `ContextoExecucao` real;
- criar superfícies autenticadas para EXPEDICAO/ENTREGADOR;
- usar feature flag/adapters canônicos;
- fitness anti-test-runtime no caminho comercial;
- preservar entrypoints de teste apenas sob `tests/`/test mode.

### F10-C — KDS PRONTO → Expedição

- compor handoff pós-commit KDS;
- transição idempotente de Entrega vinculada para expedição;
- replay, isolamento e falha segura;
- provar que falha de Entrega não desfaz Produção/KDS já autoritativa.

### F10-D — Driver Governance / Jornada Operacional

- listar entregadores elegíveis pelo repositório canônico de usuários;
- atribuição tenant scoped;
- checklist → atribuição → coleta → rota → conclusão/tentativa falha;
- RBAC e isolamento por usuário/tenant;
- nenhuma identidade livre/hardcoded no comercial.

### F10-E — Commercial Runtime E2E

- PostgreSQL 16;
- migrations oficiais;
- app/page real sem `FM_AI_TEST_MODE`;
- login EXPEDICAO real;
- Pedido/KDS real até `PRONTO`;
- Entrega em `AGUARDANDO_EXPEDICAO`;
- checklist e atribuição a ENTREGADOR real;
- login ENTREGADOR real;
- coleta → rota → confirmação/tentativa falha;
- negativa RBAC para identidade não autorizada;
- evidência PostgreSQL final e isolamento.

## 8. Gates mínimos

Cada sub-bloco deve executar, conforme aplicável:
- compile;
- Ruff;
- mypy;
- testes focados;
- PR13 Entrega Gates;
- KDS gates afetados;
- Auth/RBAC gates afetados;
- Commercial Runtime Readiness V1;
- matriz transversal antes de fechamento documental.

Falha deve ser corrigida e retestada; nenhum bloco será declarado fechado com vermelho conhecido.

## 9. STOP / Governança

Este inventário autoriza apenas a sequência técnica da Fase 10 sob as regras já aprovadas.

Continua proibido:
- merge sem autorização humana explícita;
- deploy sem autorização humana explícita;
- Fake/runtime_teste em caminho comercial;
- migration nova sem drift objetivo;
- relaxar gate para fazê-lo passar;
- apagar pendências externas/físicas legítimas;
- criar identidade/cadastro paralelo quando a plataforma já possui autoridade canônica.

**Próximo bloco após o inventário verde:** F10-B — Commercial Boundary / Identity / Surface.
