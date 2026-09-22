# Kordena — KCA-00 System Design Comercial

**Status:** APROVADO PARA EXECUÇÃO KCA-01
**Data:** 2026-09-21
**Base factual revisada:** `staging/kordena-premium@55ef4cacf7df6e55c533e815f35bf0a6e50f1adf`

## Objetivo

Adicionar a fundação comercial que falta ao Kordena sem criar autoridade paralela ao domínio operacional existente.

O Kordena permanece autoridade sobre tenant, unidade, usuários operacionais e dados do restaurante. A FM Commercial Platform passa a ser a autoridade compartilhada para cliente comercial global, product account, catálogo comercial, trial, assinatura, billing e entitlement.

## CURRENT comprovado

- `main@5a17b0c8a1cb6dad576ce5b089166748b138900c` é o CURRENT integrado oficial, porém está 394 commits atrás do staging funcional.
- PR #118 permanece OPEN/DRAFT em `feat/web-parity-v1-total-original-migration@bbbd1f879bddb1c7ea3b62b5e7b3b4e10b86dc1d`.
- `staging/kordena-premium@55ef4cacf7df6e55c533e815f35bf0a6e50f1adf` contém integralmente o HEAD da PR #118 mais três commits de composição de staging: Docker/Python 3.12, driver PostgreSQL psycopg3 e proxy Vercel→backend.
- O HEAD da PR #118 possui 30 workflow runs de PR concluídos com SUCCESS.
- O staging possui status SUCCESS de Railway e Vercel.
- O CURRENT de identidade local mantém e-mail globalmente único e um `tenant_id` diretamente no usuário.
- Não existe no CURRENT autoridade canônica de customer/product account/trial/subscription/billing SaaS/entitlement comercial.

## TARGET

```text
FM Commercial Platform
├── Commercial Registry
├── Product Accounts
├── Plan Catalog
├── Pricing / Promotions
├── Trial Engine
├── Subscription Engine
├── Billing
├── Entitlement
└── Provisioning
        ├── Kordena
        ├── Iron
        └── futuros produtos

FM Control Center
└── Control Plane / read models / administração governada
```

## IDs canônicos

- `fm_customer_id`: organização comercial global da Nova FM.
- `product_account_id`: relação de um customer com um produto.
- `tenant_id`: fronteira operacional do produto.
- `identity_user_id`: identidade humana global — TARGET KCA-02.
- `usuario_id`: identificador operacional legado do Kordena durante transição.
- `unidade_id`: unidade operacional.
- IDs futuros: `trial_id`, `subscription_id`, `billing_account_id`, `plan_id`, `price_id`.

Nenhum ID de provider externo é canônico.

## Boundaries

### Commercial Registry
Autoridade de `fm_customer_id`, dados comerciais mínimos e classificação da conta.

### Product Account Registry
Autoridade de `product_account_id`, `product_code`, binding com customer e, quando provisionado, `product_tenant_id`.

### Kordena
Autoridade de tenant, unidade, operação, pedidos, estoque, usuários operacionais e RBAC do produto.

### FM Control Center
Control Plane. Não grava diretamente em tabelas operacionais do Kordena.

## Decisões congeladas

1. Global Identity + Memberships é o TARGET; implementação apenas no KCA-02.
2. FM Commercial Platform é compartilhada entre produtos.
3. O Kordena terá exatamente quatro planos: `KORDENA_PLAN_A` a `KORDENA_PLAN_D`. Nomes, preços e capacidades são configuráveis e versionados.
4. Entitlement é centralmente calculado, mas projetado localmente em cada produto; Kordena não depende de chamada ao FMCC em cada request.
5. Billing SaaS é separado de pagamentos operacionais do estabelecimento.
6. Contas `INTERNAL_TEST` não contam como cliente/trial/receita/churn comercial.
7. Provisioning entre contextos usa Saga + Outbox/Inbox quando o fluxo cruzar autoridades.
8. Preço e promoção nunca são hardcoded e toda mudança é versionada/auditada.

## KCA-01 autorizado

Implementar somente:
- Commercial Customer Registry;
- Product Account Registry;
- persistência aditiva;
- idempotência;
- auditoria;
- outbox de eventos mínimos;
- application boundary;
- API administrativa interna governada;
- testes, migrations e documentação.

Não implementar KCA-02 ou posteriores.

## Persistência

Inicialmente o módulo pode residir no mesmo PostgreSQL/cluster do Kordena, porém em tabelas/boundaries próprios. Isso é decisão de implantação, não fusão de autoridades.

Migrations devem ser forward/additive, rastreáveis, com fresh/upgrade convergence e sem alterar migrations históricas.

## Segurança

- backend é autoridade;
- rotas administrativas exigem sessão, `ADMIN_ACESSAR`, step-up e permissão adequada;
- nenhum tenant é aceito como autoridade apenas por vir do frontend;
- cross-customer/cross-tenant não autorizado é STOP;
- secrets nunca entram em registry, auditoria ou eventos.

## Idempotência e concorrência

Comandos de criação recebem uma chave de idempotência. Retry do mesmo comando e mesmo payload devolve o mesmo resultado lógico. Reuso da chave com payload incompatível falha fechado.

## Eventos KCA-01

- `customer.created`
- `customer.updated`
- `product_account.created`
- `product_account.activated`
- `product_account.suspended`
- `product_account.closed`

Persistência por outbox transacional; publicação externa/broker fica fora do KCA-01.

## Rollback

Rollback preferencial é forward-fix. O código KCA-01 pode ser desabilitado/retirado sem apagar tabelas. Dados comerciais já persistidos não são removidos automaticamente.

## STOP conditions

- conflito de autoridade;
- cross-tenant/cross-customer;
- migration destrutiva;
- hardcode de plano/preço;
- billing operacional misturado ao SaaS;
- rota pública acidental;
- idempotência não comprovada;
- schema/manifest divergente;
- CI crítico vermelho introduzido pelo KCA-01.

## Gate KCA-G0

KCA-G0 fica aprovado para início do KCA-01 com as ADRs KCA-001..010 adotadas e a reconciliação CURRENT registrada neste diretório.
