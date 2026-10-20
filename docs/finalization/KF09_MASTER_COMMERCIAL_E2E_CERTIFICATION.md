# KF-09 — Master Commercial E2E Final Certification

Data: 2026-09-30

## Candidate tested

- PR: #168
- exact-head tested: `bd53cce1bd71e49ae711e07079fd9d3953ad28b6`
- merged staging SHA: `d71c79b74d432d79226a7e2545b0328a231b8e95`
- public signup on release runtime: **OFF**
- real billing charge: **NOT USED**

## Controlled commercial journey

The current-head KCA-16 full commercial E2E ran outside `FM_AI_TEST_MODE` on real ephemeral PostgreSQL in staging mode with a controlled sandbox billing provider.

The journey proved, through canonical application/HTTP boundaries:

1. public signup in the isolated E2E runtime;
2. email verification through the captured verification dispatcher;
3. customer/product-account provisioning;
4. trial activation;
5. authenticated login and operational access;
6. admin step-up and onboarding access;
7. trial expiration;
8. fail-closed billing-only paywall;
9. commercial plan selection;
10. sandbox checkout;
11. authenticated billing webhook;
12. subscription transition to `ACTIVE`;
13. entitlement restoration;
14. operational access restoration;
15. billing transaction reconciliation;
16. FMCC snapshot updated;
17. commercial observability updated;
18. logout.

The evidence contract explicitly records `billing_real_used=false`.

## Exact-head gates

All mandatory KF-09 trigger workflows completed successfully:

- Kordena KCA Commercial Gate — run `36787148166`;
- Kordena KCA15 Internal Homologation — run `36787148076`;
- Kordena KCA16 Full Commercial E2E — run `36787148226`;
- Kordena KCA17 Final Readiness — run `36787148302`;
- PR Superseded Runs Cleanup — run `36787148258`.

The KCA-16 run also passed:

- commercial security/integration matrix;
- migrations and schema baseline;
- high-confidence tracked-secret scan;
- Python dependency audit;
- Playwright Chromium E2E;
- accessibility;
- responsive baseline;
- performance baseline;
- Web ESLint;
- Web TypeScript;
- Web node regression;
- npm audit at HIGH severity;
- Next production build;
- full Python regression;
- diff whitespace.

KCA-17 independently passed backup/restore and rollback drill, safe-release default, security/chaos matrix, secret scan, dependency audits, full regression and Web production build.

## Release-runtime and FM Command evidence

The Kordena Railway release runtime had already deployed the previous exact staging SHA successfully before the KF-09 trigger. After merge of PR #168, Railway automatically started deployment of `d71c79b74d432d79226a7e2545b0328a231b8e95`.

FM Command live runtime was revalidated against Kordena using the existing governed S2S token:

- Render service: `srv-danhfirtqb8s73bug4ag`;
- Command commit: `847ed0167086a041fa4446fde2d64e4b29c690f3`;
- event: `kordena_runtime_bootstrap_verified`;
- timestamp: `2026-09-30T22:43:29.832Z`;
- sync result: `duplicate`;
- ingested facts: `0`.

After the smoke, bootstrap flags were restored to `false` and the clean Render deployment returned to `live`.

Read-only reconciliation of the Command PostgreSQL database showed:

- source count: 1;
- sync count: 1;
- completed sync count: 1;
- canonical fact count: 0.

Therefore the live verification was idempotent and did not create duplicate sources, duplicate syncs, or synthetic customer facts.

## Authority and manual-data rules

No manual SQL correction was used to make the controlled commercial E2E pass.

No authority bypass was introduced. Authentication, admin step-up, entitlement, commercial access gate, billing webhook boundary and FMCC bearer control remained active in the tested journey.

The read-only SQL query against the Command database was used only after the smoke to reconcile counts; it did not mutate state.

## Gate interpretation

`MASTER_COMMERCIAL_E2E_PASS = PASS_CONTROLLED_SANDBOX`

`NO_MANUAL_DATA_FIX = PASS`

`NO_AUTHORITY_BYPASS = PASS`

This is the maximum truthful KF-09 result without authorization for a real-money provider. The Master Schedule explicitly permits controlled sandbox execution when real money is not authorized.

The separate production billing prerequisite remains **PENDING_EVIDENCE** under KF-04/KCA-17 and is not converted to PASS by this certification.

Likewise, this certification does not claim that a new external customer was created on the live Railway database; public signup remains disabled there.

## Result

KF-G09 is certified for the controlled-sandbox path allowed by the Master Schedule.

This does **not** unlock KF-10 because earlier aggregate gates still contain external or physical-evidence blockers, including KF-04, KF-05 and the remaining physical Next.js click-audit portion of KF-08.
