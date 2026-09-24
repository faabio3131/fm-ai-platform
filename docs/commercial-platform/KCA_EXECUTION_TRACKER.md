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
| KCA-09B Multi-Provider Configuration & Receiving Accounts | PASS — `b38f20b0c7520e39203076a07923c76767ffb970` |
| KCA-G9B | PASS |
| KCA-10 Webhook Inbox + Reconciliation | PASS — `ccdf7883f63d184e34dab51ad26babc69b3edf9a` |
| KCA-G10 | PASS |
| KCA-11 Expiração + Paywall + Recovery | PASS — `f61c86ae44f88ecd38e050217ccd55960c4a9fd0` |
| KCA-G11 | PASS |
| KCA-12 FM Control Center — Integração + Commercial Control Plane | PASS — `b35ba198ecd9a667f0473829c16562e2474a1f31` |
| KCA-G12 | PASS — recertificação documental obrigatória |
| KCA-13 Observability / Antiabuse / FinOps | PASS / MERGED — pré-merge `72cb89feadc2930bf08a22d57edd31afc9bb7c54`; staging `05c65c16ef380158b4602780511a9997e08cb5bb`; pós-merge Vercel + Railway SUCCESS |
| KCA-14 Security Hardening + Tenant Isolation Audit | PASS / MERGED — PR #133; merge `16975a52202ec6602499bb4981d85461977d9952`; pós-merge Vercel + Railway SUCCESS; CRITICAL OPEN=0; HIGH OPEN=0 |
| KCA-15 Homologação Interna Nova FM | PASS CANDIDATE — `ed79e7ca7f5f5b156e247f37d1c8143e6cc8fd37`; PostgreSQL staging-mode; INTERNAL_TEST real persistido; awaiting exact-head doc recertification + merge |
| KCA-16 Full Commercial E2E + Audit & Fix | NÃO INICIADO |
| KCA-17 Final Readiness / Release | NÃO INICIADO |

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


## Execução KCA-09B — abertura

- KCA-G9 previamente certificado.
- Prompt formal: `docs/commercial-platform/KCA09B_EXECUTION_PROMPT.md`.
- Objetivo: configuração multi-provider, contas recebedoras e roteamento governado antes do KCA-10.
- Nenhum provider, credencial, conta financeira ou cobrança real será criado.
- FM Control Center permanece apenas como futura superfície administrativa; autoridade continua na FM Commercial Platform.
- KCA-10 permanece NÃO INICIADO até KCA-G9B PASS.


## Certificação KCA-09B

- Candidate funcional: `b38f20b0c7520e39203076a07923c76767ffb970`.
- Migration: `0057_commercial_billing_config_v1`.
- Provider accounts multi-provider/configuráveis: PASS.
- Provider code aberto/provider-neutral: PASS.
- Conta DRAFT sem credencial: PASS.
- Onboarding/rotação posterior em Secret Vault cifrado: PASS.
- Secret reference somente; nenhum segredo em claro na configuração/API: PASS.
- Isolamento `vault:*` por tenant/unidade: PASS.
- Adapter registry runtime: PASS.
- Teste de conexão não financeiro: PASS.
- Ativação somente após connection test PASS: PASS.
- Sandbox/Production: PASS.
- Métodos de pagamento e capabilities recurring/webhooks: PASS.
- Routing primary + fallbacks: PASS.
- Rota incompatível/ausente: fail-closed.
- Fallback não executa cobrança automática: PASS.
- RBAC + step-up administrativo: PASS.
- API preparada para futura superfície do FM Control Center: PASS.
- KCA-10 Webhook Inbox/Reconciliation: NÃO INICIADO.
- Schema baseline: 127 tabelas; SHA `dfa71718df03907d1cf44cdb7f54ce774d7b05395b4a9ef20885d90951e88c55`.
- KCA targeted: 161 passed, 2 warnings.
- Full Python: 1762 passed, 5 skipped, 102 warnings.
- Web Node: 14/14; ESLint/TypeScript/Next build/diff: PASS.
- 13/13 workflows do candidate funcional: SUCCESS.
- KCA-G9B: PASS.
- STOP obrigatório mantido antes do KCA-10.


