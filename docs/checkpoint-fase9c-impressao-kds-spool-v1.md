# CHECKPOINT F9-C — IMPRESSÃO KDS → SPOOL V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Issue:** #75  
**PR draft:** #76  
**Branch:** `recovery/v1-fase9-impressao-operacional-cutover`  
**SHA técnico final validado:** `c30fb3de5748dc3b7e53b0030e0fc62703cc2295`  
**Data:** 03/09/2026  
**Status:** F9-C FECHADA TECNICAMENTE / F9-D LIBERADA

## Escopo fechado

F9-C implementou a integração comercial KDS → spool sem transferir autoridade
operacional para a impressão.

A ordem transacional validada é:

1. KDS roteia e persiste a Produção;
2. a UoW autoritativa do KDS executa commit;
3. somente após o commit, a integração de impressão é acionada;
4. o spool é criado em UoW própria;
5. falha de spool é registrada como best-effort e não desfaz o KDS.

## Evidência objetiva

No SHA técnico final:

- `Fase 9C Impressao KDS Spool Gate` / run `33704029604`: PASS;
- `Commercial Runtime Readiness V1`: PASS;
- `PR10 KDS Gates`: PASS;
- `PR14 Impressao Gates`: PASS;
- `V1 Wave2 KDS`: PASS;
- matriz transversal: **27/27 workflows verdes**.

Os testes dedicados provam:

- replay idempotente do mesmo roteamento KDS produz exatamente um job;
- falha do spool não remove nem reverte a Produção KDS persistida;
- ticket usa dados canônicos de setor/item/pedido;
- `ImpressoraFake` permanece apenas no universo de testes.

## Correção de homologação

O primeiro candidato revelou uma falha exclusivamente no seed do teste:
`canal="balcao"` não pertence ao enum canônico `CanalAtendimento`.

O SHA final substituiu o seed por `canal="pdv"`, valor canônico válido.
Nenhuma regra de negócio foi alterada.

## Readiness após F9-C

Fechados:
- B9-01 — Application/UoW comercial;
- B9-02 — KDS → spool composto.

Permanecem:
- B9-03 — adapter físico/comercial;
- B9-04 — configuração durável de destinos por tenant/unidade/setor;
- B9-05 — superfície comercial de spool/contingência/reimpressão;
- B9-06 — Commercial Runtime E2E + prova física, reservado à F9-E;
- blocker externo `physical_printer_hardware_gate_pending`.

`impressao_operacional` permanece `CUTOVER_PENDING`.

## Regra de continuidade

A próxima etapa permitida é **F9-D — Adapter e Configuração Operacional**.

F9-D não autoriza:
- merge;
- deploy;
- uso comercial de `ImpressoraFake`;
- criação de migration sem drift objetivo;
- fechamento de hardware físico sem prova real.

A PR #76 permanece draft e qualquer merge/deploy depende de autorização humana
explícita.
