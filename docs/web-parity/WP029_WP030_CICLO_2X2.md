# Kordena V1 — Ciclo WP-029 + WP-030

## Estado do ciclo

- PR oficial: **#118 — OPEN / DRAFT / NÃO MERGEADA**.
- Branch: `feat/web-parity-v1-total-original-migration`.
- Base preservada: `731f6db17ec46a8173d10dd29897c8c623e52f16`.
- HEAD funcional certificado do WP-029: `9d082a397d6fa0b08ed67e08f80ec818167961a8`.
- Regra de avanço: nenhum WP seguinte começa antes de o atual estar literalmente 100% verde.

## WP-029 — Pagamentos / PIX / Provedores

**Status: MIGRADO / 100% VERDE.**

### Autoridades canônicas preservadas

A migração Web não criou segundo checkout, segundo fluxo PIX, segundo webhook nem segundo ledger. A superfície nova reutiliza:

- `core/pagamentos/*` para domínio, ledger append-only, idempotência, concorrência e modelos financeiros;
- `application/pagbank.py` para criação/processamento do PIX PagBank;
- `application/pagbank_reconciliacao.py` para reconciliação autenticada com o provedor;
- `infra/pagamentos/pagbank_runtime.py` para resolução tenant/unidade da referência de credencial sem devolver o segredo;
- checkout/pagamento operacional já existente no PDV.

### Superfície Web entregue

- rota Next.js: `/pagamentos`;
- façade HTTP session-aware em `http_api/pagamentos_web.py`;
- Application Web em `application/pagamentos_web.py`;
- cliente Web em `web/src/features/pagamentos/services/pagamentos-api.ts`;
- workspace em `web/src/features/pagamentos/components/PagamentosWorkspace.tsx`;
- registro no Shell sem ampliar privilégios;
- contrato HTTP dedicado em `tests/api/test_pagamentos_web_http_contract.py`.

A consulta exige `financeiro.visualizar`. A reconciliação exige adicionalmente `pagamento.confirmar`. Tenant e unidade vêm da sessão assinada; `X-Tenant-ID` e `X-Unit-ID` não substituem o escopo da sessão. Segredos do PagBank não são serializados para a Web.

### Evidência de certificação

Workflow `Web Parity WP028-WP030 Gate`, run `34905146574`, job `wp028-wp029`:

- `py_compile`: PASS;
- Ruff: PASS;
- mypy: PASS — 4 arquivos sem issues;
- matriz Python WP-028 + WP-029 + regressões de pagamentos/PagBank/PIX: **54 passed, 0 failed**;
- ESLint: PASS;
- TypeScript `tsc --noEmit`: PASS;
- Next.js production build: PASS;
- `git diff --check`: PASS;
- rota `/pagamentos` presente no build de produção.

No mesmo HEAD, os workflows obrigatórios associados à PR também concluíram com sucesso:

- Commercial Runtime Readiness V1: SUCCESS;
- Assistente Fase 4 Gate V1: SUCCESS;
- PR Superseded Runs Cleanup: SUCCESS;
- Web Parity WP028-WP030 Gate: SUCCESS.

### Decisão de fechamento

WP-029 está certificado como **MIGRADO / 100% VERDE** no HEAD funcional `9d082a397d6fa0b08ed67e08f80ec818167961a8`. Nenhuma promoção para merge, deploy ou produção foi feita.

## WP-030 — Cardápio Digital público / Autosserviço

**Status neste checkpoint: PENDENTE DE IMPLEMENTAÇÃO / auditoria de autoridade iniciável somente após o fechamento documental do WP-029.**

Escopo constitucional já registrado:

- obrigatório para V1.0;
- reutilizar Catálogo, Pedido/Checkout, Delivery, Central de Pedidos e Pagamentos;
- não criar segundo catálogo, pedido, checkout ou pagamento;
- não introduzir domínio fiscal;
- a superfície pública não pode confiar em tenant/unidade arbitrários enviados pelo navegador.

Antes de qualquer implementação, o WP-030 deve auditar o mecanismo canônico de identificação pública do estabelecimento/unidade. Se essa autoridade pública segura não existir ou exigir decisão de produto/segurança, a execução deve parar e pedir decisão ao proprietário em vez de inventar uma nova política.

## No-go

- PR #118 permanece Draft e não mergeada;
- sem deploy/produção;
- sem force push/rebase/reset destrutivo;
- sem segredo real no Git;
- WP-031 Fiscal permanece backlog futuro e não deve ser implementado por este ciclo.
