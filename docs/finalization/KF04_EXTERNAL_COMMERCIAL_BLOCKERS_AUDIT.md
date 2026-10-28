# Kordena Finalization — KF-04 External Commercial Blockers Audit

## Authority

Canonical schedule:
`docs/finalization/KORDENA_CRONOGRAMA_MESTRE_FINALIZACAO_V1_COMERCIAL_v2.0.md`

Execution date: 2026-09-30
Reconciliation date: 2026-10-02

## PROJECT

Kordena

## REPOSITORY

`faabio3131/fm-ai-platform`

## BASE

`staging/kordena-premium@0d754d0645195acbb70f89a60e2a222ad1025cd8`

## OBJECTIVE

Audit the mandatory external commercial blockers required by KF-04:

```text
BILLING_PRODUCTION_READY
TRANSACTIONAL_EMAIL_READY
LEGAL_TERMS_READY
SUPPORT_READY
LIVE_CUSTOMER_BASELINE_KNOWN
```

No real financial charge is authorized by this block.

## RESULT

KF-04 remains **BLOCKED_EXTERNAL**, but the legal blocker identified in the original audit is now closed.

This is not a code-regression result. Billing production, transactional e-mail, support readiness and a fresh external-customer baseline still require external/operational evidence.

The legal package was implemented and certified after this audit by PR #177 and is reconciled below as PASS. No other missing item is converted into PASS.

---

# 1. Billing SaaS production

## What exists

Kordena has provider-neutral SaaS billing architecture:

- `BillingProvider` domain contract;
- `BillingProviderAdapterRegistryV1`;
- provider accounts;
- encrypted credential references;
- connection tests;
- routing policies;
- checkout/subscription/cancel/change/fetch transaction contracts;
- signed webhook verification boundary;
- reconciliation/event infrastructure.

ADR-KCA-008 explicitly keeps Nova FM SaaS billing separate from establishment operational payments.

## Runtime finding

The current canonical frontend runtime composes:

`BillingProviderAdapterRegistryV1()`

with no production SaaS billing adapter registered by default.

Existing Mercado Pago/PagBank operational integrations do not constitute evidence that Nova FM SaaS subscription billing is production-ready.

Railway currently exposes no service variable names indicating a configured SaaS billing provider/account integration.

No evidence was found for:
- an active production SaaS billing provider adapter;
- a validated production provider account;
- recurring subscription capability tested against the chosen provider;
- production webhook endpoint/provider registration;
- a real or provider-authorized zero-value production verification.

## Financial safety

No real charge was created.

No payment instrument was used.

No production billing transaction was fabricated.

## Status

```text
BILLING_PRODUCTION_READY = BLOCKED_EXTERNAL
```

Required external evidence:
- final provider selection;
- production merchant/account onboarding;
- credentials stored only in the governed secret store;
- provider adapter registered in the SaaS billing runtime;
- production connection test;
- webhook registration/signature test;
- recurring subscription capability proof;
- explicit authorization before any test involving real money.

---

# 2. Transactional e-mail

## What exists

Kordena has a provider-neutral SMTP verification dispatcher with:

- STARTTLS or SSL;
- optional SMTP authentication;
- password resolved by secret reference;
- one-time signup verification URL;
- sanitized message content;
- no password persistence in message body.

Public signup composes this dispatcher only when public signup is enabled.

## Runtime finding

The Railway service currently has no configuration names for:

- `FM_AI_TRANSACTIONAL_EMAIL_SMTP_HOST`
- `FM_AI_TRANSACTIONAL_EMAIL_SMTP_PORT`
- `FM_AI_TRANSACTIONAL_EMAIL_FROM`
- `FM_AI_TRANSACTIONAL_EMAIL_USERNAME`
- `FM_AI_TRANSACTIONAL_EMAIL_PASSWORD_SECRET_REF`
- `FM_AI_TRANSACTIONAL_EMAIL_PASSWORD`
- `FM_AI_PUBLIC_WEB_BASE_URL`

