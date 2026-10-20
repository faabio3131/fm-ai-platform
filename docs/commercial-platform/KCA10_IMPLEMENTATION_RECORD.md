# KCA-10 — Implementation Record

## Escopo
Webhook Inbox + Reconciliation provider-neutral da FM Commercial Platform.

## Candidate funcional
- SHA: `ccdf7883f63d184e34dab51ad26babc69b3edf9a`.
- Base: `staging/kordena-premium`.
- KCA-G9B previamente certificado.
- KCA-11 não iniciado.

## Persistência
Migration:
- `0058_commercial_billing_events_v1`

Novas tabelas:
- `fm_billing_subscription_bindings_v1`
- `fm_billing_webhook_inbox_v1`
- `fm_billing_transactions_v1`
- `fm_billing_event_cursors_v1`
- `fm_billing_reconciliation_runs_v1`

Schema baseline:
- **132 tabelas**
- SHA-256: `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`

## Pipeline canônico de webhook
Fluxo final:
1. localizar provider account configurada;
2. verificar assinatura pelo adapter provider-neutral;
3. calcular body hash;
4. persistir Inbox durável;
5. payload bruto válido é cifrado antes da persistência;
6. nenhuma assinatura/raw payload é persistida em claro;
7. normalizar pelo adapter após Inbox durável;
8. resolver binding interno↔externo;
9. aplicar proteção de ordering;
10. aplicar Billing Ledger e/ou Subscription Engine canônico;
11. marcar PROCESSED ou classificar falha;
12. retry governado;
13. DEAD_LETTER após exaustão;
14. replay administrativo controlado.

## Inbox cifrada
- Cipher dedicado: `BillingWebhookPayloadCipher`.
- Fernet com chave mestra de infraestrutura.
- Campo persistido: `payload_ciphertext`.
- Raw body não é persistido.
- Assinatura não é persistida.
- Body hash permanece disponível para idempotência/replay protection.
- Payload cifrado permite normalização posterior, retry e replay sem perder o evento original.

## Idempotência e replay protection
- `provider_account_id + external_event_id` é único.
- Mesmo event ID + mesmo body hash: idempotente.
- Mesmo event ID + body hash diferente: fail-closed por replay conflict.
- Provider resend não duplica efeitos.

## Ordering
Cursor durável por stream:
- transação: `transaction:<external_transaction_ref>`
- assinatura: `subscription:<subscription_id>`

Proteção:
- provider sequence quando disponível;
- fallback por provider occurred_at;
- evento antigo não pode regredir estado;
- out-of-order fica `IGNORED_OUT_OF_ORDER`.

## Billing Ledger
Ledger provider-neutral persiste:
- provider account/code;
- external transaction reference;
- subscription interna opcional;
- tipo/status;
- amount/currency;
- provider sequence/time;
- último external event ID;
- reconciliation status;
- version/correlation.

IDs externos nunca substituem IDs internos.

## Subscription Binding
Binding explícito e auditável entre:
- provider account;
- internal subscription_id;
- external subscription reference;
- external customer reference opcional.

Eventos de assinatura sem binding ficam retryable em vez de inventar ownership.

## Retry / DLQ / Replay
Estados suportados:
- RECEIVED
- VERIFIED
- PROCESSING
- PROCESSED
- FAILED_RETRYABLE
- DEAD_LETTER
- IGNORED_OUT_OF_ORDER
- REJECTED

Retry:
- somente falhas classificadas como retryable;
- limite explícito;
- backoff exponencial limitado;
- exaustão → DEAD_LETTER.

Replay:
- somente DEAD_LETTER;
- exige controle administrativo existente;
- não contorna ordering, binding, idempotência ou validação canônica.

## Reconciliation
- Consulta provider através do BillingProvider KCA-09.
- Compara status/amount/currency com Billing Ledger.
- Marca IN_SYNC ou REPAIRED.
- Reparo é auditado.
- Provider/reference mismatch falha fechado.

## HTTP / Segurança
Ingress público:
- `/v1/commercial/billing/webhooks/{provider_account_id}`
- payload limitado;
- headers completos normalizados entregues ao adapter;
- nenhuma assinatura hardcoded;
- resposta não ecoa payload/segredo.

Admin:
- binding;
- consulta Inbox/DLQ;
- retry batch;
- replay;
- leitura de transaction;
- reconciliation manual.

Controles administrativos permanecem atrás de RBAC + step-up existente.

## Testes obrigatórios do cronograma
PASS:
- duplicate webhook;
- forged signature;
- event out of order;
- timeout sem estado financeiro parcial;
- provider resend;
- reconciliation repairs state.

Testes adicionais:
- event ID/body hash collision;
- payload cifrado em Inbox;
- retry após binding aparecer;
- retry exhaustion → DLQ;
- replay controlado;
- provider-neutral headers;
- public ingress fail-closed;
- admin step-up;
- schema/migration fitness;
- KCA-11 não antecipado.

## Evidência do candidate funcional
KCA targeted:
- **187 passed**
- **2 warnings**

Full Python:
- **1788 passed**
- **5 skipped**
- **102 warnings**

Web:
- Node tests: **14/14 PASS**
- ESLint: PASS
- TypeScript: PASS
- Next production build: PASS

Infra/gates:
- Migration manifest: PASS
- Schema baseline: PASS
- Ruff: PASS
- mypy: PASS
- compileall: PASS
- diff whitespace: PASS
- GitHub Actions candidate: **13/13 SUCCESS**

## Governança
- PR #126 permanece OPEN/DRAFT.
- Nenhum merge.
- Nenhum deploy.
- `main` não alterada.
- Nenhum provider financeiro real.
- Nenhuma credencial real.
- Nenhuma cobrança real.
- Nenhum webhook financeiro real externo.
- KCA-11 não iniciado.

## Gate
**KCA-G10: PASS no candidate funcional**

O HEAD documental final deve ser recertificado antes do encerramento definitivo.