## Execução KCA-10 — abertura

- KCA-G9B previamente certificado no HEAD documental `de02f8c2c7c816472425ae4fbba95d440ab24d56` com 13/13 workflows SUCCESS.
- Prompt formal: `docs/commercial-platform/KCA10_EXECUTION_PROMPT.md`.
- Escopo: durable webhook inbox, signature verification, event ID/body hash, idempotência, replay protection, normalization, ordering, retry/DLQ/replay controlado, Billing Ledger mínimo e reconciliation.
- KCA-11 Paywall/Recovery/Dunning permanece NÃO INICIADO.
- Nenhum provider, credencial, conta financeira ou cobrança real será utilizado.


## Certificação KCA-10

- Candidate funcional: `ccdf7883f63d184e34dab51ad26babc69b3edf9a`.
- Migration: `0058_commercial_billing_events_v1`.
- Durable Webhook Inbox: PASS.
- Assinatura provider-neutral por headers: PASS.
- Body hash/idempotência/replay protection: PASS.
- Payload válido persistido cifrado antes da normalização: PASS.
- Raw payload/assinatura não persistidos em claro: PASS.
- Normalização após Inbox durável: PASS.
- Binding assinatura interna↔externa: PASS.
- Ordering cursor/sequence/time: PASS.
- Provider resend idempotente: PASS.
- Retry governado/backoff: PASS.
- DEAD_LETTER por exaustão: PASS.
- Replay administrativo controlado: PASS.
- Billing Transaction Ledger: PASS.
- Reconciliation IN_SYNC/REPAIRED: PASS.
- Subscription Engine canônico preservado: PASS.
- KCA-11 Paywall/Recovery/Dunning: NÃO INICIADO.
- Schema baseline: 132 tabelas; SHA `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- KCA targeted: 187 passed, 2 warnings.
- Full Python: 1788 passed, 5 skipped, 102 warnings.
- Web Node: 14/14; ESLint/TypeScript/Next build/diff: PASS.
- Candidate funcional: 13/13 workflows SUCCESS.
- KCA-G10: PASS.
- STOP obrigatório mantido antes do KCA-11.

## Certificação KCA-11

- Candidate preliminar substituído: `f6b529d0cdfd14b11e5b82f9f7ac89803a2f0ea8`.
- Candidate funcional certificado: `f61c86ae44f88ecd38e050217ccd55960c4a9fd0`.
- Implementation record: `docs/commercial-platform/KCA11_IMPLEMENTATION_RECORD.md`.
- Migration: não aplicável; nenhuma mudança de schema no KCA-11.
- Schema baseline: 132 tabelas; SHA `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- Expiração server-side/UTC no boundary exato: PASS.
- Scheduler atrasado + execução repetida/reprocessável: PASS.
- Relógio determinístico do scheduler propagado ao entitlement: PASS.
- Trial expirado → `TRIAL_EXPIRED` / `BILLING_ONLY`: PASS.
- Request gate backend fail-closed: PASS.
- Login e superfícies comerciais mínimas preservadas: PASS.
- API operacional protegida retorna bloqueio comercial: PASS.
- Paywall com planos/checkout/suporte/logout: PASS.
- Dados operacionais preservados; nenhum fluxo de bloqueio apaga dados: PASS.
- Trial EXPIRED → Subscription ACTIVE → Entitlement FULL: PASS.
- Recovery repetido/idempotente: PASS.
- Stale/missing entitlement: fail-closed.
- Cross-tenant: fail-closed.
- KCA targeted: 192 passed, 2 warnings.
- Full Python: 1793 passed, 5 skipped, 102 warnings.
- Web Node: 16 passed, 0 failed, 0 skipped.
- Migration manifest/schema baseline/Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- Candidate técnico final `f61c86ae44f88ecd38e050217ccd55960c4a9fd0`: 8/8 GitHub Actions SUCCESS + Vercel SUCCESS.
- KCA-G11: PASS.
- PR #127: MERGED em `staging/kordena-premium`; merge commit `87f4e2f47abcc5bd0be372c477bec612aed0a482`.
- KCA-12/FM Control Center: executado e certificado em candidates funcionais; ver seção KCA-12.
- Nenhum deploy público, cliente/trial/assinatura real, provider, credencial ou cobrança real foi executado.


