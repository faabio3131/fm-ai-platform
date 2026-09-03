# INVENTÁRIO FASE 9 — IMPRESSÃO POR SETOR — CUTOVER COMERCIAL V1

**Projeto:** KORDENA / GERENTE AI V1.0  
**Fase:** 9 — Impressão por Setor  
**Issue:** #77  
**Branch:** `recovery/v1-fase9-impressao-commercial-cutover`  
**Base:** `main` pós-merge da Fase 8  
**Status:** F9-A — INVENTÁRIO CURRENT → TARGET

## 1. Autoridade e regra de recuperação

Este inventário é subordinado ao Documento Mestre, ao inventário patrimonial V1 e às regras de governança vigentes.

A Fase 9 NÃO autoriza reescrita do domínio de impressão. O patrimônio canônico deve ser preservado e promovido ao runtime comercial por composição, adapters e eventos reais.

Regras obrigatórias:
- nenhuma segunda autoridade de impressão;
- `ImpressoraFake` permanece exclusivamente test-only;
- nenhum Fake/Mock/runtime_teste no commercial default;
- tenant/unidade, RBAC, idempotência, versionamento/CAS, retry, contingência e auditoria permanecem obrigatórios;
- falha de impressão nunca bloqueia nem altera KDS, Pedido, Pagamento ou Estoque;
- nenhuma migration nova sem drift objetivo de schema;
- sem merge/deploy sem autorização humana;
- Commercial Runtime E2E e evidência de adapter real antes de homologação final.

## 2. Current — patrimônio já existente

### 2.1 Domínio/spool

Já existem em `core/impressao`:
- modelos de destino e job de impressão;
- status persistentes de impressão;
- repositório de spool;
- adapter SQLAlchemy;
- renderização de ticket operacional por setor;
- deduplicação por hash/idempotency key;
- retry e contingência;
- versionamento/CAS no update do job;
- reimpressão governada e auditada;
- sanitização de conteúdo operacional para evitar PII financeira desnecessária.

### 2.2 Porta de hardware

Já existe `PortaImpressora`, com contrato:
`imprimir(impressora_id, job_id, conteudo)`.

O único adapter concreto no patrimônio atual é `ImpressoraFake`, documentado explicitamente como adapter de teste e incapaz de tocar hardware, rede ou spool do sistema operacional.

### 2.3 Serviço autoritativo

`ServicoSpoolImpressao` já implementa:
- roteamento por tenant/unidade/setor;
- ausência de destino ativo como no-op governado (`sem_destino_ativo`);
- criação idempotente do job;
- processamento do job pela porta de impressão;
- falha normalizada do adapter;
- retry e entrada em contingência;
- reimpressão com permissão e auditoria.

Princípio já presente no próprio serviço: falha de impressão jamais altera ou bloqueia o KDS.

### 2.4 Feature flag comercial

`impressao_v1_enabled()` usa o runtime registry e exige:
- `FM_AI_PRINT_V1`;
- adapter `orders` real;
- adapter `print` real.

Isto confirma que o desenho original já prevê adapter comercial separado do fake de teste.

### 2.5 Persistência/schema

O patrimônio de impressão está incluído no conjunto de operações de restaurante já existente. A F9 não parte de necessidade conhecida de migration nova. Qualquer migration adicional exige prova objetiva de drift antes de ser criada.

### 2.6 Testes existentes

Há testes unitários dedicados em `tests/unit/impressao/test_impressao.py`, cobrindo o domínio/spool. Os testes atuais não equivalem a Commercial Runtime E2E com adapter físico/real.

## 3. Current — lacunas comerciais objetivas

### B9-01 — Adapter comercial real ausente

Não existe hoje adapter de impressão comercial capaz de encaminhar o job para uma impressora/rede/spool de SO real.

**Regra:** implementar a porta existente; não alterar o domínio para acomodar provider específico.

### B9-02 — Composition root comercial ausente/incompleto

