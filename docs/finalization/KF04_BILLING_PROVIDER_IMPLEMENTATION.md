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


## Identidade canônica por recebimento

Nenhum pagamento SaaS novo pode entrar no ledger sem vínculo resolvido com a
assinatura interna. O envelope de identidade financeira é:

```text
product_code
fm_customer_id
product_account_id
tenant_id
subscription_id
billing_transaction_id
provider_account_id
external_transaction_ref
last_external_event_id
correlation_id
```

Regras:

- `fm_customer_id` é a identidade comercial global do cliente na FM;
- `product_account_id` separa a relação desse cliente com cada produto;
- `product_code` impede misturar Kordena, IRON, CampaIA ou produtos futuros;
- `tenant_id` mantém o escopo operacional do produto;
- `subscription_id` identifica o contrato recorrente;
- `billing_transaction_id` identifica o lançamento canônico interno;
- `provider_account_id + external_transaction_ref` identifica univocamente a
  transação no provider;
- rebind de uma transação existente para outro cliente/produto/assinatura é
  proibido;
- pagamento sem binding de assinatura permanece fora do ledger financeiro e é
  tratado como pendência/retry governado;
- transações históricas sem evidência suficiente não recebem identidade
  inventada durante migration;
- batches, inadimplência, reconciliação e métricas do Command devem agrupar
  primeiro por `product_code` e depois por `fm_customer_id` /
  `product_account_id`, nunca somente por nome, e-mail ou referência externa.

Isso mantém o recebimento de cada produto segregado mesmo quando produtos
diferentes usam o mesmo provider ou a mesma conta bancária da FM.

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

## Configuração futura no Command

A conta recebedora da FM permanece deliberadamente não configurada nesta PR.
Nenhum dado bancário, CPF, CNPJ, Access Token ou Webhook Secret real foi
incluído.

O Command passa a expor uma fronteira privada para configuração governada:

```text
/v1/control-plane/fmcc/billing
```

A configuração é provider-neutral e orientada pelo registry runtime. O próprio
adapter publica os campos de credencial necessários, evitando hardcode da UI
para um fornecedor específico.

Para o Mercado Pago Subscriptions, os campos atuais são apresentados pelo
adapter como:

- Access Token;
- Webhook Secret.

A interface administrativa deve permitir selecionar:

- provider disponível;
- titular **Pessoa Física (PF)** ou **Pessoa Jurídica (PJ)**;
- ambiente sandbox/produção;
- formas de pagamento;
- recorrência;
- webhooks;
- prioridade/routing.

Credenciais são armazenadas somente pelo fluxo cifrado de Vault. A UI/API retorna
apenas `credential_configured=true/false`, nunca o segredo resolvido.

Uma provider account de produção pode permanecer em `DRAFT` ou
`VALIDATING` sem os dados externos. A promoção a `ACTIVE` exige:

1. tipo de titular PF/PJ explícito;
2. credencial configurada;
3. connection test válido;
4. transição governada de status.

`legal_entity_ref` é opcional até existir um perfil jurídico canônico. Não se
inventa identificador para preencher a configuração.

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
