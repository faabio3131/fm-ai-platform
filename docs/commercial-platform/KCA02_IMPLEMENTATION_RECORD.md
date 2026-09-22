# KCA-02 — Global Identity + Memberships

**Status:** CERTIFICADO — KCA-G2 PASS
**Base KCA-01 certificada:** `c623dd4a8bef04105b720d80c7d44b97bce00189`

## Objetivo

Separar identidade humana global do escopo operacional de tenant, preservando
compatibilidade com o Kordena V1 durante a transição.

## Implementação candidata

- `identity_user_id` global;
- `membership_id` por produto/tenant;
- credencial/senha no identity user;
- RBAC e unidades no membership;
- membership default para login inicial;
- uma identidade pode possuir múltiplos tenants Kordena;
- sessão carrega `identity_user_id + membership_id + tenant_id + unidade`;
- troca explícita de membership rotaciona sessão e revoga step-up;
- endpoint de listagem/seleção de memberships;
- backfill aditivo dos usuários legados;
- compatibilidade controlada com `fm_usuarios_v1`;
- nenhuma remoção de tabela/constraint legada neste bloco.

## Novas tabelas

- `fm_identity_users_v1`;
- `fm_identity_memberships_v1`;
- `fm_identity_membership_roles_v1`;
- `fm_identity_membership_units_v1`.

## Migration

`0050_global_identity_membership_v1`

## Regra de compatibilidade

O primeiro membership de uma identidade criada pelo fluxo V1 mantém
`usuario_id == identity_user_id == membership_id` apenas como ponte compatível.

Memberships adicionais recebem `membership_id` próprio e não criam um segundo
registro de credencial/e-mail.

Essa igualdade inicial não transforma os conceitos em uma única autoridade.

## Segurança

- tenant ativo vem do membership persistido;
- seleção de membership só aceita membership da mesma identidade global e produto;
- troca de membership revoga elevação administrativa;
- RBAC e unidades permanecem independentes por membership;
- membership de outra identidade falha fechado;
- nenhuma seleção confia em tenant enviado diretamente pelo frontend.

## Fora de escopo

Signup público, trial, planos/pricing, entitlement, subscription e billing
permanecem não iniciados.


## Audit & Fix executado

A implementação foi submetida aos gates KCA e transversais. Durante o ciclo de
certificação foram identificadas e corrigidas causas-raiz reais, sem reduzir
cobertura:

1. inspeção de existência do schema global usando o `Engine` podia trocar a
   conexão de SQLite em memória; a detecção passou a usar a conexão ativa da
   própria `Session`;
2. criação/reconstrução de identidade global foi estabilizada para preservar a
   mesma transação e a ponte de compatibilidade com o usuário V1;
3. import ordering e classe declarativa foram ajustados aos gates Ruff;
4. schema baseline foi atualizado para a migration 0050;
5. expectativas históricas do runtime foram reconciliadas com a nova migration,
   sem alterar migrations anteriores.

## Certificação do candidate

**Candidate SHA:** `b67b1e82459657b691bac8429af501548edb9ac5`

Workflow KCA: **Kordena KCA Commercial Gate** — run `35683797426` — **SUCCESS**.

Evidências:

- migration manifest: PASS;
- schema baseline: PASS — **109 tabelas**;
- schema SHA-256:
  `6792e66af3402609e367344cf50b4b7f19d8369404fe3153616f4248e1f7fcab`;
- Ruff: PASS;
- mypy: PASS — **30 source files**;
- KCA/security targeted: **71 passed, 0 failed**;
- full Python regression: **1669 passed, 5 skipped, 102 warnings**;
- Web ESLint: PASS;
- TypeScript: PASS;
- Web Node: **11 passed, 0 failed**;
- Next production build: PASS;
- diff whitespace: PASS.

Todos os **16 workflows** disparados no candidate concluíram em **SUCCESS**,
incluindo WP-031 Master Gate, WP-031 B/E/F/G/H/I/J/L, Pre-E Audit & Fix,
Web Parity WP022, Commercial Runtime Readiness, Schema Baseline e Assistente.

## Gate

**KCA-G2: PASS.**

A arquitetura agora suporta uma identidade humana global com memberships
isolados por produto/tenant. O KCA-03 e blocos posteriores permanecem não
iniciados.
