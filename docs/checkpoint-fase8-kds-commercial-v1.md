# Checkpoint — Fase 8 — KDS Commercial Cutover V1

**Status:** FASE 8 FECHADA  
**Issue:** #73  
**PR:** #74 (draft)  
**Branch:** `recovery/v1-fase8-kds-commercial-cutover`  
**SHA técnico final:** `132e80bd2373aa30de42c4e17fea0037324ff7da`

## Escopo fechado

- F8-A: Current -> Target / System Design;
- F8-B: composition/RBAC commercial boundary;
- F8-C: Pedido -> KDS -> Estoque -> Outbox/Auditoria;
- F8-D: multi-setor, CAS/replay, fail-closed, cache read-only e isolamento;
- F8-E: Commercial Runtime E2E final.

## Evidência F8-E

`Fase 8E KDS Commercial Runtime E2E Gate` run 3 / `33685383011`: **PASS**.

O gate provou:
- PostgreSQL 16;
- migrations oficiais e schema current;
- `app.py` real;
- `FM_AI_TEST_MODE` ausente;
- identidade persistida e login real;
- COZINHA recebe KDS;
- GARCOM autenticado não recebe KDS;
- Pedido confirmado é roteado pela UI comercial;
- zero produção antes do clique e uma produção depois;
- `aguardando -> aceita -> em_preparo -> pronta`;
- Pedido macro `pronto`;
- reserva de Estoque `consumida`;
- saldo físico 8 e reservado 0;
- Outbox e Auditoria persistidos;
- COZINHA não possui ação de retirada.

## Correções reveladas pelo gate

1. O candidato `7827edbbb9fc228a7928c5fd6a801d2bda65ce85` revelou um locator Playwright incorreto para o selectbox Streamlit.
2. O candidato `c0496ac856a463f959a1017199af73b0a557783f` chegou ao roteamento real e foi corretamente bloqueado por `cozinha_nao_autorizada`, pois o cenário não tinha Pagamento V1 confirmado.
3. O candidato final `132e80bd2373aa30de42c4e17fea0037324ff7da` incluiu a pré-condição financeira válida sem ampliar RBAC nem relaxar a política de cozinha.

## Matriz transversal

**32/32 workflows verdes no SHA técnico final.**

## Readiness

`kds = COMMERCIAL_CANDIDATE`

- `code_blockers=[]`;
- `external_blockers=[]`;
- Commercial Runtime E2E registrado;
- browser comercial registrado;
- nenhuma migration F8 nova;
- nenhum Fake/Mock/runtime_teste no commercial default.

## Governança

Nenhum merge ou deploy foi realizado.

A promoção da PR #74 e qualquer deploy continuam dependentes de autorização humana explícita.