## Certificação KCA-12

- Implementation record: `docs/commercial-platform/KCA12_IMPLEMENTATION_RECORD.md`.
- Base Kordena: `staging/kordena-premium` @ `87f4e2f47abcc5bd0be372c477bec612aed0a482`.
- Candidate funcional Kordena: `b35ba198ecd9a667f0473829c16562e2474a1f31`.
- PR Kordena: #128 — OPEN/DRAFT durante a certificação.
- Candidate funcional FMCC: `5d4843d4bd5ac403c59a0d491413f4482a0318f9`.
- PR FMCC: #16 — OPEN/DRAFT durante a certificação.
- Migration Kordena: não aplicável; nenhuma migration nova.
- Schema baseline Kordena: 132 tabelas; SHA `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- Read contract `kordena.fmcc.commercial.v1`: PASS.
- Clientes / Product Accounts / trials / subscriptions / billing / entitlement: PASS.
- Usuários/unidades: contagens minimizadas sem PII: PASS.
- INTERNAL_TEST excluído dos facts de KPI: PASS.
- Administração dos quatro planos via `AplicacaoCatalogoComercialV1`: PASS.
- Nome/descrição/preço/periodicidade/benefício/limite/promoção/ativação futura: PASS.
- Versionamento / idempotência / audit trail: PASS.
- Preview/diff + confirmação + password step-up: PASS.
- FMCC sem SQL direto no banco operacional Kordena: PASS.
- Nenhuma segunda autoridade comercial: PASS.
- Cross-tenant control tenant/source isolation: PASS.
- Secret reference/origin allowlist/token isolation: PASS.
- Contract drift/incomplete snapshot: fail-closed.
- MRR/ARR/churn/inadimplência monetária/saúde/custos/suporte ausentes: exibidos como indisponíveis com dependência explícita; nenhum valor inventado.
- KCA targeted Kordena: 202 passed, 1 warning.
- Full Python Kordena: 1803 passed, 5 skipped, 101 warnings.
- Web Node Kordena: 16 passed, 0 failed, 0 skipped.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- Kordena candidate: 7/7 GitHub Actions SUCCESS + Vercel SUCCESS.
- FMCC: 33 test files / 118 tests PASS; lint/typecheck/migrations/build/Docker/runtime dependency audit: PASS.
- FMCC Foundation Gate: SUCCESS.
- KCA-G12: PASS nos candidates funcionais.
- Fechamento depende da recertificação do HEAD documental gerado por este registro/tracker.
- KCA-12 ainda não está integrado na staging neste ponto documental; bloco cognitivo permanece proibido até o merge KCA-12 e verificação pós-merge.
- KCA-13 permanece NÃO INICIADO.


## Execução KCA-13 — abertura

- Base Kordena reconciliada: `staging/kordena-premium` @ `9c52fd998e04c4d723171917f3776c9da7295858`.
- Base FMCC reconciliada: `main` @ `5b433832e599f07a7b39c373c508733775d78406`.
- Branch Kordena: `feat/kordena-commercial-kca13-observability-antiabuse-finops`.
- Branch FMCC: `feat/fmcc-kca13-kordena-observability`.
- CURRENT confirmou AI FinOps, audit trail, correlation IDs e KCA-12 já existentes; KCA-13 reutiliza essas autoridades.
- Escopo: projeção read-only de observabilidade, métricas governadas, antiabuso, health, alertas determinísticos, tracing e FinOps.
- INTERNAL_TEST permanece excluído de KPIs comerciais.
- Custo de infraestrutura permanece unavailable até fonte governada real.
- Nenhuma migration nova foi criada.
- Candidate funcional Kordena: `10cb4ac5da96947e0298616af9a3e56c37fccb23`.
- KCA targeted: 212 passed, 1 warning.
- Full Python: 1813 passed, 5 skipped, 101 warnings.
- Web Node: 16 passed.
- Runtime Readiness / KCA Commercial / WP-031 Master / WP-031L Parity: SUCCESS.
- FMCC `main@0e37eecb69d00361216468891c7442b74b993b29`: Foundation Gate pós-merge SUCCESS — 48 test files / 185 tests; 6/6 E2E; secret scan 232 arquivos; build/runtime/Docker/dependency audit HIGH PASS.
- 4 advisories MODERATE transitivos no npm; nenhum HIGH/CRITICAL bloqueante.
- HEAD documental recertificado: `8325913147bb2019b617249e66410ff14c0beba7`.
- Runtime Readiness #1135 / KCA Commercial #289 / WP-031 Master #298 / WP-031L Parity #308 / cleanup #835: SUCCESS.
- KCA-G13: PASS canônico.
- PR Kordena #130 permanece OPEN/DRAFT e não mergeada.
- KCA-14 permanece NÃO INICIADO.


## Certificação KCA-13

- Implementation/certification record: `docs/commercial-platform/KCA13_IMPLEMENTATION_RECORD.md`.
- Base Kordena: `staging/kordena-premium@9c52fd998e04c4d723171917f3776c9da7295858`.
- Candidate funcional: `10cb4ac5da96947e0298616af9a3e56c37fccb23`.
- PR Kordena #130: OPEN/DRAFT; não mergeada.
- Migration: não aplicável; KCA-13 é projeção read-only sobre autoridades existentes.
- Contrato: `kordena.observability.kca13.v1`, aditivo ao `kordena.fmcc.commercial.v1`.
- INTERNAL_TEST excluído dos KPIs: PASS.
- Public Signup → account_class TRIAL: fitness contract PASS.
- Kordena × sibling-product isolation por Product Account: PASS, incluindo regressão Kordena + IRON.
- MRR/ARR sem FX inventado e moedas separadas: PASS.
- Missing/unavailable != zero: PASS.
- Churn com base histórica insuficiente → unavailable: PASS.
- Antiabuso observável sem risk score arbitrário: PASS.
- Health + alertas determinísticos: PASS.
- Correlation IDs/tracing: PASS.
- AI FinOps existente reutilizado: PASS.
- Infra cost: explicitamente unavailable enquanto não existir fonte governada.
- Limitação conhecida: usage_by_plan usa o plano corrente no as_of; não reconstrói histórico de mudança de plano dentro da janela.
- KCA targeted: 212 passed, 1 warning.
- Full Python: 1813 passed, 5 skipped, 101 warnings.
- Web Node: 16 passed.
- Ruff/mypy/Migration Manifest/Schema Baseline/ESLint/TypeScript/Next build/diff: PASS.
- Runtime Readiness #1134: SUCCESS.
- KCA Commercial Gate #288: SUCCESS.
- WP-031 Master Gate #297: SUCCESS.
- WP-031L Regression Channel Parity #307: SUCCESS.
- FMCC PR #19 foi mergeada concorrentemente durante a execução; merge não foi efetuado por este fluxo.
- FMCC current main: `0e37eecb69d00361216468891c7442b74b993b29`.
- FMCC pós-merge Foundation Gate #391: SUCCESS.
- FMCC pós-merge: 48 test files / 185 tests; 6 E2E; secret scan 232 tracked files; runtime smoke/Docker/dependency audit HIGH PASS.
- npm: 4 advisories MODERATE transitivos; nenhum HIGH/CRITICAL bloqueante.
- HEAD documental recertificado: `8325913147bb2019b617249e66410ff14c0beba7`.
- Runtime Readiness #1135: SUCCESS.
- KCA Commercial Gate #289: SUCCESS.
- WP-031 Master Gate #298: SUCCESS.
- WP-031L Regression Channel Parity #308: SUCCESS.
- PR Superseded Runs Cleanup #835: SUCCESS.
- KCA-G13: PASS canônico.
- KCA-14: NÃO INICIADO.


## Certificação KCA-13

- Candidate funcional Kordena: `10cb4ac5da96947e0298616af9a3e56c37fccb23`.
- Candidate funcional FMCC: `5def840f7a42686ae11df16406fcc68d54bb9647`.
- FMCC base reconciliada após drift autorizado da PR #18: `main@221e8866c5d07f488dceb1861d44bf0771a75c0a`.
- PR Kordena #130: OPEN / DRAFT / não mergeada.
- PR FMCC #19: MERGED externamente em `0e37eecb69d00361216468891c7442b74b993b29`; `main` posteriormente avançou para `eb130c37bdd26c559c517fcfc3cf3731874ffc59` por commit operacional sem alteração do contrato KCA-13.
- Kordena KCA Commercial Gate #288: SUCCESS.
- KCA targeted: 212 passed, 1 warning.
- Full Python: 1813 passed, 5 skipped, 101 warnings.
- Schema baseline: 132 tabelas; SHA `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- Ruff/mypy/ESLint/TypeScript/Next build/diff: PASS.
- Web Node: 16 tests, 0 skipped.
- Commercial Runtime Readiness V1 #1134: SUCCESS.
- WP-031 Master Gate #297: SUCCESS.
- WP-031L Regression Channel Parity #307: SUCCESS.
- FMCC Foundation Gate #390: SUCCESS.
- FMCC Cognitive Governed Intelligence Gate #72: SUCCESS.
- Observabilidade read-only, provenance, correlation IDs, health e alertas: PASS.
- INTERNAL_TEST excluído e public signup -> TRIAL protegido por fitness test.
- Isolamento cross-product Kordena/IRON comprovado por teste.
- AI FinOps existente reutilizado; nenhum segundo FinOps criado.
- Infra cost sem fonte governada: permanece unavailable, nunca zero inventado.
- Nenhuma migration nova no KCA-13.
- Nenhum merge Kordena, provider real, cliente real ou abertura pública executado. O merge FMCC #19 ocorreu externamente durante a execução e está reconciliado como fato do CURRENT.
- KCA-G13: PASS.
- KCA-14: NÃO INICIADO.


