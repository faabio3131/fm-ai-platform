# KCA-03 — Quatro Planos + Pricing + Promoções

**Status:** CERTIFICADO — KCA-G3 PASS
**Base KCA-02 certificada:** `b67b1e82459657b691bac8429af501548edb9ac5`
**Candidate funcional:** `4934ee2db1febe51b1bb4fd114faf2eddb94c89f`

## Objetivo

Criar o catálogo comercial governado do Kordena com exatamente quatro planos
canônicos, mantendo nomes, preços, benefícios, limites e promoções totalmente
configuráveis e versionados, sem exigir alteração de código ou deploy para
mudanças comerciais normais.

## Decisões implementadas

Os quatro códigos internos estáveis são:

- `KORDENA_PLAN_A`
- `KORDENA_PLAN_B`
- `KORDENA_PLAN_C`
- `KORDENA_PLAN_D`

A migration semeia apenas identidade/rank dos quatro planos. Nenhum nome
comercial, preço ou benefício definitivo é seed/hardcoded.

## Novas tabelas

- `fm_commercial_plans_v1`
- `fm_commercial_plan_versions_v1`
- `fm_commercial_plan_entitlements_v1`
- `fm_commercial_prices_v1`
- `fm_commercial_promotions_v1`
- `fm_commercial_promotion_versions_v1`
- `fm_commercial_promotion_plans_v1`

## Migration

`0051_commercial_catalog_v1`

A migration é aditiva e cria exatamente os quatro registros canônicos do
Kordena com status inicial `configuration_pending`.

## Catálogo versionado

Versões de plano carregam:

- nome comercial;
- descrição;
- elegibilidade de trial;
- marketing badge;
- metadata;
- entitlements/capabilities;
- limites e unidades;
- validade temporal;
- motivo da mudança;
- ator de criação/validação/publicação;
- timestamps;
- estado DRAFT → VALIDATED → PUBLISHED ou REVOKED.

Nova versão não reescreve silenciosamente a versão histórica anterior.

## Pricing

Preço é entidade separada e versionada por revisão.

Campos principais:

- currency;
- billing_period;
- amount;
- revision;
- policy de alteração;
- validade;
- status;
- motivo;
- auditoria de criação/validação/publicação.

Políticas suportadas:

- `NEW_CUSTOMERS_ONLY`
- `AT_NEXT_RENEWAL`
- `MIGRATION_SCHEDULED`
- `MANUAL_MIGRATION`

Alteração futura pode ser agendada. O preço anterior permanece reproduzível
historicamente.

## Promoções

Promoções são overlay comercial independente do preço-base.

Tipos:

- percentual;
- valor fixo;
- preço fixo.

Suportam:

- janela de validade;
- planos elegíveis;
- limite total de resgates;
- limite por customer;
- rules JSON;
- versionamento;
- validação;
- publicação;
- auditoria e outbox.

## Administração governada

A API administrativa foi incorporada à fronteira `/v1/admin/commercial`.

Requisitos:

- autenticação válida;
- `ADMIN_ACESSAR`;
- step-up administrativo ativo;
- idempotency key nas mutações críticas;
- optimistic versioning;
- preview/diff antes de publicação;
- motivo obrigatório;
- auditoria;
- outbox transacional.

Um código fora dos quatro planos canônicos é rejeitado.

## Eventos

O KCA-03 registra eventos comerciais, incluindo:

- `plan.version.published`;
- `price.published`;
- `promotion.version.published`.

A publicação externa em broker permanece separada do registro transacional
local da outbox.

## Audit & Fix

Durante a execução foram corrigidos, sem reduzir cobertura:

1. import ordering/formatting exigidos por Ruff;
2. tipagem de serialização de dataclasses;
3. validação de currency;
4. compatibilidade dos testes da migration KCA-02;
5. expectativas do runtime para a migration 0051;
6. schema baseline;
7. import ordering do migration runner.

## Certificação

Workflow canônico: **Kordena KCA Commercial Gate**
Run: `35730485861`
Resultado: **SUCCESS**

Evidências:

- Migration manifest: PASS;
- Schema baseline: PASS — **116 tabelas**;
- schema SHA-256:
  `64fa1bd61e7c174b3d7571b7bba02fd95d6ce65b0a642ee65de3a519fb352294`;
- Ruff/mypy KCA: PASS;
- KCA targeted: **81 passed, 0 failed**;
- Full Python regression: **1684 passed, 5 skipped, 102 warnings**;
- Web ESLint: PASS;
- TypeScript: PASS;
- Web Node: **11 passed, 0 failed**;
- Next production build: PASS;
- diff whitespace: PASS.

Todos os **16 workflows** disparados no candidate SHA concluíram em **SUCCESS**,
incluindo WP-031 Master Gate, Commercial Runtime Readiness, Schema Baseline,
Web Parity WP022, WP-031 B/E/F/G/H/I/J/L, Pre-E Audit & Fix e Assistente.

## Gate

**KCA-G3: PASS.**

## Fora de escopo

Ainda não iniciado:

- KCA-04 Entitlement Authority + projeção local;
- provisioning;
- signup público;
- trial;
- subscription;
- billing provider;
- paywall/recovery;
- FM Control Center completo;
- usuário interno de homologação;
- cliente externo;
- abertura pública.

Nenhum preço real ou nome comercial definitivo foi configurado neste bloco.
