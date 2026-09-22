# KCA-06 — Implementation Record

## Status

**EM CERTIFICAÇÃO — KCA-G6 AINDA NÃO APROVADO**

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

## Evidência em validação

A regressão do primeiro HEAD KCA-06 revelou quatro testes legados que congelavam o manifesto até `0053_commercial_provisioning_v1`. A migration `0054_commercial_signup_v1` já estava corretamente registrada no runner. Os testes foram atualizados para reconhecer a nova migration canônica.

Commits corretivos:
- `885a25f0fd81747fa7d5add0a29fc964818bb1ba`
- `d4a6814f487875404aa81918d83debf823c956e2`

## Gate

**KCA-G6 = PENDENTE**

Somente promover para PASS após Migration manifest, schema baseline, targeted KCA, full Python, frontend lint/typecheck/tests/build, regressão e CI aplicáveis ficarem verdes.
