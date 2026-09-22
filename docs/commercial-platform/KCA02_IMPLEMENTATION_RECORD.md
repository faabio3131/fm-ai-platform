# KCA-02 — Global Identity + Memberships

**Status:** IMPLEMENTAÇÃO CANDIDATA — AGUARDA CI / GATE KCA-G2
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
