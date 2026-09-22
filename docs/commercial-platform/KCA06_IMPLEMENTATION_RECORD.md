# KCA-06 — Implementation Record

## Status

**PASS — KCA-G6 CERTIFIED**

## Scope implementado

- Public Signup + Verification.
- Backend público desabilitado por padrão; liberação comercial permanece fora de escopo.
- Signup intent persistido em migration `0054_commercial_signup_v1`.
- E-mail normalizado, termos obrigatórios e validação de payload.
- Verification token aleatório; apenas SHA-256 persistido; token possui expiração e consumo único.
- Reenvio rotaciona token e possui cooldown/limite.
- Anti-enumeration para signup duplicado.
- Rate limiting por origem e honeypot básico.
- Password transitório cifrado por secret reference e removido após READY.
- Provisioning delegado ao KCA-05 Provisioning Orchestrator.
- Tenant/plan/entitlement não são aceitos pelo contrato público.
- Estados: EMAIL_PENDING, EMAIL_VERIFIED, PROVISIONING_REQUESTED, READY, FAILED_RETRYABLE.
- Audit/correlation preservados.
- Frontend de signup existe, mas feature flag pública permanece desligada por padrão.

## Certification evidence

Candidate certificado: `1569253f69db951bdb1c5ac36a7c9908d40483b4`

GitHub Actions:
- Kordena KCA Commercial Gate: run `35750059891` — SUCCESS.
- 17/17 workflows associados ao candidate concluíram SUCCESS.
- Migration manifest: PASS.
- Schema baseline: PASS — 122 tabelas.
- Schema SHA-256: `0c25e3fe75497b92f0c2e9667d864c90daba44fcc3da56ba1fec224abb2bc113`.
- Ruff/mypy: PASS.
- KCA targeted suite: **115 passed, 2 warnings**.
- Full Python regression: **1716 passed, 5 skipped, 102 warnings**.
- Web ESLint: PASS.
- Web TypeScript: PASS.
- Web Node: **14 tests, 0 skipped**.
- Next production build: PASS.
- Diff whitespace: PASS.
- WP-031 Master Gate: SUCCESS.
- Commercial Runtime Readiness: SUCCESS.
- Schema Baseline Probe: SUCCESS.
- Web Parity, Pre-E Audit & Fix, WP-031 B/E/F/G/H/I/J/L, Assistente e Visual Premium gates: SUCCESS.

## Correção realizada durante a certificação

A regressão do primeiro HEAD KCA-06 revelou quatro testes legados que congelavam o manifesto até `0053_commercial_provisioning_v1`. A migration `0054_commercial_signup_v1` já estava corretamente registrada no runner. Os testes foram atualizados para reconhecer a nova migration canônica.

Commits corretivos:
- `885a25f0fd81747fa7d5add0a29fc964818bb1ba`
- `d4a6814f487875404aa81918d83debf823c956e2`

## Gate

**KCA-G6 = PASS**

Não iniciar KCA-07 automaticamente. PR #125 deve permanecer OPEN/DRAFT, sem merge e sem deploy público.
