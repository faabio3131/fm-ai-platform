# KCA-04 — Implementation Record

## Status

**PASS — KCA-G4 CERTIFIED**

## Candidate

- Functional/final candidate: `6b43c8454c13e6ac64d31907286c5e4af2979983`
- PR: #125
- Branch: `feat/kordena-commercial-platform-kca`
- Governance: PR OPEN/DRAFT; no merge; no public deploy.

## Scope delivered

- Commercial Entitlement Authority.
- Canonical commercial states and access modes: `FULL`, `LIMITED`, `BILLING_ONLY`, `BLOCKED`.
- Capability resolution from the effective versioned plan.
- Capability limits/config preservation.
- Monotonic entitlement revisions.
- Versioned entitlement snapshots.
- Canonical `entitlement.changed` outbox event.
- Local Kordena entitlement projection.
- Durable local inbox for event deduplication.
- Old/out-of-order revisions cannot regress the local projection.
- Missing entitlement is fail-closed.
- Stale policy with last-known-good grace and fail-closed maximum staleness.
- Product-account/tenant binding validation prevents cross-tenant recalculation.
- Idempotent recalculation.
- Audit/correlation/causation preserved.

## Migration

- `0052_commercial_entitlement_v1`
- Tables added:
  - `fm_commercial_entitlement_snapshots_v1`
  - `fm_kordena_entitlement_projection_v1`
  - `fm_kordena_entitlement_inbox_v1`

## Certification evidence

GitHub Actions run `35737636630` on candidate `6b43c8454c13e6ac64d31907286c5e4af2979983`:

- Migration manifest: PASS.
- Schema baseline: PASS — 119 tables.
- Schema SHA-256: `0e3b2e74403557045ad75aacac6bc5b09cf79d704a529ed0967702784d17f145`.
- Ruff: PASS.
- mypy: PASS.
- KCA targeted suite: **90 passed**.
- Full Python regression: **1691 passed, 5 skipped, 102 warnings**.
- Web ESLint: PASS.
- Web TypeScript: PASS.
- Web Node tests: PASS, 0 skipped.
- Next production build: PASS.
- Diff whitespace: PASS.
- All 16 pull-request workflow runs observed for the candidate concluded SUCCESS.
- Vercel commit status: SUCCESS.

## Security / failure behavior

- Missing local projection => `BLOCKED`.
- Stale snapshot beyond configured grace => fail-closed.
- `stale_fail_mode=FULL` is rejected.
- Disabled/missing capability is denied.
- Cross-tenant product-account mismatch is denied.
- Duplicate event is idempotent.
- Older revision is persisted only to inbox evidence and does not regress projection.

## Rollback / mitigation

- Migration is additive.
- Kordena request-side behavior can continue using the last-known-good projection within configured stale policy.
- New snapshots are append-only; historical evidence is preserved.
- Projection accepts only newer revisions, permitting forward repair with a newer snapshot/event.

## Gate

**KCA-G4 = PASS**

KCA-05 may start only after this certification commit is green in CI.
