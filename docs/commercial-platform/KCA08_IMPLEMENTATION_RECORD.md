# KCA-08 — Implementation Record

## Escopo
Subscription Engine canônico e provider-neutral, com lifecycle persistente, binding histórico de plano/versão/preço, conversão Trial → Subscription, idempotência, concorrência otimista, auditoria/outbox e integração com Entitlement Authority.

## Candidate funcional
- SHA: `e5f63d6ee7bba2e19ad4daf5102e36116ee9f11d`
- Base da execução: `staging/kordena-premium@40e2029019fb426cb22f55ebf7137474661bfda5`
- KCA-G7 previamente certificado.

## Persistência
- Migration: `0056_commercial_subscription_v1`.
- Tabela principal: `fm_commercial_subscriptions_v1`.
- Schema baseline: **125 tabelas**.
- Schema SHA-256: `c6caa6d8ab1b58ae318b20e4b003b6db181f5211884e8a42eb4b09dd78ff0251`.

## Controles certificados
- State machine explícita: PENDING / ACTIVE / PAST_DUE / SUSPENDED / CANCELED.
- CANCELED permanece terminal.
- Recuperação PAST_DUE → ACTIVE e SUSPENDED → ACTIVE.
- Binding persistente de `plan_code`, `plan_version_id`, `price_id`, moeda, periodicidade e valor contratado.
- Alteração de catálogo posterior não reescreve o contrato histórico já persistido.
- Criação idempotente com idempotency key + request hash e conflito explícito de payload.
- Uma assinatura por Product Account; duplicidade protegida.
- Optimistic concurrency/version em mutações.
- Conversão Trial ACTIVE → CONVERTED coordenada com ativação da assinatura.
- Trial histórico preservado após conversão.
- Subscription Engine não concede acesso diretamente; sincroniza a Entitlement Authority e projeção local.
- Estados comerciais ACTIVE/PAST_DUE/SUSPENDED/CANCELED são projetados pelo boundary canônico.
- Customer/Product Account/Tenant e catálogo são validados fail-closed.
- Cross-tenant e price/plan-version mismatch negados.
- Outbox e auditoria seguem os contratos comerciais existentes.
- Nenhum provider financeiro concreto foi conectado em KCA-08.

## Evidência de testes — candidate
- Compile: PASS.
- Migration manifest: PASS.
- Schema baseline: PASS.
- Ruff/mypy KCA: PASS.
- KCA targeted: **134 passed, 2 warnings**.
- Full Python: **1735 passed, 5 skipped, 102 warnings**.
- Web ESLint: PASS.
- Web TypeScript: PASS.
- Web Node: **14 tests, 14 pass, 0 fail, 0 skipped**.
- Next production build: PASS.
- Diff whitespace: PASS.
- GitHub Actions associados ao candidate: **13/13 SUCCESS**.

## Governança
- PR #126 permanece OPEN/DRAFT.
- Nenhum merge.
- Nenhum deploy público.
- `main` não alterada.
- Nenhum cliente real, cobrança real ou provider real.
- KCA-09 não foi iniciado antes da certificação funcional do G8.

## Gate
**KCA-G8: PASS**

## Rollback / mitigação
Mudanças são aditivas e versionadas. Preservar histórico de assinatura e aplicar forward-fix em regressões posteriores; não apagar ou reescrever estados comerciais históricos para reparar inconsistências.
