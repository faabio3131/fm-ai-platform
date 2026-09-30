# Kordena Finalization — KF-03 Kordena ↔ FM Command Runtime Live

## Authority

Canonical schedule:
`docs/finalization/KORDENA_CRONOGRAMA_MESTRE_FINALIZACAO_V1_COMERCIAL_v2.0.md`

Execution date: 2026-09-30

## PROJECT

Kordena

## KORDENA CURRENT

Repository:
`faabio3131/fm-ai-platform`

Base branch:
`staging/kordena-premium`

Certified KF-02 base:
`a9f14a0d4fa563ea0e9efb02dd01d23878a1f5a8`

Railway project:
`diplomatic-expression`

Railway service:
`fm-ai-platform`

Railway service domain:
`https://fm-ai-platform-production.up.railway.app`

Kordena deployment after KF-03 runtime configuration:
`326bda1a-0934-4445-b91f-efeb9ccf279b`

Kordena deployment status:
`SUCCESS`

PostgreSQL status:
`SUCCESS`

## FM COMMAND CURRENT

Repository:
`faabio3131/FM-CONTROL-CENTER`

Command implementation PR:
`#26 — feat(kf03): bootstrap Kordena live runtime source`

Command merge commit:
`847ed0167086a041fa4446fde2d64e4b29c690f3`

Command implementation candidate:
`e6ef276e02abf18f39200904ec2f43e996f6715d`

Implementation CI:
- FMCC Foundation Gate run `36767889787` — SUCCESS
- FMCC F21 Operational Readiness Gate run `36767889789` — SUCCESS

Runtime:
- Render workspace: `My Workspace`
- Render service: `fmcc-preview-web`
- Render service id: `srv-danhfirtqb8s73bug4ag`
- Render PostgreSQL: `fmcc-preview-postgres`
- Runtime URL: `https://fmcc-preview-web.onrender.com`
- Runtime commit: `847ed0167086a041fa4446fde2d64e4b29c690f3`
- final runtime deploy after one-time bootstrap disable: `dep-daun37o473hc73bscir0`
- final deploy status: `live`

## OBJECTIVE

Close the canonical KF-03 gate without rebuilding FM Command and without granting Command direct database access to Kordena.

Required path:

```text
FM COMMAND
→ governed server-to-server connector
→ Kordena /v1/control-plane/fmcc
→ canonical Kordena commercial authorities
```

Forbidden path:

```text
FM COMMAND
→ direct SQL
→ Kordena database
```

## RUNTIME CONFIGURATION

The following runtime settings were configured in the Render secret/environment store:

- `FMCC_KORDENA_CONTROL_TENANT_ID`
- `FMCC_KORDENA_ALLOWED_ORIGINS`
- `FMCC_KORDENA_CONTROL_PLANE_TOKEN`
- `FMCC_KORDENA_BASE_URL`

The corresponding Kordena server-to-server token was rotated/configured in Railway through:

- `FM_AI_FMCC_CONTROL_PLANE_TOKEN`

No token value is stored in Git, this document, logs, or frontend code.

One-time bootstrap flags were temporarily enabled for source registration and live verification:

- `FMCC_KORDENA_RUNTIME_BOOTSTRAP=true`
- `FMCC_KORDENA_RUNTIME_BOOTSTRAP_VERIFY=true`

After live verification and idempotency proof, both flags were returned to `false`. The connector configuration and server-side secret remain active.

## CONTROL TENANT

FM Command organization:

- name: `Nova FM Tecnologia`
- tenant id: `RBycgEmGWBNMBVu86y0wpY8OQ87UmG5R`

Canonical Command Kordena product:

- product id: `eb59fa86-c71d-4f4b-9b6b-7f209db0f50e`
- slug: `kordena`
- status: `active`

The bootstrap rejects ambiguous/mismatched control tenants or Kordena products fail-closed.

## REGISTERED SOURCE

Exactly one governed source was created:

- source id: `7409d6f8-db3a-432a-8623-bb904913f6fe`
- name: `Kordena Commercial`
- source type: `kordena-commercial-v1`
- authoritative domain: `commercial`
- sync mode: `pull`
- mapping version: `kordena-commercial-v1`
- secret reference: `env:FMCC_KORDENA_CONTROL_PLANE_TOKEN`
- status: `configured`
- freshness: `300s`
- base URL: Railway Kordena HTTPS origin

Post-bootstrap database proof:

```text
source_count = 1
```

## LIVE HEALTH + SNAPSHOT + SYNC

The first live bootstrap produced:

- `kordena_runtime_source_bootstrapped`
- source id `7409d6f8-db3a-432a-8623-bb904913f6fe`
- `connector_sync_started`
- `connector_sync_completed`
- `kordena_runtime_bootstrap_verified`

Initial sync execution:

- execution id: `186aa774-0f0c-4ebb-85b2-b15f09b4760d`
- status: `completed`
- attempt: `1`
- error: none
- ingested facts: `0`

