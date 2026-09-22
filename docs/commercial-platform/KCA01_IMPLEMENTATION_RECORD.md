# KCA-01 — Commercial Registry + Product Accounts

**Status:** IMPLEMENTAÇÃO CANDIDATA — AGUARDA CI / GATE KCA-G1
**Baseline SHA:** `922db0e3c568d8db232eecbf8059398e522e8603`

## Escopo implementado

- `fm_customer_id` como identidade comercial global;
- `customer_code` humano não autoritativo;
- classificação `internal_test | trial | paid | partner`;
- Product Account separado de customer e tenant;
- binding `product_code + product_tenant_id`;
- optimistic versioning;
- idempotência explícita de criação;
- auditoria comercial global pré-tenant;
- outbox comercial transacional;
- API administrativa interna protegida por sessão + `ADMIN_ACESSAR` + step-up;
- migration forward-only;
- testes unitários, integração, contrato HTTP e fitness.

## Tabelas

- `fm_customers_v1`
- `fm_product_accounts_v1`
- `fm_commercial_idempotency_v1`
- `fm_commercial_audit_v1`
- `fm_commercial_outbox_v1`

A auditoria/outbox comercial é separada da auditoria/outbox operacional porque customer/product account existem antes de um tenant/unidade e os envelopes operacionais atuais exigem esse escopo. Isso não transfere autoridade operacional do Kordena para a Commercial Platform.

## Invariantes

- `fm_customer_id != product_account_id != tenant_id`;
- provider externo nunca fornece ID canônico;
- binding de `product_code + product_tenant_id` é único;
- tenant binding não pode ser trocado silenciosamente;
- Product Account só entra em `active` com tenant;
- retry da mesma criação e mesmo payload retorna o mesmo agregado lógico;
- mesma idempotency key com payload diferente falha fechado;
- `INTERNAL_TEST` é classificação comercial, não autorização;
- nenhuma rota pública/signup é criada no KCA-01.

## Lifecycle Product Account

`requested -> provisioning | active | closed`

`provisioning -> active | suspended | closed`

`active -> suspended | closed`

`suspended -> active | closed`

`closed` é terminal.

## Rollback

Forward-fix. A migration não possui drop automático. Reverter o código não apaga customer/product account/outbox/auditoria já persistidos.

## Fora de escopo

KCA-02 Global Identity/Membership e todos os blocos posteriores permanecem não iniciados.