The runtime also has no `FM_AI_PUBLIC_SIGNUP_ENABLED` variable configured.

The code defaults public signup to disabled.

Therefore there is no evidence of a live transactional SMTP provider or a real delivery test in the current Railway runtime.

## Status

```text
TRANSACTIONAL_EMAIL_READY = BLOCKED_EXTERNAL
```

Required external evidence:
- SMTP/provider account;
- sender/domain authorization;
- secret configured in Railway/vault;
- final public web base URL;
- successful provider connection;
- controlled real delivery to an approved mailbox;
- delivery evidence without exposing token/secret.

---

# 3. Terms / Privacy / LGPD

## Reconciliation after PR #177

The blocker recorded by the original 2026-09-30 audit was resolved by the versioned legal package and acceptance-trail implementation.

Canonical legal sources:

- Terms 1.0: `docs/legal/01_TERMOS_DE_USO_KORDENA_V1.md`;
- Privacy 1.0: `docs/legal/02_POLITICA_PRIVACIDADE_LGPD_KORDENA_V1.md`;
- DPA 1.0: `docs/legal/03_DPA_TRATAMENTO_DADOS_KORDENA_V1.md`.

Certified behavior:

- stable public routes `/legal/termos`, `/legal/privacidade` and `/legal/dpa`;
- public legal API exposes the ACTIVE version metadata;
- signup displays and submits the exact active legal versions and SHA-256 hashes;
- backend recalculates the legal authority and fails closed on missing, nonexistent, expired or mismatched versions/hashes;
- append-only commercial audit events record document type, version, hash, signup/correlation identifiers and server timestamp;
- marketing consent remains optional and separate from mandatory legal acceptance.

Certification evidence:

- PR #177 HEAD: `58fefed17a3025d72b8355113f6325442c00b8ee`;
- pre-merge matrix: 15/15 applicable workflows `SUCCESS`, 0 failures;
- merge SHA: `eac2292cd6699e00552af2a867daaab0f66911e1`;
- post-merge Vercel: `SUCCESS`;
- post-merge Railway deployment `acc5cbb9-b61f-4966-8c22-d6135a659af7`: `SUCCESS`.

This is a technical/project-governance certification of the approved launch documents and acceptance mechanism. It does not claim an external legal opinion.

## Status

```text
LEGAL_TERMS_READY = PASS
LEGAL_VERSIONING_PASS = PASS
LEGAL_ACCEPTANCE_TRAIL_PASS = PASS
PRIVACY_DISCLOSURE_PASS = PASS
OPTIONAL_CONSENT_SEPARATION_PASS = PASS
```

---

# 4. Operational support

## Finding

No customer-facing support route/configuration or launch support contact was found in the current Kordena web app.

Railway currently exposes no support/help/ticket configuration names.

`application/kds_runtime_support.py` is an internal runtime helper and is not evidence of commercial customer support.

No launch evidence currently identifies:
- support channel;
- operating hours;
- incident escalation;
- response targets;
- customer-facing contact;
- ownership for billing/account/security incidents.

## Status

```text
SUPPORT_READY = BLOCKED_EXTERNAL
```

Required evidence:
- official support channel;
- responsible operator/queue;
- incident escalation procedure;
- billing/security/account recovery path;
- customer-facing support contact;
- support runbook linked to launch operations.

---

# 5. Live external customer baseline

FM Command KF-03 registered exactly one governed Kordena commercial source.

The first real sync completed successfully and persisted:

```text
source_count = 1
sync_count = 1
completed_count = 1
fact_count = 0
```

Kordena canonical FMCC facts intentionally exclude `account_class=internal_test`.

Therefore the completed sync did not produce a non-internal canonical commercial fact.

This is evidence that no external commercial fact was ingested at that sync point; it is **not** sufficient to claim a continuously current external-customer baseline after that timestamp.

The bootstrap idempotency guard correctly prevents replaying the same initial sync key merely to manufacture a second execution.

## Status

