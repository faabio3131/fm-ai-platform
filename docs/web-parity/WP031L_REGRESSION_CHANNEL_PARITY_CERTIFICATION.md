# WP-031L — Regression / Channel Parity — Certification

**Status:** CERTIFIED_INTERNAL
**Data:** 21/09/2026
**Repositório:** `faabio3131/fm-ai-platform`
**Branch:** `feat/web-parity-v1-total-original-migration`
**PR:** #118 — OPEN/DRAFT
**HEAD funcional certificado:** `c990d1e92f87a6eea2110f4bc3141bff4321f6c8`
**Workflow:** `WP-031L Regression Channel Parity`
**Run:** `35556451970` — SUCCESS
**Matriz do HEAD:** 28/28 workflows SUCCESS

## Escopo certificado

O WP-031L comprovou que os canais e superfícies do Kordena continuam convergindo nas autoridades canônicas já existentes, sem criar domínio fiscal por canal.

- PDV usa Checkout V1 canônico.
- Delivery Próprio converge no mesmo Checkout V1 transacional.
- Salão/Garçom reutiliza Pagamentos V1.
- Marketplaces convertem eventos externos para Pedido interno.
- Central/Pedido permanece autoridade operacional.
- Fiscal outbound nasce de `venda.criada` após reconhecimento financeiro canônico.
- Cognitive Fiscal permanece consulta read-only.
- Canais operacionais não executam regras do Fiscal Engine localmente.

## Evidências

- frozen Fiscal V1 baseline: PASS;
- compile: PASS;
- Ruff: PASS;
- mypy: PASS;
- migration manifest: PASS;
- schema baseline: 100 tabelas, SHA-256 `6724f5e6a6b558ac82f9f88e4c964978fb10b0a94eb81e75ee085a76ca6cb645`;
- authority fitness contract: 5 passed;
- operational channel parity: 101 passed / 14 warnings;
- fiscal + cognitive parity: 109 passed / 5 warnings;
- payment + stock + security: 150 passed / 56 warnings;
- full Python regression: 1642 passed / 5 skipped / 102 warnings;
- Web ESLint: PASS;
- Web TypeScript: PASS;
- Web Node: 6 passed / 0 failed / 0 skipped;
- Next production build: PASS;
- diff whitespace: PASS;
- matriz integral do SHA: 28/28 SUCCESS.

## Correções durante o bloco

O CI detectou e bloqueou três problemas no fitness contract criado para o próprio WP-031L: whitespace documental, formatação de import e uma suposição textual incorreta sobre enums dinâmicos. Todos foram corrigidos sem remover asserts, reduzir cobertura, adicionar skip/xfail ou alterar o produto para satisfazer o teste.

## Limites preservados

Esta certificação é interna. Não declara homologação SEFAZ/provider, certificado/CSC real, produção fiscal, merge, deploy, Visual Premium ou V2.

## Próximo bloco

`WP-031 Master Gate`.

O WP-031 continua `PENDING` até o Master Gate ser certificado.
