# ADENDO DE FECHAMENTO — INVENTÁRIO FASE 10 — EXPEDIÇÃO / ENTREGADOR V1

Este adendo preserva o inventário Current → Target original como baseline auditável e registra o fechamento dos blockers B10-01 a B10-05 em 04/09/2026.

## Fechamento dos blockers

### B10-01 — Contexto comercial de Expedição/Entregador
**FECHADO.** A UI comercial deriva `ContextoExecucao` da `IdentidadeUsuario` autenticada. Contexto injetado permanece permitido apenas sob `FM_AI_TEST_MODE=1` para regressão histórica.

### B10-02 — Superfície comercial autenticada
**FECHADO.** `pages/9_Expedicao_Entrega.py` compõe runtime comercial, autenticação, feature flag/adapters reais e RBAC para EXPEDICAO, ENTREGADOR, GERENTE e ADMINISTRADOR, falhando fechado para identidades sem alçada.

### B10-03 — KDS/Pedido PRONTO → Entrega/Expedição
**FECHADO.** `application/entrega_kds_handoff.py` executa handoff idempotente pós-commit KDS em UoW separada. Replay não duplica evento/versão; falha do handoff não desfaz o KDS autoritativo.

### B10-04 — Governança do entregador
**FECHADO.** O comercial lista e atribui somente identidades canônicas ativas, do mesmo tenant, com papel `ENTREGADOR` e unidade autorizada. A elegibilidade é revalidada dentro da UoW da atribuição. ID livre permanece somente no universo de testes históricos.

### B10-05 — Commercial Runtime E2E
**FECHADO.** O gate `Fase 10E Entrega Commercial Runtime E2E Gate`, run #2 (`33925204226`), comprovou a jornada em PostgreSQL 16 + browser + autenticação real + RBAC, sem `FM_AI_TEST_MODE`.

## Evidência final

SHA técnico: `022b282ce4fcf3310c6bd722355d10a7afda48a9`.

Matriz transversal: **29/29 workflows SUCCESS**.

Estado durável final comprovado:
- Pedido `pronto`;
- Entrega `entregue`;
- entregador `entregador-f10e`;
- versão 7;
- prova `proof://pedido-f8e`;
- eventos: `entrega.criada` → `entrega.aguardando_expedicao` → `entrega.aguardando_entregador` → `entrega.atribuida` → `entrega.coletada` → `entrega.em_rota` → `entrega.concluida`.

## Resultado

Os targets 1–10 do inventário da Fase 10 foram cumpridos sem migration nova e sem Fake/runtime_teste no caminho comercial.

Classificação final da Fase 10: **COMMERCIAL_CANDIDATE**.

A PR #81 permanece draft. Não houve merge nem deploy.
