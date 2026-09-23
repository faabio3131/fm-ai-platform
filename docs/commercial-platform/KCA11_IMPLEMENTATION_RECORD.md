# KCA-11 — Implementation Record

## Escopo

Expiração autoritativa de trial + Paywall + Recovery da FM Commercial Platform/Kordena, conforme `KCA11_EXECUTION_PROMPT.md`.

## Candidate funcional certificado

- SHA técnico: `f6b529d0cdfd14b11e5b82f9f7ac89803a2f0ea8`.
- Base de integração: `staging/kordena-premium` @ `9867651dc5422ff21f91392bdae9ce44afa536f3`.
- PR: #127 — OPEN/DRAFT.
- KCA-G10 previamente integrado/certificado.
- KCA-12/FM Control Center: NÃO INICIADO.

## Persistência / schema

- Nenhuma migration nova no KCA-11.
- Schema baseline preservado em **132 tabelas**.
- SHA-256 do schema baseline: `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- Migration manifest: PASS.

## Expiração autoritativa

Implementado e certificado:

- boundary temporal server-side/UTC;
- `now >= ends_at` não mantém trial operacional;
- trial expirado projeta `TRIAL_EXPIRED`;
- modo comercial restrito é `BILLING_ONLY`;
- scheduler atrasado não prolonga acesso;
- execução em lote possui limite explícito;
- repetição do processamento não regride estado;
- request gate também valida a expiração temporal, não dependendo exclusivamente da pontualidade do scheduler;
- auditoria/outbox/entitlement continuam no fluxo canônico.

Durante a auditoria pré-certificação foi encontrada e corrigida uma divergência de relógio: o scheduler aceitava um instante UTC explícito, porém o recálculo do entitlement usava um `now()` independente. O KCA-11 passou a propagar o instante autoritativo da transição para o recálculo do entitlement, preservando determinismo em reprocessamento/backfill.

## Request gate comercial

O gate comercial do backend:

- resolve tenant pela identidade/sessão server-side;
- falha fechado para tenant comercial gerenciado sem entitlement válido;
- bloqueia APIs operacionais quando o acesso está restrito;
- responde `402 PAYMENT_REQUIRED` com estado comercial seguro;
- não depende de decisão do browser;
- preserva as rotas mínimas necessárias para autenticação e recuperação comercial;
- não permite que headers do cliente se tornem autoridade de tenant.

A flag `commercial_access_gate_enabled` permanece configuração explícita de rollout; isso não autoriza abertura pública neste gate.

## Paywall Web

O shell autenticado possui `CommercialAccessGuard` e consome o estado comercial do backend.

Quando o acesso operacional está restrito, a superfície preserva:

- autenticação;
- consulta do estado comercial;
- listagem de planos;
- início de checkout canônico;
- seleção de método de pagamento suportado pelo contrato;
- suporte configurável por `NEXT_PUBLIC_SUPPORT_URL`;
- logout;
- mensagem explícita de preservação dos dados.

O frontend não grava estado comercial e não cria autoridade paralela.

O canal de suporte permanece configurável por ambiente e não é hardcoded. A configuração de produção é pré-requisito de rollout, não parte de uma cobrança real neste gate.

## Checkout e billing

- Checkout utiliza `/v1/commercial/checkout`.
- Idempotency key é enviada pelo cliente e validada pelo backend canônico.
- URLs de retorno seguem validação same-origin/HTTPS conforme ambiente.
- Nenhum provider financeiro real foi ativado.
- Nenhuma credencial real foi adicionada.
- Nenhuma cobrança real foi executada.

## Recovery

O recovery reutiliza as autoridades canônicas existentes:

- Subscription Engine KCA-08;
- Billing Provider boundary KCA-09;
- Webhook Inbox/Reconciliation KCA-10;
- Entitlement Authority KCA-04;
- projeção local Kordena.

Certificado:

- trial `EXPIRED` pode seguir para assinatura `ACTIVE` pela autoridade de assinatura;
- assinatura ativa recalcula o entitlement;
- projeção local volta a `FULL`;
- acesso operacional é restaurado sem alteração manual de banco;
- repetição da ativação/recovery é idempotente e não duplica o entitlement resultante;
- estados de trial não permitidos continuam fail-closed.

## Segurança e isolamento

Cobertura certificada inclui:

- stale/missing entitlement fail-closed;
- cross-tenant binding rejeitado;
- request gate no boundary HTTP;
- API operacional bloqueada mesmo sem depender da UI;
- sessão/autenticação preservada no paywall;
- RBAC/step-up comercial/admin herdados permanecem vigentes;
- nenhuma autoridade financeira ou operacional paralela criada.

## Testes obrigatórios do KCA-11

Cobertura confirmada para:

- expiração no boundary exato;
- trial ainda válido antes do boundary;
- scheduler atrasado;
- execução repetida/reprocessável;
- login após expiração;
- tentativa direta à API operacional protegida;
- paywall com planos/checkout/suporte/logout;
- preservação de dados por bloqueio sem mutação/deleção operacional;
- assinatura ACTIVE após trial EXPIRED restaura entitlement;
- recovery repetido/idempotente;
- stale/missing entitlement fail-closed;
- tenant isolation/cross-tenant fail-closed;
- regressão completa dos KCA anteriores.

## Evidência do candidate técnico

### KCA targeted

- **194 passed**
- **2 warnings**

### Full Python regression

- **1795 passed**
- **5 skipped**
- **102 warnings**

### Web

- Node tests: **16 passed**
- Node tests: **0 failed**
- Node tests: **0 skipped**
- ESLint: PASS
- TypeScript: PASS
- Next production build: PASS

### Static / infra

- compileall: PASS
- Migration manifest: PASS
- Schema baseline: PASS
- Ruff: PASS
- mypy: PASS — 78 source files
- diff whitespace: PASS

### CI do SHA técnico

No SHA `f6b529d0cdfd14b11e5b82f9f7ac89803a2f0ea8`:

- Kordena KCA Commercial Gate: SUCCESS
- WP-031 Master Gate: SUCCESS
- WP-031J Web UX Functional: SUCCESS
- WP-031L Regression Channel Parity: SUCCESS
- Web Parity WP022 Certification: SUCCESS
- Commercial Runtime Readiness V1: SUCCESS
- Kordena V1 Visual Premium Gate: SUCCESS
- PR Superseded Runs Cleanup: SUCCESS
- Vercel: SUCCESS

Resultado: **8/8 GitHub Actions SUCCESS + Vercel SUCCESS**.

## Governança

- PR #127 permanece OPEN/DRAFT.
- Nenhum merge executado.
- Nenhum deploy público autorizado/executado por este gate.
- `main` não alterada por este fechamento.
- Nenhum cliente real criado.
- Nenhum trial real criado.
- Nenhuma assinatura real criada.
- Nenhum provider/credencial/cobrança real utilizado.
- KCA-12/FM Control Center permanece NÃO INICIADO.

## Gate

**KCA-G11: PASS no candidate técnico `f6b529d0cdfd14b11e5b82f9f7ac89803a2f0ea8`.**

O HEAD documental criado pelo fechamento deste registro/tracker deve ser recertificado antes de qualquer merge.