### Recertificação documental pós-drift

- HEAD documental anterior: `0a9e82e0bae6a4a09db705a3483250831b0b82a0`.
- Runtime Readiness #1137: SUCCESS.
- KCA Commercial Gate #291: SUCCESS.
- WP-031 Master #300: SUCCESS.
- WP-031L Parity #310: SUCCESS.
- Cleanup #837: SUCCESS.
- Drift factual reconciliado: FMCC PR #19 foi mergeada externamente; nenhuma tentativa de rollback automático foi realizada.


## Fechamento integrado KCA-13

- PR #130: MERGED.
- HEAD pré-merge recertificado: `72cb89feadc2930bf08a22d57edd31afc9bb7c54`.
- Evidência pré-merge: Runtime Readiness #1140 / KCA Commercial #294 / WP-031 Master #303 / WP-031L Parity #313 / Cleanup #840 / Vercel — SUCCESS.
- KCA targeted: 212 passed, 1 warning.
- Full Python: 1813 passed, 5 skipped, 101 warnings.
- Merge commit / staging: `05c65c16ef380158b4602780511a9997e08cb5bb`.
- Pós-merge: Vercel SUCCESS + Railway SUCCESS.
- KCA-G13: PASS, INTEGRADO E ENCERRADO.
- KCA-14 somente pode iniciar a partir deste CURRENT certificado.


