# Kordena Finalization — KF-03 Kordena ↔ FM Command Runtime Live

## Authority

Canonical schedule:
`docs/finalization/KORDENA_CRONOGRAMA_MESTRE_FINALIZACAO_V1_COMERCIAL_v2.0.md`

Execution date: 2026-09-30

## Final Kordena state

Repository:
`faabio3131/fm-ai-platform`

Branch:
`staging/kordena-premium`

KF-03 functional merge:
`PR #161 — fix(kordena): exclude internal tests from FMCC commercial summary`

Merged staging SHA:
`f7efa571ab4e90fe31caf7f9a764768a01916a64`

Railway:
- project: `diplomatic-expression`
- service: `fm-ai-platform`
- deployment: `fa7066ea-0f0b-4b7e-9e3f-700de7254681`
- deployment SHA: `f7efa571ab4e90fe31caf7f9a764768a01916a64`
- application status: `SUCCESS`
- PostgreSQL status: `SUCCESS`
- runtime healthcheck: `GET /healthz -> 200`

## Final FM Command state

Repository:
`faabio3131/FM-CONTROL-CENTER`

Runtime implementation:
`PR #26 — feat(kf03): bootstrap Kordena live runtime source`

Main/runtime commit:
`847ed0167086a041fa4446fde2d64e4b29c690f3`

Implementation CI:
- FMCC Foundation Gate `36767889787` — SUCCESS
- FMCC F21 Operational Readiness Gate `36767889789` — SUCCESS

Render:
- service: `fmcc-preview-web`
- service id: `srv-danhfirtqb8s73bug4ag`
- database: `fmcc-preview-postgres`
- public runtime: `https://fmcc-preview-web.onrender.com`
- final deploy with one-time bootstrap disabled: `dep-daung9s9v7es73a8c2eg`
- final deploy status: `live`

## Governed runtime path

Authorized path:

```text
FM Command
→ HTTPS server-to-server connector
→ Kordena /v1/control-plane/fmcc
→ Kordena canonical commercial authorities
```

Forbidden path remains absent:

```text
FM Command
→ direct SQL
→ Kordena PostgreSQL
```

FM Command stores only its own:
- source definition;
- sync execution;
- canonical facts/provenance.

No Kordena database credential or direct Kordena persistence adapter was added to FM Command.

## Runtime secrets

Configured only in runtime secret stores:

Kordena / Railway:
- `FM_AI_FMCC_CONTROL_PLANE_TOKEN`

FM Command / Render:
- `FMCC_KORDENA_CONTROL_TENANT_ID`
- `FMCC_KORDENA_ALLOWED_ORIGINS`
- `FMCC_KORDENA_CONTROL_PLANE_TOKEN`
- `FMCC_KORDENA_BASE_URL`

No secret value is versioned in Git or this certification.

## Registered Command source

Exactly one governed source exists:

- source id: `7409d6f8-db3a-432a-8623-bb904913f6fe`
- name: `Kordena Commercial`
- source type: `kordena-commercial-v1`
- authoritative domain: `commercial`
- sync mode: `pull`
- mapping version: `kordena-commercial-v1`
- secret reference: `env:FMCC_KORDENA_CONTROL_PLANE_TOKEN`
- freshness: `300s`

Persistent proof:

```text
source_count = 1
```

## Initial real sync

The first live KF-03 runtime bootstrap produced:

- source registration;
- real S2S health;
- real governed snapshot/sync;
- completed sync execution.

Execution:
`186aa774-0f0c-4ebb-85b2-b15f09b4760d`

Result:
```text
status = completed
attempt = 1
error = none
ingested = 0
```

Persistent state:
```text
sync_count = 1
completed_count = 1
fact_count = 0
```

## Why fact_count = 0 is correct

The current baseline contains internal homologation/test commercial data.

Kordena's canonical FMCC fact projection explicitly excludes:
`account_class=internal_test`

Therefore internal trial/subscription/payment/entitlement activity does not become FM Command commercial facts.

No synthetic customer, trial, subscription, payment, entitlement, MRR, ARR, churn or conversion fact was created to make KF-03 pass.

## Semantic defect found during live certification

During KF-03 review, a real inconsistency was found before certification:

- canonical facts excluded `internal_test`;
- KCA-13 observability excluded `internal_test`;
- the KCA-12 top-level `summary` still counted internal-test commercial state.

Because FM Command consumes that summary, internal homologation data could appear as a commercial customer/trial/subscription/payment/user/unit count.

This was not accepted as certified.

## Correction

PR #161 corrected the Kordena commercial summary to:

