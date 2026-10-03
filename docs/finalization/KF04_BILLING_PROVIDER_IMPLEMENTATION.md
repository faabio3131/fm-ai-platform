# KF-04 — SaaS Billing Provider Implementation

**Project:** Kordena  
**Status:** IMPLEMENTED — aguardando certificação da PR  
**Data:** 02/10/2026

## Objetivo

Fechar a lacuna técnica entre a arquitetura provider-neutral KCA-09/KCA-11 e um
provider SaaS recorrente real, sem executar cobrança financeira e sem misturar o
billing da Nova FM com pagamentos operacionais dos estabelecimentos.

## Provider técnico candidato

```text
MERCADO_PAGO_SUBSCRIPTIONS
```

Este provider code é deliberadamente separado da integração operacional
`mercado_pago` já existente para Pix/Orders de restaurantes.

## Autoridade de preço

O Mercado Pago não se torna autoridade comercial do Kordena.

A autoridade permanece no catálogo versionado KCA-03:

```text
plan_code
→ plan_version_id
→ price_id
→ contracted_amount
→ currency
→ billing_period
```

O checkout envia ao provider um snapshot já contratado pelo domínio comercial.

## Composição

O runtime Web passa a registrar o adapter técnico no
`BillingProviderAdapterRegistryV1`.

Registrar o adapter **não ativa billing**.

Para qualquer chamada real continuam obrigatórios:

- provider account persistido;
- ambiente compatível;
- credencial por referência governada;
- connection test PASS;
- provider account ACTIVE;
- routing policy ativa;
- capability recurring;
- capability webhooks.

Na ausência desses itens o fluxo falha fechado.

## Credencial

O adapter recebe uma única referência de segredo já governada pelo Commercial
Billing/Vault. O valor resolvido deve ser um JSON contendo:

```json
{
  "access_token": "...",
  "webhook_secret": "..."
}
```

O valor não é persistido pelo adapter e não é incluído em repr/logs.

## Operações implementadas

- connection test somente leitura;
- customer create;
- recurring checkout/preapproval;
- recurring subscription create;
- subscription amount/frequency change;
- subscription cancellation;
- authorized-payment fetch/reconciliation;
- HMAC webhook verification;
- subscription event normalization;
- payment event normalization.

## Segurança

- `X-Idempotency-Key` em mutações;
- timeout explícito;
- sem retry oculto no adapter;
- auth/validation/conflict/rate-limit/timeout/5xx mapeados para erros canônicos;
- webhook HMAC-SHA256 verificado antes de qualquer consulta de reconciliação;
- payload de webhook não é tratado como autoridade financeira para valor/status:
  o adapter consulta a API autenticada antes de normalizar o evento;
- períodos de cobrança desconhecidos falham fechado;
- nenhuma credencial real incluída no repositório.

## Estado externo

Este bloco técnico **não** promove o gate final:

```text
BILLING_PROVIDER_ADAPTER_READY = PENDING_PR_CERTIFICATION
PRODUCTION_MERCHANT_ACCOUNT = PENDING_EXTERNAL
PRODUCTION_CREDENTIAL = PENDING_EXTERNAL
PRODUCTION_CONNECTION_TEST = PENDING_EXTERNAL
PRODUCTION_WEBHOOK_REGISTRATION = PENDING_EXTERNAL
REAL_MONEY_VERIFICATION = NOT_AUTHORIZED
REAL_CHARGE_EXECUTED = NO

BILLING_PRODUCTION_READY = BLOCKED_EXTERNAL
```

Somente evidência externa real pode promover `BILLING_PRODUCTION_READY` para
PASS.
