# CHECKPOINT FASE 10 — EXPEDIÇÃO / ENTREGADOR — COMMERCIAL RUNTIME V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Fase:** 10 — Expedição / Entregador  
**Branch:** `recovery/v1-fase10-expedicao-entregador-cutover`  
**PR:** #81 (draft)  
**Data:** 04/09/2026  
**Status técnico:** COMMERCIAL CANDIDATE — F10-A/B/C/D/E concluídos

## 1. Autoridade técnica

SHA técnico validado:
`022b282ce4fcf3310c6bd722355d10a7afda48a9`

Gate dedicado:
`Fase 10E Entrega Commercial Runtime E2E Gate` — run #2 — run id `33925204226` — SUCCESS.

Matriz transversal do mesmo SHA: **29/29 workflows SUCCESS**.

## 2. Evidência Commercial Runtime F10-E

O gate executou em PostgreSQL 16, ambiente staging comercial, migrations oficiais, autenticação SQLAlchemy real e `FM_AI_TEST_MODE` ausente.

Jornada comprovada no navegador:
1. COZINHA autenticada roteou o item e concluiu KDS até `PRONTO`;
2. handoff pós-commit promoveu a Entrega para `aguardando_expedicao`;
3. EXPEDIÇÃO autenticada concluiu o checklist;
4. EXPEDIÇÃO atribuiu somente o usuário canônico elegível `entregador-f10e`;
5. GARCOM autenticado foi recusado pelo RBAC e não produziu mutação;
6. ENTREGADOR autenticado confirmou coleta, saída em rota e conclusão da entrega.

## 3. Evidência PostgreSQL durável

Após COZINHA/KDS:
- Pedido: `pronto`;
- KDS: `pronta`;
- Entrega: `aguardando_expedicao`;
- versão Entrega: 2.

Após EXPEDIÇÃO:
- Entrega: `atribuida`;
- entregador: `entregador-f10e`;
- versão Entrega: 4;
- checklist concluído e atribuição persistidos.

Após tentativa indevida do GARCOM:
- Entrega permaneceu `atribuida`;
- entregador permaneceu `entregador-f10e`;
- versão permaneceu 4.

Estado final após ENTREGADOR:
- Pedido: `pronto`;
- Entrega: `entregue`;
- entregador: `entregador-f10e`;
- versão Entrega: 7;
- prova: `proof://pedido-f8e`;
- `producao_pronta_em`, `checklist_concluido_em`, `atribuida_em`, `coletada_em`, `saiu_em` e `entregue_em` persistidos.

Trilha de eventos, em ordem:
1. `entrega.criada`;
2. `entrega.aguardando_expedicao`;
3. `entrega.aguardando_entregador`;
4. `entrega.atribuida`;
5. `entrega.coletada`;
6. `entrega.em_rota`;
7. `entrega.concluida`.

## 4. Qualidade e regressão

No gate dedicado:
- Ruff: verde;
- mypy: verde — 14 arquivos;
- regressões de Entrega: 17 testes verdes;
- browser COZINHA: verde;
- browser EXPEDIÇÃO: verde;
- browser GARCOM/RBAC: verde;
- browser ENTREGADOR: verde;
- evidências PostgreSQL intermediárias e final: verdes.

A matriz transversal completa do SHA técnico também fechou 29/29 verde.

## 5. Decisões de arquitetura preservadas

- nenhuma migration F10 foi criada: o schema oficial existente foi suficiente;
- nenhuma identidade paralela de entregador foi criada;
- nenhum ID livre/hardcoded de entregador permanece no caminho comercial;
- validação de entregador elegível ocorre também dentro da mesma UoW da atribuição;
- handoff KDS → Entrega ocorre depois do commit autoritativo do KDS, em UoW separada;
- falha logística não desfaz KDS/Pedido já commitados;
- nenhum Fake/runtime_teste é usado como autoridade do caminho comercial.

## 6. Readiness

`entrega` pode avançar de `CUTOVER_PENDING` para `COMMERCIAL_CANDIDATE`:
- code blockers: nenhum;
- external blockers específicos da Entrega: nenhum;
- Commercial Runtime E2E: comprovado no run #2;
- desktop Chromium: comprovado no mesmo gate.

Isso não promove automaticamente outros módulos e não apaga pendências externas/físicas de outras fases.

## 7. Pendências separadas e preservadas

Continuam separadas da Fase 10, sem alteração por este checkpoint:
- homologação física da impressora da Fase 9, diferida para o fechamento final;
- homologações externas legítimas, como Mercado Pago/Pix, Meta/WhatsApp e PagBank, conforme inventário global.

## 8. Governança

A Fase 10 está tecnicamente fechada como **COMMERCIAL_CANDIDATE**. A PR #81 permanece draft.

**Nenhum merge foi autorizado ou executado. Nenhum deploy foi autorizado ou executado.**