```text
LIVE_CUSTOMER_BASELINE_KNOWN = PARTIAL_EVIDENCE / BLOCKED_EXTERNAL
```

Required evidence before PASS:
- fresh governed customer/trial/subscription baseline;
- explicit classification of internal_test vs external;
- count and identifiers kept privacy-safe;
- no manual SQL correction;
- provenance timestamp/correlation.

---

# 6. Secret/config hygiene finding corrected during KF-04

Railway contained one environment variable whose **key itself had secret-like material** rather than a legitimate configuration name.

Actions:
- the suspicious variable value was neutralized;
- the Railway infrastructure agent removed that exact variable key;
- follow-up variable inventory confirmed the suspicious key is absent;
- no other runtime variable was intentionally changed;
- Railway redeployed successfully;
- Kordena application status returned `SUCCESS`;
- PostgreSQL remained `SUCCESS`;
- `GET /healthz` returned `200`.

Final cleanup deployment:

`fda35d63-32b6-40fd-81ae-cae5ddc58f84`

The secret-like key is intentionally not reproduced in this document.

---

# 7. Current runtime configuration evidence

Railway Kordena service currently contains the expected core runtime names, including:

- `DATABASE_URL`
- `FM_AI_ENV`
- `FM_AI_FMCC_CONTROL_PLANE_TOKEN`
- `FM_AI_SECRET_MASTER_KEY`
- `FM_AI_SESSION_SECRET`
- `FM_AI_TENANT_ID`
- `FM_AI_UNIDADE_ID`

It does not currently contain names evidencing production setup for:
- SaaS billing provider;
- transactional SMTP;
- public signup;
- public web URL for verification;
- support channel.

Legal document authority/versioning is repository-backed and was certified by PR #177; it does not depend on a Railway environment-variable name.

Values remain redacted by the connected Railway permission model.

---

# 8. Security / governance result

```text
REAL_CHARGE_EXECUTED = NO
FAKE_BILLING_PASS = NO
FAKE_EMAIL_PASS = NO
FAKE_LEGAL_PASS = NO
LEGAL_EVIDENCE_CERTIFIED = PASS
FAKE_SUPPORT_PASS = NO
SECRET_LIKE_ENV_KEY_REMOVED = PASS
RAILWAY_APP_HEALTH_AFTER_CLEANUP = PASS
POSTGRES_HEALTH = PASS
PUBLIC_SIGNUP = OFF / NOT CONFIGURED
```

---

# 9. KF-G04

```text
BILLING_PRODUCTION_READY = BLOCKED_EXTERNAL
TRANSACTIONAL_EMAIL_READY = BLOCKED_EXTERNAL
LEGAL_TERMS_READY = PASS
LEGAL_VERSIONING_PASS = PASS
LEGAL_ACCEPTANCE_TRAIL_PASS = PASS
PRIVACY_DISCLOSURE_PASS = PASS
OPTIONAL_CONSENT_SEPARATION_PASS = PASS
SUPPORT_READY = BLOCKED_EXTERNAL
LIVE_CUSTOMER_BASELINE_KNOWN = BLOCKED_EXTERNAL

KF-G04 = BLOCKED_EXTERNAL
```

This gate must not be promoted to PASS until the missing external evidence exists.

---

# 10. Inputs/actions required to unblock KF-04

1. Choose and provision the Nova FM SaaS billing provider in production.
2. Provide/configure its production credentials and webhook registration.
3. Authorize any real-money verification separately.
4. Provision transactional e-mail/SMTP and authorize sender/domain.
5. Legal package/versioned acceptance: CLOSED by PR #171 + PR #177 certification.
6. Define official support channel and launch support runbook.
7. Execute a fresh governed external-customer baseline check.

Until then, public signup and public release must remain disabled.

## Gate conclusion

```text
KF04_AUDIT_COMPLETE = PASS
KF_G04 = BLOCKED_EXTERNAL
PUBLIC_RELEASE_ALLOWED = NO
```
