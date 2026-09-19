# WP-013 + WP-014 — Certificação Integrada

Data da certificação: 2026-09-15
Branch: `feat/web-parity-v1-total-original-migration`
Base preservada: `feat/web-parity-v1-wp010-wp011-delivery-entrega`
SHA técnico certificado antes deste registro: `52874816779d2d91e8ce0ac0006e6d99938bb135`

## Status

- WP-013 — Catálogo Administrativo: **MIGRADO / CERTIFICADO / 100% VERDE**.
- WP-014 — Engenharia de Cardápio / Ficha Técnica: **MIGRADO / CERTIFICADO / 100% VERDE**.

A certificação preserva o catálogo canônico existente. Nenhum segundo catálogo, ficha técnica, serviço de preços ou persistência paralela foi criado.

## Auditoria e correção funcional

A auditoria confirmou que WP-013 já reutilizava o boundary canônico `/v1/catalogo`, com sessão assinada priorizada por `AuthSessionRuntime`, isolamento de unidade, compatibilidade Basic somente para legado/testes e step-up administrativo para mutações Web.

No WP-014 foi reproduzida a pendência histórica do preço sugerido. A interface calculava a sugestão, mas copiava o valor automaticamente para o preço final apenas quando `preco === 0`. Depois de mudanças na receita ou margem, o valor final poderia deixar de refletir a sugestão corrente.

A correção removeu esse preenchimento automático implícito e adicionou a ação explícita **Aplicar preço sugerido**. O preço final continua editável manualmente; a aplicação da sugestão somente ocorre por decisão do usuário e é arredondada para duas casas decimais. A persistência continua usando `criarPratoComFicha` e a aplicação canônica `AplicacaoLegacyCardapioV1`.

## Evidências funcionais preservadas

A matriz existente comprova, entre outros pontos:

- listagem e filtros do catálogo por unidade;
- categorias da unidade ativa;
- criação e edição de produto;
- preço e disponibilidade;
- isolamento entre unidades;
- idempotência de criação;
- sessão ativa e troca autorizada de unidade;
- rejeição sem credenciais;
- insumos e ficha técnica escopados;
- criação atômica e idempotente de prato + ficha;
- rollback integral em falha parcial;
- importação Gemini pelo boundary canônico;
- rejeição de insumo de outra unidade;
- persistência sem catálogo paralelo.

## Teste de contrato adicionado

Arquivo: `tests/contract/test_web_catalogo_ficha_wp013_wp014.py`

O contrato prova que:

1. o catálogo Web reutiliza `build_http_app` e `build_catalogo_router` canônicos;
2. a sessão assinada é resolvida por `auth_runtime.resolver_identidade(request)`;
3. mutações Web preservam `ADMIN_ACESSAR` e step-up administrativo;
4. o frontend usa cookies de sessão com `credentials: "include"`;
5. a ficha usa aplicação explícita da sugestão de preço;
6. o comportamento antigo `if (preco === 0)` não permanece;
7. o preço final manual continua disponível;
8. a persistência permanece na aplicação canônica existente.

## Evidência do gate WP-013/WP-014

Workflow: `Web Parity Phase 1 WP013-WP014 Certification`
Run: `35020493501`
Job: `104554640418`

Resultado integral: **SUCCESS**.

- Compile da superfície canônica: PASS.
- Ruff: PASS.
- mypy: PASS (`Success: no issues found in 2 source files`).
- Matriz direcionada Catálogo/Ficha: **23 passed**.
- Regressão Python completa: **1494 passed, 5 skipped**.
- ESLint do catálogo/ficha: PASS.
- TypeScript: PASS.
- Next production build: PASS.
- `git diff --check`: PASS.

## Evidência transversal no mesmo SHA técnico

Também concluíram com sucesso no SHA `52874816779d2d91e8ce0ac0006e6d99938bb135`:

- `Commercial Runtime Readiness V1` — run `35020493494`.
- `PR Superseded Runs Cleanup` — run `35020493480`.
- `Web Parity WP028-WP030 Gate` — run `35020493464`.
- `Assistente Fase 4 Gate V1` — run `35020493468`.
- `Web Parity Phase 1 WP010-WP011 Certification` — run `35020493534`.

## Governança

- PR #118 permanece OPEN/DRAFT.
- Nenhum merge foi realizado.
- Nenhum deploy foi realizado.
- Nenhuma V2 foi iniciada.
- Nenhum domínio paralelo foi introduzido.
- Não há bloqueio funcional residual conhecido em WP-013 ou WP-014 após esta certificação.

## Próxima etapa autorizada

Após a recertificação deste commit documental no HEAD exato, a Fase 1 pode avançar para WP-015 — Estoque / Validades.
