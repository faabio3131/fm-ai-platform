# ADENDO CANÔNICO — INVENTÁRIO FASE 9 — F9-E COMERCIAL VALIDADA

**Documento pai:** `docs/inventario-fase9-impressao-operacional-v1.md`  
**Issue:** #75  
**PR:** #79 (draft)  
**SHA técnico validado:** `20a80f9d8f1c479ad95091d0537795a29503f80e`  
**Data:** 04/09/2026

Este adendo reconcilia o inventário da Fase 9 após a prova comercial de ponta a ponta da F9-E. Ele não encerra o gate físico/manual de impressora e não altera o histórico dos blocos F9-B/F9-C/F9-D.

## Estado reconciliado

- F9-B: FECHADA
- F9-C: FECHADA
- F9-D: FECHADA TECNICAMENTE
- F9-E — Commercial Runtime E2E: FECHADA TECNICAMENTE
- F9-E — hardware físico/manual: **PENDENTE — DIFERIDO PARA HOMOLOGAÇÃO FINAL V1**
- Fase 9 / cutover final: `CUTOVER_PENDING`
- Continuidade técnica: **LIBERADA PARA FASE 10**

## Blockers

### B9-01 — Composition/Application comercial ausente
**FECHADO EM F9-B.**

### B9-02 — KDS → spool não composto
**FECHADO EM F9-C.**

### B9-03 — Adapter físico/comercial ausente
**FECHADO EM F9-D.**

### B9-04 — Destinos sem configuração comercial durável
**FECHADO EM F9-D.**

### B9-05 — Superfície comercial ausente
**FECHADO EM F9-D.**

### B9-06 — Evidência comercial/física

#### B9-06a — Commercial Runtime E2E
**FECHADO EM F9-E.**

Evidência autoritativa:
- workflow `Fase 9E Impressao Commercial Runtime E2E Gate`;
- run #16 / ID `33908356204`;
- job ID `101138594119`;
- PostgreSQL 16 + migrations oficiais;
- `app.py` comercial sem `FM_AI_TEST_MODE`;
- login COZINHA real;
- Pedido/KDS cria spool;
- job original persiste `impresso`, tentativa 1;
- transporte RAW TCP capturou 165 bytes com `pedido-f8e` e `Burger F8-E`;
- reimpressão persiste `pendente` e vinculada ao original;
- GARCOM é negado por RBAC;
- estado final confirma ausência de mutação indevida.

#### B9-06b — Impressora física/manual
**PERMANECE ABERTO — PENDÊNCIA DIFERIDA PARA A HOMOLOGAÇÃO FINAL DA V1.**

O listener TCP não substitui uma impressora física. Ainda é necessário validar manualmente pelo menos:
- modelo/firmware e protocolo aceito;
- conectividade real até a impressora;
- impressão em papel;
- largura/encoding/corte;
- ticket por setor;
- reimpressão física;
- indisponibilidade/contingência no ambiente real.

Por decisão de execução de 04/09/2026, essa dependência de hardware real fica registrada para a fase final de homologação, seguindo o mesmo princípio usado para pendências externas que dependem de ambiente/provedor real, como Mercado Pago, Meta e PagBank. O diferimento não equivale a aprovação nem homologação; apenas impede que uma dependência externa indisponível paralise o restante do cutover técnico da V1.

## Evidência transversal

No SHA `20a80f9d8f1c479ad95091d0537795a29503f80e`, a matriz final ficou **35/35 workflows SUCCESS**.

O único vermelho inicial fora da F9-E foi um timeout do E2E CRM/PDV cashback dentro do `PR11 Salao Gates`. A reexecução do mesmo job passou sem mudança de código, classificando a ocorrência como transitória e evitando alteração especulativa no helper global de combobox.

## Readiness

A reconciliação correta permanece:
- `impressao_operacional.status = CUTOVER_PENDING`;
- `code_blockers = []`;
- `external_blockers = [physical_printer_hardware_gate_pending]`;
- `commercial_runtime_e2e` preenchido com a evidência do run F9-E #16;
- `physical_test = null`.

Não promover para `COMMERCIAL_HOMOLOGATED` enquanto a prova física/manual permanecer ausente.

## Regra de continuidade

O B9-06b foi **diferido, não fechado**. Até a homologação final:
- não fechar B9-06b;
- não declarar cutover final físico da Fase 9;
- não remover o blocker físico;
- não preencher `physical_test` sem evidência real;
- não fazer merge;
- não fazer deploy;
- merge/deploy somente com autorização humana explícita.

Como os blockers de código B9-01 a B9-05 estão fechados e o B9-06a comercial foi validado, a sequência do Documento Mestre fica liberada para **Fase 10 — Expedição/Entregador**, iniciando obrigatoriamente por inventário Current → Target antes de código.
