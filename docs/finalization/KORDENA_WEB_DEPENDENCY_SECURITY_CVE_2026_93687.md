# Kordena — Web Dependency Security Isolation

**Data:** 02/10/2026
**Status:** controle compensatório temporário, bloqueante e auditável

## Contexto

KCA-16 e KCA-17 identificaram `CVE-2026-93687` / `GHSA-vfj7-8cjw-p6xm` em `braces`, introduzido transitivamente pela toolchain de desenvolvimento do Next.js/ESLint.

O pacote não é uma dependência escolhida diretamente pelo Kordena para o runtime.

## Decisão de segurança

O gate não é desativado e `npm audit fix --force` não é usado.

A política passa a exigir simultaneamente:

1. `npm audit --omit=dev --audit-level=high` com **0 HIGH e 0 CRITICAL**;
2. prova automática de que `braces` está **ausente** da árvore de dependências de produção;
3. audit completo incluindo devDependencies;
4. exceção somente para o advisory exato `GHSA-vfj7-8cjw-p6xm`, pacote `braces`, severidade máxima `high`;
5. qualquer outro HIGH/CRITICAL continua sendo **FAIL**;
6. a exceção expira para revisão obrigatória em `2026-10-10`;
7. se o advisory deixar de existir na árvore, a exceção se torna inválida e o CI exige sua remoção.

## Evidência produzida

Os gates KCA-16/KCA-17 executam:

`.github/scripts/verify_web_dependency_security.mjs`

e produzem:

`evidence/web-dependency-security.json`

O arquivo separa explicitamente o estado de produção do estado das dependências de desenvolvimento.

## Exit criteria

A exceção deve ser removida imediatamente quando:

- a árvore de dependências deixar de reportar o advisory; ou
- existir atualização upstream aplicável que elimine a vulnerabilidade sem degradar segurança/compatibilidade.

Nenhuma vulnerabilidade HIGH/CRITICAL de runtime pode ser aceita por esta política.
