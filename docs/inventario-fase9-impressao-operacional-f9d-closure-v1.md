# ADENDO CANÔNICO — INVENTÁRIO FASE 9 — F9-D FECHADA

**Documento pai:** `docs/inventario-fase9-impressao-operacional-v1.md`  
**Issue:** #75  
**PR:** #79 (draft)  
**SHA técnico validado:** `75b9b947edc88d3b094916564c098999d3348cf5`  
**Data:** 04/09/2026

Este adendo reconcilia formalmente o inventário da Fase 9 após a conclusão técnica da F9-D, sem reescrever o histórico dos blocos F9-B/F9-C.

## Estado reconciliado

- F9-B: FECHADA
- F9-C: FECHADA
- F9-D: FECHADA TECNICAMENTE
- F9-E: LIBERADA

## Blockers

### B9-01 — Composition/Application comercial ausente
**FECHADO EM F9-B.**

### B9-02 — KDS → spool não composto
**FECHADO EM F9-C.**

### B9-03 — Adapter físico/comercial ausente
**FECHADO EM F9-D.**

Implementado adapter comercial RAW TCP/JetDirect em `infra/impressao/adapter_tcp.py`, com timeout explícito, porta padrão 9100, erro normalizado e sem Fake/test-runtime no caminho comercial.

### B9-04 — Destinos sem configuração comercial durável
**FECHADO EM F9-D.**

Destinos são resolvidos por tenant/unidade/setor em `infra/impressao/configuracao_sqlalchemy.py`, reutilizando `fm_configuracoes_estabelecimento_v1.parametros_operacionais`, com governança administrativa já existente.

### B9-05 — Superfície comercial ausente
**FECHADO EM F9-D.**

`app.py` expõe `Impressão Operacional`; a UI permite observabilidade do spool, processamento de pendentes/falhos, contingência e reimpressão sob RBAC.

### B9-06 — Evidência comercial/física ausente
**PERMANECE ABERTO PARA F9-E.**

Ainda falta a prova de ponta a ponta no runtime comercial e a prova física/manual com impressora real. Nenhuma evidência física foi presumida.

## Evidência F9-D

No SHA `75b9b947edc88d3b094916564c098999d3348cf5`:
- 29/29 workflows SUCCESS;
- Fase 9D Impressao Adapter Config UI Gate: SUCCESS;
- PR14 Impressao Gates: SUCCESS;
- Fase 9B: SUCCESS;
- Fase 9C: SUCCESS;
- Commercial Runtime Readiness V1: SUCCESS;
- Wave0 / Wave1 Authoritative / regressões transversais: SUCCESS.

## Readiness

`impressao_operacional` permanece corretamente em `CUTOVER_PENDING` porque ainda existe:
- `physical_printer_hardware_gate_pending`;
- `commercial_runtime_e2e = null`;
- `physical_test = null`.

Code blockers B9-01 a B9-05 estão fechados. O status só poderá evoluir após a F9-E produzir evidência real suficiente.

## Próximo bloco

**F9-E — Commercial Runtime E2E / físico**

Regras:
- sem merge;
- sem deploy;
- sem Fake/runtime_teste no caminho comercial;
- sem migration nova sem drift objetivo;
- sem fechar hardware físico sem teste real;
- merge/deploy somente com autorização humana explícita.
