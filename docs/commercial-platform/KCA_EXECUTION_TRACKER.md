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
| KCA-04+ | NÃO INICIADO |

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
