# WP-015 — Certificação Integrada de Estoque / Almoxarifado / Validades

Data da certificação: 2026-09-15
Branch: `feat/web-parity-v1-total-original-migration`
Base preservada: `feat/web-parity-v1-wp010-wp011-delivery-entrega`
SHA técnico certificado antes deste registro: `3daaddf7b97236ba0b80c13f0e36c91025f22a0c`

## Status

- WP-015 — Estoque / Almoxarifado / Validades: **MIGRADO / CERTIFICADO / 100% VERDE**.

A certificação preserva o estoque canônico e as fronteiras legadas governadas já existentes. Nenhum segundo estoque, WMS, persistência paralela, lote físico completo ou FEFO físico foi criado.

## Auditoria e gap fechado

A auditoria confirmou que a implementação Web já reutilizava as autoridades existentes:

- `application/legacy_estoque_transacoes.py` para gravações transacionais;
- `application/legacy_estoque_forecasting.py` para forecasting e alertas;
- `application/legacy_estoque_leitura_visual.py` para leitura visual;
- `http_api/estoque.py` como adaptador HTTP fino e session-aware;
- `infra/legacy_product_scope.py` para resolução explícita e fail-closed de tenant/unidade para loja legada;
- `/admin/estoque` e `web/src/features/backoffice/estoque` como superfície Web.

O gap encontrado não estava na regra de negócio. Faltava uma certificação HTTP/Web dedicada que comprovasse sessão, RBAC, step-up, spoofing de headers, isolamento cross-unit, persistência, forecasting e leitura visual de forma integrada.

Foram adicionados:

- `tests/api/test_estoque_http_contract.py`;
- `tests/contract/test_web_estoque_wp015.py`;
- `.github/workflows/web-parity-phase1-wp015-certification.yml`.

Nenhuma mudança funcional no domínio do estoque foi necessária para o gate ficar verde.

## Evidências funcionais e de segurança

A matriz dedicada comprova:

1. ausência de sessão é rejeitada;
2. perfil sem permissão de estoque é rejeitado;
3. sessão assinada governa tenant/unidade;
4. `X-Tenant-ID` e `X-Unit-ID` não sobrescrevem o escopo autenticado;
5. listagem retorna somente insumos da unidade ativa;
6. valor total e status de reposição são calculados sobre o estoque real da unidade;
7. mutações Web exigem step-up administrativo;
8. criação persiste na loja legada mapeada para a unidade autenticada;
9. leitura/lote atualiza item existente e cria novo item pelo application canônico;
10. exclusão cross-unit falha fechado e não remove o item remoto;
11. forecasting recebe tenant/unidade do contexto autenticado e permanece testável sem envio externo real;
12. leitura visual rejeita mídia inválida e arquivo vazio;
13. leitura visual válida delega ao application existente e persiste no escopo correto;
14. a Web usa cookies de sessão com `credentials: "include"` e delega as regras ao boundary `/v1/estoque`.

## Evidência do gate WP-015

Workflow: `Web Parity Phase 1 WP015 Certification`
Run: `35033773942`
Job: `104598077500`
HEAD técnico: `3daaddf7b97236ba0b80c13f0e36c91025f22a0c`

Resultado integral: **SUCCESS**.

- Compile da superfície canônica: PASS.
- Ruff: PASS.
- mypy: PASS (`Success: no issues found in 4 source files`).
- Matriz direcionada Estoque/Validades: **10 passed**.
- Regressão Python completa: **1503 passed, 5 skipped, 0 failed**.
- ESLint WP-015: PASS.
- TypeScript: PASS.
- Teste Node de navegação Backoffice: **3 passed, 0 failed**.
- Next production build: PASS.
- `git diff --check`: PASS.

## Limitações deliberadas preservadas

Permanecem fora do escopo desta migração conservativa:

- lote físico completo;
- FEFO físico;
- novo WMS;
- segunda persistência de estoque.

Essas ausências não foram mascaradas nem tratadas como funcionalidades concluídas.

## Governança

- PR #118 deve permanecer OPEN/DRAFT.
- Nenhum merge foi realizado por esta certificação.
- Nenhum deploy foi realizado.
- A `main` não foi alterada.
- Nenhuma V2 foi iniciada.
- Nenhum domínio paralelo foi introduzido.

## Próxima etapa autorizada

Após a recertificação deste commit documental no HEAD exato, a execução sequencial pode avançar para WP-016 — CRM / Clientes / Cashback.
