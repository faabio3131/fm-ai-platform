# CHECKPOINT FASE 9D — IMPRESSÃO — ADAPTER, CONFIGURAÇÃO E UI V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Issue:** #75  
**PR:** #79 — draft  
**Branch:** `recovery/v1-fase9d-impressao-adapter-config-ui`  
**SHA técnico validado:** `75b9b947edc88d3b094916564c098999d3348cf5`  
**Data:** 04/09/2026  
**Status:** F9-D tecnicamente fechada; F9-E liberada para evidência comercial/física.

## 1. Escopo fechado

A F9-D fechou os blockers de código B9-03, B9-04 e B9-05 sem reescrever o domínio/spool existente e sem criar migration nova.

### B9-03 — Adapter comercial real
- `infra/impressao/adapter_tcp.py` implementa `ImpressoraTCPRaw`;
- transporte RAW TCP/JetDirect, com porta padrão 9100;
- timeout explícito e erro normalizado;
- nenhum `ImpressoraFake` ou `runtime_teste` no caminho comercial.

### B9-04 — Configuração durável de destinos
- `infra/impressao/configuracao_sqlalchemy.py` resolve destinos por tenant/unidade/setor;
- reutiliza `fm_configuracoes_estabelecimento_v1.parametros_operacionais` da Administração;
- configuração governada no Centro Administrativo com PIN/RBAC já canônicos;
- sem fallback entre tenants/unidades;
- nenhuma migration F9 nova.

### B9-05 — Superfície comercial
- `core/impressao/ui_comercial.py` expõe observabilidade do spool;
- `app.py` inclui a aba `Impressão Operacional` sob feature flag;
- operador pode processar jobs pendentes/falhos e observar contingência;
- reimpressão continua passando pelo serviço/Application e pelo RBAC `impressao.reimprimir`.

## 2. Evidência técnica

No SHA `75b9b947edc88d3b094916564c098999d3348cf5`:
- matriz transversal: **29/29 workflows SUCCESS**;
- `Fase 9D Impressao Adapter Config UI Gate`: SUCCESS;
- `PR14 Impressao Gates`: SUCCESS;
- `Fase 9B Impressao Commercial Boundary Gate`: SUCCESS;
- `Fase 9C Impressao KDS Spool Gate`: SUCCESS;
- `Commercial Runtime Readiness V1`: SUCCESS;
- `V1 Wave0 Production Foundation`: SUCCESS;
- `V1 Wave1 Authoritative Transactions`: SUCCESS;
- `PR16 Delivery Gates`: SUCCESS após reexecução, confirmando a falha E2E anterior como transitória;
- regressões KDS, Salão, Garçom, Entrega, Marketplaces, CRM, Gerente IA e hardening: SUCCESS.

## 3. Correções durante o bloco

1. O primeiro candidato revelou somente violações Ruff na nova UI; foram corrigidas sem relaxar lint e sem mascarar erros de domínio.
2. A segunda rodada revelou ordenação de imports em `infra/impressao/configuracao_sqlalchemy.py` e tipagem do stub de teste; ambas foram corrigidas objetivamente.
3. Um E2E antigo de Delivery falhou por não localizar temporariamente `fora_da_area_de_entrega`; os demais cenários e contratos estavam verdes e a reexecução posterior passou.

## 4. Readiness após F9-D

- `impressao_operacional = CUTOVER_PENDING`;
- code blockers B9-01/B9-02/B9-03/B9-04/B9-05: fechados;
- B9-06 permanece aberto exclusivamente para evidência comercial/física da F9-E;
- blocker externo `physical_printer_hardware_gate_pending` permanece;
- `commercial_runtime_e2e` permanece nulo até a F9-E;
- `physical_test` permanece nulo até prova real;
- nenhuma homologação física foi inventada.

## 5. Próximo bloco — F9-E

A F9-E deve provar, no mesmo SHA candidato:
1. PostgreSQL 16 + migrations oficiais;
2. `app.py` real sem `FM_AI_TEST_MODE`;
3. identidade/login comercial;
4. Pedido → KDS → spool;
5. adapter comercial em sucesso e contingência controlada;
6. reimpressão autorizada e negativa de RBAC;
7. navegador real;
8. prova física/manual com impressora real quando o hardware estiver disponível.

## 6. Regras de continuidade

- PR #79 permanece draft;
- sem merge;
- sem deploy;
- sem Fake/test runtime no caminho comercial;
- sem migration nova sem drift objetivo;
- sem fechar `physical_printer_hardware_gate_pending` sem evidência real;
- merge/deploy somente com autorização humana explícita.
