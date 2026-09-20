# FM Cognitive Core — Preview Deployment Contract

This contract deploys the **existing canonical Cognitive Core** as a dedicated
internal HTTP service for FM Control Center. It does not create a second Core.

## Render service

Recommended non-production service:

- name: `fm-cognitive-core-preview`
- repository: `faabio3131/fm-ai-platform`
- branch during certification: `feat/web-parity-v1-total-original-migration`
- runtime: Python 3.12
- build command: `pip install -r requirements.txt`
- start command:
  `uvicorn http_api.fmcc_core_app:build_fmcc_core_app --factory --host 0.0.0.0 --port $PORT`
- health check path: `/healthz`

Production is not authorized by this contract.

## Required runtime configuration

The service must receive configuration only through Render environment/secrets.

### Canonical runtime

- `FM_AI_ENV=staging`
- `DATABASE_URL`: PostgreSQL containing the canonical Kordena/Core control-plane
  schema and migrations;
- `FM_AI_TENANT_ID`: service runtime tenant scope required by the existing
  commercial runtime contract;
- `FM_AI_UNIDADE_ID`: service runtime unit scope required by the existing
  commercial runtime contract.

### Shared-Core service authentication

- `FM_CORE_SERVICE_TOKEN_REF=env:FM_CORE_SERVICE_TOKEN`
- `FM_CORE_SERVICE_TOKEN`: strong random service-to-service token.

The token value must never be committed, documented, logged or pasted in chat.

### AI routing control plane

- `FM_CORE_ROUTING_TENANT_ID`
- `FM_CORE_ROUTING_UNIT_ID`

These values point to the tenant/unit that owns the approved generative-AI
configuration in the canonical control plane. The corresponding database records
must contain an enabled and homologated `ia.generativa` route and a secret
**reference**, never a raw provider credential.

The provider secret itself remains resolved by the canonical `SecretStore`.

## FM Control Center Preview

Configure the FMCC Web Service with:

- `FM_CORE_BASE_URL=https://<shared-core-preview-service>`
- `FM_CORE_SERVICE_TOKEN=<same service token value>`

Do not append `/v1/fmcc` to `FM_CORE_BASE_URL`; the FMCC client appends the
versioned paths itself.

## Required smoke

1. `GET /healthz` on the shared Core returns HTTP 200.
2. Missing Bearer token on `POST /v1/fmcc/plan` returns HTTP 401.
3. FMCC authenticated user calls `POST /api/core/query`.
4. FMCC calls shared Core `/v1/fmcc/plan`.
5. The returned capability remains inside the FMCC allowlist.
6. FMCC MetricService resolves the governed metric for the authenticated tenant.
7. FMCC sends only governed facts/evidence to `/v1/fmcc/synthesize`.
8. Shared Core returns grounded text while FMCC preserves the same provenance.
9. A metric without governed value returns unavailable rather than a fabricated
   number.
10. No production deployment is performed.

F09 may be promoted from boundary-tested to integrated only after this smoke has
real evidence.
