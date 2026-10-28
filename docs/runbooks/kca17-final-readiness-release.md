# KCA-17 — Final Readiness / Controlled Release Runbook

## Purpose

This runbook closes the technical readiness envelope for Kordena V1 without fabricating external approvals. It does not itself activate public signup, choose a billing provider, approve legal terms, or authorize production/public rollout.

## Canonical release rule

Public signup/trial stays disabled by default until:
- KCA-G0 through KCA-G16 are green;
- KCA-17 technical readiness is green;
- every required external prerequisite in `KCA17_EXTERNAL_PREREQUISITES.json` has concrete evidence;
- public release is explicitly authorized under the current release policy.

## Technical readiness drill

The KCA-17 workflow must prove on an ephemeral PostgreSQL staging runtime:
1. migrations and schema baseline;
2. isolated tenant/unit sentinel creation;
3. PostgreSQL `pg_dump` backup;
4. backup SHA-256 verification;
5. restore into a distinct safe database;
6. restored schema and sentinel tenant/unit integrity;
7. health endpoint;
8. public signup disabled by default;
9. commercial observability snapshot;
10. rollback controls remain available;
11. KCA-16 commercial E2E regression;
12. security, dependency and secret gates;
13. full Python/Web regression.

## Backup / restore

Never restore a drill over production. The workflow uses disposable source and restore databases.

Evidence must contain:
- backup manifest/checksum;
- source database name;
- restore database name;
- source/restore table counts;
- sentinel tenant/unit mapping before/after;
- measured backup/restore durations.

Measured durations are evidence only; they are not new approved RPO/RTO targets.

## Rollback

Safe rollback order:
1. stop rollout / keep public signup disabled;
2. disable the commercial/public release switch;
3. revert application release to the previously certified SHA when required;
4. preserve new commercial records; never hard-delete to simulate rollback;
5. reconcile outbox/inbox/webhooks before resuming;
6. migration rollback is handled separately from code rollback.

## Observability and incident response

Use:
- `/healthz`;
- KCA-13 commercial health/alerts/correlation IDs;
- Vercel/Railway deployment status;
- webhook inbox/reconciliation/DLQ evidence;
- existing Gate E and canary rollback runbooks.

A Critical/High security finding, database restore divergence, failed health check, failed required CI, or tenant-integrity divergence is NO-GO.

## External prerequisites

The following are release authorities, not facts the code may invent:
- approved production SaaS billing provider/account/credentials;
- approved transactional email provider/runtime;
- applicable terms/privacy policy approval and publication;
- customer support readiness;
- final domain DNS/TLS/application binding;
- public rollout authorization.

If any is missing, technical readiness may pass, but KCA-G17 remains `BLOCKED_EXTERNALLY`.

## Visual Premium

Visual Premium is deliberately outside this execution. It must not be used to hide any non-visual functional/readiness blocker.
