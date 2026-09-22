# KCA-00 — Reconciliação do CURRENT

**Data:** 2026-09-21  
**Modo da auditoria:** leitura remota no GitHub antes da criação da branch KCA.

## Linhas relevantes

| Linha | SHA | Situação |
|---|---|---|
| `main` | `5a17b0c8a1cb6dad576ce5b089166748b138900c` | CURRENT integrado oficial |
| PR #117 head | `731f6db17ec46a8173d10dd29897c8c623e52f16` | OPEN/DRAFT; base da PR #118 |
| PR #118 head | `bbbd1f879bddb1c7ea3b62b5e7b3b4e10b86dc1d` | OPEN/DRAFT; baseline funcional certificado |
| `staging/kordena-premium` | `55ef4cacf7df6e55c533e815f35bf0a6e50f1adf` | CURRENT funcional/deploy mais avançado |

Comparações verificadas:
- `main...PR118`: 391 commits à frente, 0 atrás.
- `PR118...staging`: 3 commits à frente, 0 atrás.
- `main...staging`: 394 commits à frente, 0 atrás.

Os três commits exclusivos de staging modificam apenas composição/deploy:
- `Dockerfile`;
- `core/runtime/database.py`;
- `tests/test_runtime_database_driver.py`;
- `web/next.config.ts`;
- `web/src/lib/api.ts`.

Não há mudança de domínio comercial nesses três commits.

## CI

O HEAD da PR #118 possui 30 workflow runs associados ao commit e todos estão concluídos com `success`, incluindo WP-031 Master Gate, Commercial Runtime Readiness, Visual Premium e gates Web/Fiscal.

O HEAD de staging possui status de deploy `success` em Railway e Vercel. Como os workflows históricos de push estão fortemente acoplados à branch `feat/web-parity-v1-total-original-migration`, o KCA cria workflow próprio de baseline/quality gate.

## Decisão da base KCA

A branch oficial KCA deve partir de:

`staging/kordena-premium@55ef4cacf7df6e55c533e815f35bf0a6e50f1adf`

Motivo: é o superset linear do HEAD certificado da PR #118 e contém as três correções necessárias ao staging atualmente implantado.

A PR KCA deve ter como base `staging/kordena-premium` para manter o diff estritamente comercial e não misturar 394 commits de patrimônio anterior.

## Situação de PRs históricas

- PR #118: REFERÊNCIA/CANÔNICA DA MIGRAÇÃO WEB; não mergear ou fechar por este KCA.
- PR #117: dependência histórica da PR #118; não tocar neste KCA.
- demais PRs antigas: fora do escopo.

## Resultado

Não existe dúvida de branch canônica para esta missão: o Ponto Zero comercial é o HEAD do staging registrado acima.