The connector's sync path necessarily performed the governed Kordena snapshot request and validated the full `kordena.fmcc.commercial.v1` response contract before mapping canonical facts.

### Why ingested facts = 0 is correct

The current Kordena projection explicitly excludes `account_class=internal_test` customers and their dependent trial/subscription/billing/entitlement facts from FM Command canonical commercial facts.

Therefore a clean internal-only baseline can legitimately produce zero canonical facts.

No synthetic customer, trial, subscription, payment, entitlement, MRR, ARR, churn or conversion fact was created to make the test pass.

This preserves the rule:

```text
missing/unavailable != invented zero
```

## IDEMPOTENCY — REAL RUNTIME PROOF

A second Render deployment of the same Command commit was executed while the one-time bootstrap remained enabled.

Result:

```text
kordena_runtime_bootstrap_verified
syncStatus = duplicate
ingested = 0
```

Persistent database state after the second initialization:

```text
source_count = 1
sync_count = 1
completed_count = 1
```

The runtime did not create a duplicate source, duplicate sync execution, or duplicate fact.

The initial sync idempotency key remained:

`7409d6f8-db3a-432a-8623-bb904913f6fe:kf03-kordena-runtime-bootstrap-v1`

## PROVENANCE

The live connector preserves the canonical source/mapping/schema chain.

FM Command's Kordena Core capability emits evidence with:

- `source:<source_id>`
- `mapping:<mapping_version>`
- `schema:<snapshot.schema_version>`
- source authority `kordena_fm_commercial_platform`
- freshness status
- quality status
- snapshot `as_of`

For KCA-13 metrics, the Command UI displays the Kordena-provided `quality_status` and `source_authority`, and displays unavailable data as `Indisponível` rather than manufacturing a number.

No canonical fact row exists for the current internal-only baseline because the Kordena projection correctly excludes internal-test commercial facts. This is a provenance-preserving absence, not missing ingestion.

## COMMAND UI + CORE

The live source is consumed by the existing Command architecture, not by a parallel implementation.

### Commercial UI

`/dashboard/commercial/kordena`:

- resolves the tenant-scoped source through `SourceRegistryService`;
- selects only `kordena-commercial-v1`;
- retrieves live snapshot through `KordenaCommercialControlService`;
- renders `Indisponível` when source/metric evidence is absent;
- does not query Kordena PostgreSQL.

### Command Core

`KordenaCommercialSummaryCapability`:

- requires `commercial:read`;
- resolves the active tenant Kordena product;
- requires exactly one tenant/product-scoped Kordena source;
- reads the governed snapshot;
- validates freshness;
- emits source/mapping/schema provenance refs;
- returns unavailable on unproven/stale runtime state.

`buildCoreGateway()` composes this capability into the FM Command Vertical Cognitive Core.

## NO DIRECT KORDENA DATABASE ACCESS

The Command integration uses:

- HTTPS base URL allowlist;
- Bearer S2S token;
- Kordena control-plane endpoints;
- Command's own PostgreSQL only for source definitions, sync executions and canonical facts.

The Kordena boundary exposes:

- `GET /v1/control-plane/fmcc/health`
- `GET /v1/control-plane/fmcc/snapshot`
- governed catalog commands

The Kordena bearer token is validated server-side with constant-time comparison and a minimum configured length.

No Kordena `DATABASE_URL`, database credential, SQL connection string, or direct Kordena persistence adapter was added to FM Command.

## SECURITY

```text
SERVER_TO_SERVER_TOKEN = PASS
HTTPS_ALLOWLIST = PASS
CONTROL_TENANT_SCOPE = PASS
SECRET_IN_SERVER_STORE = PASS
SECRET_IN_GIT = NO
DIRECT_KORDENA_DB_ACCESS = NO
BOOTSTRAP_FAIL_CLOSED = PASS
IDEMPOTENCY = PASS
INTERNAL_TEST_EXCLUDED = PASS
FABRICATED_ZERO = NO
NFCORE_CHANGE = NO
REAL_BILLING = NO
PUBLIC_RELEASE = NO
```

## ROLLBACK / REVERSIBILITY

KF-03 does not require destructive Kordena data migration.

Runtime changes are reversible by:

1. disabling/removing the Command Kordena source;
2. removing the Command connector runtime variables;
3. rotating/removing the shared S2S token in both secret stores.

The Kordena commercial authorities remain authoritative throughout. Command is a control/read plane consumer.

## GATE

```text
KORDENA_COMMAND_RUNTIME_CONNECTED = PASS
HEALTH_PASS = PASS
SYNC_PASS = PASS
PROVENANCE_PASS = PASS
NO_DIRECT_DB_ACCESS = PASS

KF-G03 = PASS
```

## NEXT BLOCK

After this documentary exact-head certification is green, merged and post-merge validated:

`KF-04 — Bloqueadores Comerciais Externos Obrigatórios`

KF-04 covers production billing, transactional e-mail, legal terms/LGPD, operational support and the live-customer baseline.
