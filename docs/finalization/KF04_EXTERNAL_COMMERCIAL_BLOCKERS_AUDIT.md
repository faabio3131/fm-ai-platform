# Kordena Finalization — KF-04 External Commercial Blockers Audit

## Authority

Canonical schedule:
`docs/finalization/KORDENA_CRONOGRAMA_MESTRE_FINALIZACAO_V1_COMERCIAL_v2.0.md`

Execution date: 2026-09-30

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

KF-04 is **BLOCKED_EXTERNAL**.

This is not a code-regression result. The internal platform contains substantial commercial infrastructure, but the production provider/account/legal/support evidence required by the Master Schedule is not currently present in the live Kordena runtime.

No missing item is converted into PASS.

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

## What exists

The signup backend requires:

`terms_accepted = true`

and accepts a consent map.

The frontend currently displays a required checkbox:

`Li e aceito os termos aplicáveis ao cadastro.`

## Finding

No customer-facing legal route was found under the current Next.js app for:

- Terms of Use;
- Privacy Policy;
- LGPD/privacy notice;
- support/contact policy associated with those documents.

No versioned legal-document identifier is bound to the signup acceptance in the current contract.

Therefore a boolean acceptance exists, but the exact document accepted by a future customer is not yet evidenced/versioned.

## Status

```text
LEGAL_TERMS_READY = BLOCKED_EXTERNAL
```

Required evidence:
- approved Terms of Use;
- approved Privacy Policy/LGPD notice;
- legal-controller/contact identity;
- document versions/effective dates;
- frontend routes/links;
- signup persistence of accepted legal version(s);
- legal review/approval appropriate for launch jurisdiction.

No legal content is invented by this audit.

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
- support channel;
- legal document versions.

Values remain redacted by the connected Railway permission model.

---

# 8. Security / governance result

```text
REAL_CHARGE_EXECUTED = NO
FAKE_BILLING_PASS = NO
FAKE_EMAIL_PASS = NO
FAKE_LEGAL_PASS = NO
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
LEGAL_TERMS_READY = BLOCKED_EXTERNAL
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
5. Approve Terms of Use + Privacy/LGPD content and legal identity/contact.
6. Define official support channel and launch support runbook.
7. Execute a fresh governed external-customer baseline check.

Until then, public signup and public release must remain disabled.

## Gate conclusion

```text
KF04_AUDIT_COMPLETE = PASS
KF_G04 = BLOCKED_EXTERNAL
PUBLIC_RELEASE_ALLOWED = NO
```
