# Checkpoint — F8-B — KDS Commercial Boundary

**Data:** 02/09/2026  
**Issue:** #73  
**PR:** #74 (draft)  
**SHA técnico validado:** `34ff1cef4199d5be21c37a3224303c7f79b64061`

## Resultado

F8-B — composition/RBAC/fitness comercial — **FECHADA**.

O KDS não foi reescrito. O bloco corrigiu apenas a exposição comercial da
superfície e fortaleceu a defesa em profundidade:

- `app.py` só cria a aba KDS quando a feature está habilitada e a identidade
  ativa possui `PRODUCAO_VISUALIZAR`;
- nenhuma permissão/papel foi ampliado;
- renderer recusa `permissao_insuficiente` explicitamente;
- contexto/schema de E2E permanecem restritos a `FM_AI_TEST_MODE=1`;
- simulação offline continua fora do commercial default;
- UI não possui ownership de commit;
- Application + `UnitOfWorkV1` permanecem donos dos writes;
- migration oficial permanece `0010_kds_authoritative_runtime_v1`;
- nenhuma migration F8 foi criada.

## Evidência

- Fase 8B KDS Commercial Boundary Gate run 2 / `33675298080`: **PASS**;
- V1 Wave2 KDS run 144 / `33675298045`: **PASS**;
- PR10 KDS Gates run 369 / `33675298031`: **PASS**;
- V1 Wave0 Production Foundation run 209 / `33675298074`: **PASS**;
- PR11 Salão, PR12 Garçom, F7-F, Wave1, Hardening e regressões transversais: **PASS**;
- matriz final no SHA técnico: **29/29 workflows verdes**.

## Readiness

`kds = COMMERCIAL_CANDIDATE`

- `code_blockers = []`;
- SHA técnico F8-B registrado no readiness;
- `commercial_runtime_physical_gate_pending` permanece corretamente aberto;
- Commercial Runtime E2E/physical evidence final continuam reservados ao F8-E.

## Rollback

Antes de merge/deploy, rollback é reverter os commits F8-B. Nenhum dado de
Pedido, KDS, Estoque, Evento ou Auditoria deve ser apagado.

## Decisão

**F8-C — cadeia operacional canônica — LIBERADA.**

Nenhum merge e nenhum deploy foram executados.
