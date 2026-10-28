# ADR-KCA-002 — Global Identity + Memberships
Status: ADOTADO COMO TARGET; IMPLEMENTAÇÃO KCA-02

## Contexto
No CURRENT o e-mail é único em `fm_usuarios_v1` e o usuário contém um único `tenant_id`.

## Decisão
Separar identidade humana global de memberships em produto/tenant. O tenant ativo será resolvido por membership autorizado, nunca apenas pelo e-mail.

## Alternativas
Manter um usuário por tenant foi rejeitado como arquitetura definitiva por impedir naturalmente a mesma identidade em organizações diferentes.

## Consequências
Exige evolução controlada de autenticação/sessão e testes cross-tenant.

## KCA-01
Nenhuma mudança de identidade será feita neste bloco.

## Rollback
Migração futura será aditiva antes de retirar restrições legadas.