## Certificação KCA-14 — Security Hardening + Tenant Isolation Audit

- Base canônica: `staging/kordena-premium@c8374e187bbcf782274e2c4e07f76283a1ad34cd`.
- PR: #133.
- Candidate funcional/security: `c9435f5af7f205457787a592d4a2e885f0f3ec0d`.
- Auth/RBAC targeted adversarial matrix: **104 passed, 1 warning**.
- Full Python regression: **1819 passed, 5 skipped, 101 warnings**.
- KCA targeted matrix: **254 passed, 1 warning**.
- Web Node: **16 passed, 0 skipped**.
- Migration manifest: PASS.
- Schema baseline: PASS — 132 tabelas, SHA `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- Ruff: PASS.
- mypy: PASS.
- ESLint/TypeScript/Next production build/diff: PASS.
- Auth/RBAC Commercial Gate V1 #29: SUCCESS.
- Kordena KCA Commercial Gate #299: SUCCESS.
- WP-031 Master Gate #307: SUCCESS.
- WP-031L Regression Channel Parity #317: SUCCESS.
- PR Superseded Runs Cleanup #845: SUCCESS.
- Vercel: SUCCESS.
- Hardening incorporado ao gate canônico de staging.
- Replay de sessão antiga após troca de unidade: negado por teste.
- Basic Auth legado com tenant/unidade forjados: negado por teste.
- Header spoofing contra sessão assinada: permanece fail-closed/ignorado em favor da sessão.
- Step-up administrativo e revogação por troca de unidade: PASS.
- Cross-tenant/cross-unit IDOR deny-by-default: PASS.
- Webhook assinatura forjada, duplicate/replay/out-of-order: PASS.
- FMCC service-token + step-up boundary: PASS.
- Commercial entitlement/provisioning/subscription isolation matrix: incluída no KCA gate.
- **CRITICAL OPEN = 0**.
- **HIGH OPEN = 0**.
- Primeira tentativa do Auth/RBAC gate falhou apenas porque um fitness contract exigia nomes individuais de testes que já eram cobertos por `tests/integration/comercial`; o contrato foi corrigido sem reduzir cobertura e a matriz adversarial subsequente passou.
- KCA-G14: PASS no candidate funcional; este commit documental ainda deve ser recertificado antes do merge.


## Certificação KCA-15 — Homologação Interna Nova FM

- Base canônica: `staging/kordena-premium@16975a52202ec6602499bb4981d85461977d9952`.
- PR: #134.
- Candidate técnico: `ed79e7ca7f5f5b156e247f37d1c8143e6cc8fd37`.
- PostgreSQL 16 efêmero em runtime staging: PASS.
- `FM_AI_TEST_MODE`: ausente durante homologação.
- INTERNAL_TEST persistido: PASS.
- Entitlement INTERNAL_TEST/FULL: PASS.
- Login/logout, tenant/unit, admin step-up, PDV, Salão, KDS, Gerente IA: PASS.
- FMCC snapshot/control plane: PASS.
- Administração de plano/promoção: PASS.
- INTERNAL_TEST excluído dos KPIs: PASS.
- Billing real: não utilizado.
- Cliente externo real: não utilizado.
- KCA-15 targeted: 49 passed, 1 warning.
- Full Python: 1819 passed, 5 skipped, 101 warnings.
- Master Gate: 114 + 182 + 108 targeted passes; full Python 1819 passed, 5 skipped, 101 warnings.
- Web Node: 16 passed, 0 skipped.
- Migration manifest/schema baseline/Next build: PASS.
- KCA15 Homologation #7 / Master #315 / Cleanup #853 / Vercel: SUCCESS.
- KCA-G15: PASS no candidate técnico; novo HEAD documental deve ser recertificado antes do merge.
