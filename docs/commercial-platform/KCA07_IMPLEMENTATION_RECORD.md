# KCA-07 — Implementation Record

## Escopo
Trial Engine canônico de 30 dias, com autoridade server-side, UTC, antiabuso, idempotência, expiração determinística e integração com Provisioning/Entitlement.

## Candidate funcional
- SHA: `f3af1ba4aab2d16992ada5ed1fd5b35b5ad1ab10`
- Base: `staging/kordena-premium@40e2029019fb426cb22f55ebf7137474661bfda5`

## Persistência
- Migration: `0055_commercial_trial_v1`
- Tabelas novas: `fm_commercial_trial_policies_v1`, `fm_commercial_trials_v1`
- Schema baseline: 124 tabelas
- Schema SHA-256: `a9cedb852fd163eb96bd09f7c38a09ceb4478e8c0a6807f653b5d307469c25e1`

## Controles certificados
- State machine: PENDING → ACTIVE → CONVERTED/EXPIRED/REVOKED.
- Política versionada: `KORDENA_TRIAL_30D_V1`, 30 dias, relógio UTC do servidor.
- Elegibilidade derivada do Plan Catalog; nenhum plano comercial novo foi criado.
- Antiabuso por histórico de customer/product account, email verificado e override governado/auditado.
- Idempotency key + request hash + conflito de payload.
- Expiração idempotente e independente de frontend.
- Eventos Outbox: created/activated/expired/converted/revoked.
- Integração explícita KCA-05 Provisioning → Trial Engine.
- Entitlement Authority recalculado e projeção local atualizada.
- Cross-tenant fail-closed.
- INTERNAL_TEST marcado como excluído de KPI.

## Evidência de testes — candidate
- Compile: PASS.
- Migration manifest: PASS.
- Schema baseline: PASS.
- Ruff/mypy KCA: PASS.
- KCA targeted: **127 passed, 2 warnings**.
- Full Python: **1728 passed, 5 skipped, 102 warnings**.
- Web ESLint: PASS.
- Web TypeScript: PASS.
- Web Node: **14 tests, 14 pass, 0 fail, 0 skipped**.
- Next production build: PASS.
- Diff whitespace: PASS.
- GitHub Actions: **13/13 workflows SUCCESS** no candidate.

## Governança
- PR #126 permaneceu OPEN/DRAFT.
- Nenhum merge.
- Nenhum deploy público.
- Nenhum cliente/trial comercial externo real.
- Nenhum provider/billing real.
- Main não alterada.
- KCA-08 não foi iniciado antes da certificação do G7.

## Gate
**KCA-G7: PASS**

## Rollback / mitigação
Mudanças são aditivas e versionadas. Em caso de regressão posterior, manter histórico de trial e aplicar forward-fix; não apagar registros comerciais históricos.
