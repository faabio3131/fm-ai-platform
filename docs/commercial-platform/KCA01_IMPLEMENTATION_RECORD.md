# KCA-01 — Commercial Registry + Product Accounts

**Status:** CERTIFICADO — KCA-G1 PASS
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


## Certificação final

**Candidate SHA funcional:** `c623dd4a8bef04105b720d80c7d44b97bce00189`

### Audit & Fix executado

Durante a certificação foram encontrados e corrigidos, sem reduzir cobertura:

1. incompatibilidade de tipagem estática em `_hash_requisicao`, corrigida para aceitar `Mapping[str, object]`;
2. colisão de nome de módulo Pytest entre `tests/unit/comercial/test_modelos.py` e teste legado homônimo, corrigida renomeando o teste comercial;
3. expectativas históricas de migrations em testes runtime ainda encerradas em `0048`, reconciliadas com a nova migration `0049_commercial_registry_v1`.

### Evidências do Gate KCA-G1

Workflow canônico: **Kordena KCA Commercial Gate** — run `35681467454` — **SUCCESS**.

- compile Python: PASS;
- migration manifest: PASS;
- schema baseline: PASS — **105 tabelas**, SHA-256 `0890e133e2c91151f2da49a31d91d4bb800efc08a08c6594e36135c32a31c652`;
- Ruff/mypy KCA: PASS;
- testes direcionados KCA: **16 passed**;
- regressão Python completa: **1660 passed, 5 skipped, 102 warnings**;
- Web ESLint: PASS;
- TypeScript: PASS;
- Web Node tests: **11 passed, 0 failed**;
- Next production build: PASS;
- diff whitespace: PASS.

Todos os 15 workflows disparados no candidate SHA terminaram em SUCCESS, incluindo WP-031 Master Gate e regressões fiscais/Web transversais.

## Gate

**KCA-G1: PASS.**

KCA-02 permanece **NÃO INICIADO**.
