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
| KCA-06 Public Signup + Verification | PASS — `1569253f69db951bdb1c5ac36a7c9908d40483b4` |
| KCA-G6 | PASS |
| KCA-07 Trial Engine | PASS — `f3af1ba4aab2d16992ada5ed1fd5b35b5ad1ab10` |
| KCA-G7 | PASS |
| KCA-08 Subscription Engine | PASS — `e5f63d6ee7bba2e19ad4daf5102e36116ee9f11d` |
| KCA-G8 | PASS |
| KCA-09 Billing Provider Abstraction | PASS — `640e63595046fbd68df4ff129b2cb156e845c28a` |
| KCA-G9 | PASS |
| KCA-10+ | NÃO INICIADO |

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


## Certificação KCA-06

- Functional candidate: `1569253f69db951bdb1c5ac36a7c9908d40483b4`.
- Certification documentation commit: `d18c436fa856b3c9952b3b8c5b1019cf85584300` (record) + tracker certification commit.
- Migration: `0054_commercial_signup_v1`.
- Public signup permanece desabilitado por padrão.
- Verification token: uso único, hash persistido, expiração e replay protection.
- Anti-enumeration e rate limit: PASS.
- Payload público não controla tenant/plano/entitlement: PASS.
- Provisioning delegado ao KCA-05 Orchestrator: PASS.
- KCA targeted: 115 passed, 2 warnings.
- Full Python: 1716 passed, 5 skipped, 102 warnings.
- Schema baseline: 122 tabelas.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- Web Node: 14 tests, 0 skipped.
- 17/17 workflows do candidate SHA: SUCCESS.
- KCA-G6: PASS.
- KCA-07+: NÃO INICIADO.


## Execução KCA-07 — abertura

- Base reconciliada: `staging/kordena-premium` @ `40e2029019fb426cb22f55ebf7137474661bfda5`.
- Nova branch: `feat/kordena-commercial-kca07-kca09`.
- Escopo autorizado: KCA-07 → G7 → KCA-08 → G8 → KCA-09 → G9; STOP antes de KCA-10.
- Governança: sem merge, sem deploy, sem `main`, sem cliente/trial/billing/provider real.
- Evidência baseline funcional herdada do HEAD certificado KCA-G6: 17/17 workflows SUCCESS; full Python 1716 passed, 5 skipped, 102 warnings; KCA targeted 115 passed; Web Node 14/14; schema 122 tabelas.


## Certificação KCA-07

- Candidate funcional: `f3af1ba4aab2d16992ada5ed1fd5b35b5ad1ab10`.
- Migration: `0055_commercial_trial_v1`.
- Trial policy: `KORDENA_TRIAL_30D_V1` — 30 dias UTC.
- Trial state machine / antiabuso / idempotência / expiração: PASS.
- Provisioning → Trial Engine → Entitlement Authority: PASS.
- Schema baseline: 124 tabelas; SHA `a9cedb852fd163eb96bd09f7c38a09ceb4478e8c0a6807f653b5d307469c25e1`.
- KCA targeted: 127 passed, 2 warnings.
- Full Python: 1728 passed, 5 skipped, 102 warnings.
- Web Node: 14/14; ESLint/TypeScript/Next build/diff: PASS.
- 13/13 workflows do candidate SHA: SUCCESS.
- KCA-G7: PASS.
- KCA-08 autorizado; KCA-09+ ainda não iniciado.


## Certificação KCA-08

- Candidate funcional: `e5f63d6ee7bba2e19ad4daf5102e36116ee9f11d`.
- Migration: `0056_commercial_subscription_v1`.
- State machine PENDING / ACTIVE / PAST_DUE / SUSPENDED / CANCELED: PASS.
- Recuperação PAST_DUE/SUSPENDED → ACTIVE: PASS.
- Plan/version/price binding histórico: PASS.
- Trial ACTIVE → CONVERTED + Subscription ACTIVE: PASS.
- Idempotência / optimistic concurrency / unique subscription por Product Account: PASS.
- Entitlement Authority + projeção local: PASS.
- Cross-tenant e catálogo incompatível: fail-closed.
- Schema baseline: 125 tabelas; SHA `c6caa6d8ab1b58ae318b20e4b003b6db181f5211884e8a42eb4b09dd78ff0251`.
- KCA targeted: 134 passed, 2 warnings.
- Full Python: 1735 passed, 5 skipped, 102 warnings.
- Web Node: 14/14; ESLint/TypeScript/Next build/diff: PASS.
- 13/13 workflows do candidate SHA: SUCCESS.
- KCA-G8: PASS.
- KCA-09 autorizado somente após recertificação do HEAD documental; KCA-10+ não iniciado.


## Certificação KCA-09

- Candidate funcional: `640e63595046fbd68df4ff129b2cb156e845c28a`.
- Migration: não aplicável; nenhuma persistência nova necessária neste bloco.
- BillingProvider provider-neutral: PASS.
- Operações: create_customer / create_checkout / create_subscription / cancel_subscription / change_subscription / fetch_transaction / verify_webhook.
- Error mapping retryable vs terminal: PASS.
- Timeout explícito + idempotency key + correlation id: PASS.
- Retry automático oculto: NÃO; policy permanece externa/governada.
- Secret isolation: `SecretStore` + secret reference + `SecretValue` mascarado: PASS.
- Provider concreto/SDK no domínio central: NÃO.
- Billing SaaS FM separado de pagamentos operacionais Kordena: PASS.
- KCA-10 webhook inbox/reconciliation: NÃO INICIADO.
- Schema baseline: 125 tabelas; SHA `c6caa6d8ab1b58ae318b20e4b003b6db181f5211884e8a42eb4b09dd78ff0251`.
- KCA targeted: 143 passed, 2 warnings.
- Full Python: 1744 passed, 5 skipped, 102 warnings.
- Web Node: 14/14; ESLint/TypeScript/Next build/diff: PASS.
- 13/13 workflows do candidate SHA: SUCCESS.
- KCA-G9: PASS.
- STOP obrigatório aplicado antes do KCA-10.
