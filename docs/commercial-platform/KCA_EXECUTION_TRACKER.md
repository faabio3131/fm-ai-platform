# KCA — Execution Tracker

| Bloco | Estado |
|---|---|
| KCA-00 System Design + ADRs | PASS |
| KCA-G0 | PASS |
| Baseline inicial | PASS — `922db0e3c568d8db232eecbf8059398e522e8603` |
| KCA-01 Commercial Registry | PASS — `c623dd4a8bef04105b720d80c7d44b97bce00189` |
| KCA-G1 | PASS |
| KCA-02 Global Identity + Memberships | PASS — `b67b1e82459657b691bac8429af501548edb9ac5` |
| KCA-03 Planos / Pricing / Promoções | PASS — `4934ee2db1febe51b1bb4fd114faf2eddb94c89f` |
| KCA-G3 | PASS |
| KCA-04 Entitlement Authority + Local Projection | PASS — `6b43c8454c13e6ac64d31907286c5e4af2979983` |
| KCA-G4 | PASS |
| KCA-05 Tenant Provisioning Saga | PASS — `3f0ee70c1e8483b2b6aad1a6c5737959ee555c98` |
| KCA-G5 | PASS |
| KCA-06+ | NÃO INICIADO |

## Baseline

- Python: 1644 passed, 5 skipped, 102 warnings.
- Web Node: 11 passed, 0 failed.
- Migration manifest: PASS.
- Schema baseline: PASS.
- ESLint/TypeScript/Next build/diff check: PASS.

Nenhum cliente real, trial, assinatura, billing real, usuário de homologação, merge ou abertura pública foi criado/executado.


## Certificação KCA-01

- Candidate funcional: `c623dd4a8bef04105b720d80c7d44b97bce00189`.
- KCA targeted: 16 passed.
- Full Python: 1660 passed, 5 skipped, 102 warnings.
- Web Node: 11 passed, 0 failed.
- Migration manifest/schema baseline/Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- 15 workflows do candidate SHA: SUCCESS.
- Nenhum merge, deploy, cliente real, trial, assinatura, billing real ou usuário de homologação foi executado.


## Certificação KCA-02

- Candidate funcional: `b67b1e82459657b691bac8429af501548edb9ac5`.
- Migration: `0050_global_identity_membership_v1`.
- Schema baseline: 109 tabelas.
- KCA/security targeted: 71 passed.
- Full Python: 1669 passed, 5 skipped, 102 warnings.
- Web Node: 11 passed, 0 failed.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- 16 workflows do candidate SHA: SUCCESS.
- KCA-G2: PASS.
- KCA-03+: NÃO INICIADO.


## Certificação KCA-03

- Candidate funcional: `4934ee2db1febe51b1bb4fd114faf2eddb94c89f`.
- Migration: `0051_commercial_catalog_v1`.
- Quatro planos canônicos sem preço/nome hardcoded:
  - `KORDENA_PLAN_A`
  - `KORDENA_PLAN_B`
  - `KORDENA_PLAN_C`
  - `KORDENA_PLAN_D`
- Catálogo versionado: PASS.
- Pricing versionado e agendável: PASS.
- Promoções versionadas: PASS.
- Step-up administrativo obrigatório: PASS.
- KCA targeted: 81 passed.
- Full Python: 1684 passed, 5 skipped, 102 warnings.
- Web Node: 11 passed, 0 failed.
- Schema baseline: 116 tabelas.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- 16 workflows do candidate SHA: SUCCESS.
- KCA-G3: PASS.
- KCA-04+: NÃO INICIADO.


## Certificação KCA-04

- Candidate funcional: `6b43c8454c13e6ac64d31907286c5e4af2979983`.
- Certification documentation commit: `d7a8a52fecaa2ac39509b423ec7f99f4f90279f6`.
- Migration: `0052_commercial_entitlement_v1`.
- Entitlement Authority + snapshots: PASS.
- Local Kordena projection + durable inbox: PASS.
- `entitlement.changed` outbox contract: PASS.
- Missing entitlement / stale beyond grace: fail-closed.
- Duplicate and out-of-order events: protected.
- Cross-tenant product-account mismatch: denied.
- KCA targeted: 90 passed.
- Full Python: 1691 passed, 5 skipped, 102 warnings.
- Schema baseline: 119 tables.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- 16 workflows do candidate SHA: SUCCESS.
- KCA-G4: PASS.
- KCA-05+: NÃO INICIADO.


## Certificação KCA-05

- Candidate funcional: `3f0ee70c1e8483b2b6aad1a6c5737959ee555c98`.
- Certification documentation commit: `87873b287f23e1e4d3a47416c1f0ccbd3db7c9de`.
- Migration: `0053_commercial_provisioning_v1`.
- Persisted Saga + explicit state machine: PASS.
- Idempotency + optimistic concurrency: PASS.
- Retry/restart/recovery: PASS.
- Logical compensation: PASS.
- Provisioning inbox/outbox: PASS.
- Duplicate tenant protection: PASS.
- Password not persisted in Saga: PASS.
- KCA-07 Trial Engine not anticipated; only `pending_kca07` binding exists.
- KCA targeted: 105 passed.
- Full Python: 1706 passed, 5 skipped, 102 warnings.
- Web Node: 11 passed, 0 failed.
- Schema baseline: 121 tables.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- 16 workflows do candidate SHA: SUCCESS.
- KCA-G5: PASS.
- KCA-06+: NÃO INICIADO.
