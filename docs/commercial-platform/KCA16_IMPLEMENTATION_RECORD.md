# KCA-16 — Full Commercial E2E + Audit & Fix — Implementation & Certification Record

## Base e escopo

- Base canônica: `staging/kordena-premium@37be46177dd2e2d67425e4937b024ed077fadb56`.
- Branch: `feat/kordena-kca16-full-commercial-e2e-audit-fix`.
- PR: #135.
- Visual Premium: fora do escopo.
- Objetivo: certificar a jornada comercial V1 integral, auditar a linha canônica e corrigir qualquer gap funcional necessário ao fluxo de cliente novo até recuperação pós-pagamento.

## Delta funcional encontrado e corrigido

A jornada E2E revelou que um tenant/unidade recém-provisionado precisava de ponte explícita e isolada para a estrutura legada de loja usada pelos módulos operacionais V1.

Foi implementado:
- `garantir_loja_legada_para_escopo()` em `infra/legacy_product_scope.py`;
- criação idempotente de loja legada dedicada por tenant/unidade;
- proteção contra reutilização inferida de loja existente;
- savepoint + recuperação segura em corrida concorrente;
- integração dessa ponte no provisioning canônico;
- testes de provisioning e isolamento correspondentes.

Essa correção fecha um gap real entre provisioning comercial novo e os módulos operacionais legados, sem criar uma segunda autoridade de tenant/unidade.

## Jornada certificada

Runtime: PostgreSQL 16 efêmero, `FM_AI_ENV=staging`, `FM_AI_TEST_MODE` ausente.

PASS:
1. signup;
2. email verification;
3. customer/product account;
4. tenant/company/unit/membership;
5. trial active;
6. entitlement initial;
7. login;
8. onboarding scope;
9. Kordena operations;
10. trial expiration;
11. paywall/BILLING_ONLY;
12. plan selection;
13. sandbox checkout;
14. payment webhook;
15. reconciliation;
16. subscription ACTIVE;
17. entitlement restored;
18. Kordena access restored;
19. FMCC updated;
20. observability updated;
21. admin step-up;
22. logout.

Billing real utilizado: NÃO.

## Auditoria e regressão

- KCA-16 commercial/security/integration matrix: 241 passed, 1 warning.
- KCA Commercial Gate targeted: 254 passed, 1 warning.
- Migration manifest: PASS.
- Schema baseline: PASS — 132 tabelas, SHA `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- High-confidence tracked secret scan: PASS — 1538 arquivos.
- Python `pip-audit`: nenhuma vulnerabilidade conhecida.
- Playwright E2E + accessibility + responsiveness + performance baseline: 6 passed.
- Web Node: 16 passed, 0 skipped.
- `npm audit --audit-level=high`: 0 vulnerabilidades.
- ESLint/TypeScript/Next production build: PASS.
- Full Python regression: 1819 passed, 5 skipped, 101 warnings.

## CI do candidate

Candidate: `d862342b795a10feede36895259b271e3a16a65f`.

- Commercial Runtime Readiness V1 #1147: SUCCESS.
- Kordena KCA16 Full Commercial E2E #9: SUCCESS.
- Kordena KCA15 Internal Homologation #15: SUCCESS.
- Kordena KCA Commercial Gate #306: SUCCESS.
- WP-031 Master Gate #325: SUCCESS.
- WP-031L Regression Channel Parity #325: SUCCESS.
- PR Superseded Runs Cleanup #863: SUCCESS.
- Vercel: SUCCESS.

## Gate

KCA-G16 = PASS no candidate funcional `d862342b795a10feede36895259b271e3a16a65f`.

O commit documental deste registro deve ser recertificado antes do merge. Após o merge, o staging deve ser certificado pós-merge antes do KCA-17.
