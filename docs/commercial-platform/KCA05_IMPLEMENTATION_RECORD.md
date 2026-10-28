# KCA-05 — Implementation Record

## Status

**PASS — KCA-G5 CERTIFIED**

## Candidate

- Functional/final candidate: `3f0ee70c1e8483b2b6aad1a6c5737959ee555c98`
- PR: #125
- Branch: `feat/kordena-commercial-platform-kca`
- Governance: PR OPEN/DRAFT; no merge; no public deploy.

## Scope delivered

- Persisted Tenant Provisioning Saga.
- State machine: `REQUESTED → VALIDATING → PROVISIONING → READY`, with `FAILED_RETRYABLE`, `COMPENSATING` and `COMPENSATED`.
- Mandatory idempotency key and request hash conflict detection.
- Optimistic concurrency on Saga updates.
- Canonical provisioning sequence across:
  - commercial customer;
  - product account;
  - global identity;
  - Kordena membership;
  - tenant/company/initial unit;
  - owner/admin;
  - KCA-07 trial placeholder binding only;
  - fail-closed pending entitlement projection.
- Durable provisioning inbox.
- Transactional commercial outbox events for provisioning lifecycle.
- Correlation/audit trail.
- Retry and restart/resume behavior.
- Explicit compensation without destructive deletion of operational resources.
- Duplicate tenant protection.
- Password is not persisted in the Saga; only a one-way credential fingerprint participates in the idempotency request hash.
- KCA-07 Trial Engine was not anticipated; provisioning records `pending_kca07` only.

## Migration

- `0053_commercial_provisioning_v1`
- Tables added:
  - `fm_commercial_provisioning_sagas_v1`
  - `fm_commercial_provisioning_inbox_v1`

## Certification evidence

GitHub Actions run `35744687540` on candidate `3f0ee70c1e8483b2b6aad1a6c5737959ee555c98`:

- Migration manifest: PASS.
- Schema baseline: PASS — 121 tables.
- Schema SHA-256: `65b25edda83dd9f5af2c63adaf99c11fcd8cce36c2e85b474d73ddabbdf7cec4`.
- Ruff: PASS.
- mypy: PASS.
- KCA targeted suite: **105 passed**.
- Full Python regression: **1706 passed, 5 skipped, 102 warnings**.
- Web ESLint: PASS.
- Web TypeScript: PASS.
- Web Node tests: **11 passed, 0 failed, 0 skipped**.
- Next production build: PASS.
- Diff whitespace: PASS.
- All 16 pull-request workflow runs observed for the candidate concluded SUCCESS.
- Vercel commit status: SUCCESS.

## Security / failure behavior

- Duplicate idempotency key with different payload is rejected.
- Tenant IDs are generated server-side by the Saga.
- Product-account ↔ tenant binding mismatch is rejected.
- Optimistic version check prevents silent concurrent mutation.
- Failed provisioning becomes explicit `FAILED_RETRYABLE`.
- Compensation closes the product account instead of destructively erasing audit/history.
- Pending entitlement is fail-closed until KCA-07 activates a real trial.
- Provisioning event payloads contain identifiers/state only; no password is emitted.
- Password is not stored in the provisioning Saga.

## Rollback / mitigation

- Migration is additive.
- New provisioning can be stopped without changing existing tenants.
- Failed Sagas remain inspectable/retryable.
- Compensation is logical and auditable.
- Forward-fix is preferred for partially provisioned state.

## Gate

**KCA-G5 = PASS**

KCA-06 may start after this certification record is committed.