- exclude internal-test customers from commercial customer count;
- exclude their trials;
- exclude their subscriptions;
- exclude their payments/reconciliation;
- exclude their tenant memberships/users;
- exclude their units;
- preserve `internal_test_customers` only as a diagnostic count.

Regression coverage was added to prove that:
- real/external commercial data remains counted;
- internal-test data does not contaminate commercial summary.

## PR #161 certification matrix

Exact functional HEAD before merge:
`f7f0f1ca3953aafcb6733e54a511bf809f05a188`

All required transversal gates completed SUCCESS:

- Commercial Runtime Readiness V1 — SUCCESS
- Kordena KCA Commercial Gate — SUCCESS
- Kordena KCA15 Internal Homologation — SUCCESS
- Kordena KCA16 Full Commercial E2E — SUCCESS
- Kordena KCA17 Final Readiness — SUCCESS
- Kordena KF02 Gerente IA Release E2E — SUCCESS
- WP-031L Regression Channel Parity — SUCCESS
- WP-031 Master Gate — SUCCESS
- PR Superseded Runs Cleanup — SUCCESS
- Vercel Preview Comments — SUCCESS

The KCA targeted tests that directly cover the corrected summary also completed successfully before the full regression.

## Post-merge exact-runtime proof

After PR #161 merged:

1. `staging/kordena-premium` advanced to:
   `f7efa571ab4e90fe31caf7f9a764768a01916a64`

2. Railway automatically deployed that exact SHA.

3. Railway reported:
   - application `SUCCESS`;
   - PostgreSQL `SUCCESS`;
   - `GET /healthz` returned `200`.

4. FM Command one-time runtime verification was re-enabled only for post-merge S2S validation.

5. Command started successfully and emitted:
   `kordena_runtime_bootstrap_verified`

6. The result was:
```text
syncStatus = duplicate
ingested = 0
```

This is expected because the original idempotency key was already consumed. The verification still requires a successful S2S Kordena health before reaching the duplicate sync result.

7. No second source or second sync execution was persisted.

8. The one-time bootstrap flags were immediately returned to:
```text
FMCC_KORDENA_RUNTIME_BOOTSTRAP=false
FMCC_KORDENA_RUNTIME_BOOTSTRAP_VERIFY=false
```

9. FM Command was redeployed and finished `live` in:
   `dep-daung9s9v7es73a8c2eg`

## UI and Core consumption

FM Command's Kordena commercial UI:

`/dashboard/commercial/kordena`

uses:
- `SourceRegistryService`;
- tenant-scoped source resolution;
- `KordenaCommercialControlService`;
- the governed Kordena HTTPS snapshot contract.

The FM Command Core uses:
`KordenaCommercialSummaryCapability`

which:
- requires `commercial:read`;
- resolves the tenant/product-scoped Kordena source;
- validates freshness;
- returns unavailable on stale/unproven state;
- emits provenance references for source, mapping and schema.

No parallel data path was introduced for KF-03.

## Provenance

The governed contract preserves:
- source id;
- mapping version;
- Kordena schema version;
- source authority;
- freshness;
- quality status;
- snapshot `as_of`.

For KCA-13 metrics, unavailable evidence remains unavailable instead of being converted into an invented zero.

## Security result

```text
SERVER_TO_SERVER_TOKEN = PASS
HTTPS_ALLOWLIST = PASS
CONTROL_TENANT_SCOPE = PASS
SECRET_IN_RUNTIME_STORE = PASS
SECRET_IN_GIT = NO
DIRECT_KORDENA_DB_ACCESS = NO
BOOTSTRAP_FAIL_CLOSED = PASS
IDEMPOTENCY = PASS
INTERNAL_TEST_COMMERCIAL_ISOLATION = PASS
FABRICATED_COMMERCIAL_DATA = NO
NFCORE_CHANGE = NO
REAL_BILLING = NO
PUBLIC_RELEASE = NO
```

## Gate

```text
KORDENA_COMMAND_RUNTIME_CONNECTED = PASS
POST_MERGE_EXACT_SHA_DEPLOYED = PASS
COMMAND_S2S_HEALTH_AFTER_CORRECTION = PASS
SOURCE_REGISTRATION = PASS
SYNC = PASS
IDEMPOTENCY = PASS
PROVENANCE = PASS
NO_DIRECT_DB_ACCESS = PASS
INTERNAL_TEST_ISOLATION = PASS

KF-G03 = PASS
```

## Next block

`KF-04 — Bloqueadores Comerciais Externos Obrigatórios`

KF-04 must address the external/commercial launch blockers defined by the Master Schedule without reopening KF-03.