Não há fronteira comercial consolidada que construa `ServicoSpoolImpressao` com:
- identidade autenticada;
- repositório SQL real;
- auditoria real;
- destinos persistidos/configurados;
- adapter `print` real selecionado pelo runtime registry.

### B9-03 — KDS → spool ainda não fechado no runtime comercial

O KDS já produz a informação autoritativa necessária, mas falta provar a ligação governada entre o evento/ação canônica de produção e o enfileiramento idempotente do ticket por setor.

### B9-04 — Configuração de destinos/impressoras comerciais

É necessário definir de onde vêm `impressora_id`, setor, ativação e política de tentativas no runtime comercial sem hardcode por tenant.

### B9-05 — Fitness anti-fake e fail-closed

Falta gate explícito garantindo que:
- `ImpressoraFake` não seja selecionável no commercial default;
- ausência/configuração inválida de adapter comercial não gere falso sucesso;
- falha de impressão não reverta KDS/Pedido.

### B9-06 — Resiliência operacional

Falta prova integrada de:
- retry;
- contingência;
- idempotência/replay;
- concorrência/CAS;
- reimpressão auditada;
- isolamento tenant/unidade;
- recuperação após indisponibilidade do adapter.

### B9-07 — Commercial Runtime E2E / evidência real

Falta executar a jornada comercial:
Pedido/KDS real → spool persistente → adapter comercial → confirmação/falha controlada → evidência persistida.

A homologação final de hardware depende de impressora/adaptador real disponível no ambiente físico/comercial.

## 4. Target da Fase 9

Ao final da F9:
1. KDS permanece autoridade da produção.
2. Impressão é side effect opcional e desacoplado.
3. Todo ticket nasce no spool persistente e idempotente existente.
4. Um composition root comercial constrói o serviço com identidade e adapters reais.
5. `PortaImpressora` é implementada por adapter comercial plugável.
6. Configuração de destino é tenant/unidade/setor-safe.
7. Falha de hardware/rede nunca bloqueia a cadeia do pedido.
8. Retry/contingência/reimpressão ficam observáveis e auditáveis.
9. Fake permanece apenas em testes.
10. Não há migration nova sem drift comprovado.

## 5. Sequência de execução

### F9-A — Current → Target + System Design
- inventário do patrimônio;
- mapa de blockers;
- fronteiras e invariantes;
- plano de implementação.

### F9-B — Commercial adapter/composition boundary
- composition root real;
- provider/adapter boundary;
- fitness anti-fake;
- flags/readiness coerentes.

### F9-C — KDS/Event → Spool
- ligação governada e idempotente;
- sem commit escondido;
- sem rollback cruzado KDS ↔ impressão;
- tenant/unidade preservados.

### F9-D — Resiliência
- retry;
- contingência;
- replay/idempotência;
- CAS/concorrência;
- reimpressão auditada;
- isolamento.

### F9-E — Commercial Runtime E2E
- PostgreSQL/migrations oficiais;
- app/runtime comercial sem TEST_MODE;
- KDS real;
- spool real;
- adapter comercial;
- evidência física/real quando disponível;
- matriz completa verde antes de fechamento.

## 6. Critérios de não-regressão

- nenhuma mudança de autoridade em Pedido/KDS/Pagamento/Estoque;
- nenhuma permissão ampliada sem decisão explícita;
- nenhum commit escondido em UI/service/repository;
- nenhuma dependência obrigatória de uma impressora única;
- nenhum provider hardcoded por tenant;
- nenhum dado sensível de pagamento/endereço/contato no ticket operacional sem necessidade explícita;
- impressão deve degradar para retry/contingência, nunca para corrupção da operação.

## 7. Decisão F9-A

O patrimônio de impressão é **reutilizável/canônico**. A Fase 9 é um cutover de composição, adapter e eventos — não um projeto de reescrita.

Status após este inventário: **F9-A em fechamento documental; implementação comercial ainda não iniciada**.
