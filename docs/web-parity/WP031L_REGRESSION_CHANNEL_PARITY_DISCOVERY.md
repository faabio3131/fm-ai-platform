# WP-031L — Regression / Channel Parity — CURRENT Discovery

**Status:** CONCLUÍDO / CERTIFIED_INTERNAL
**Data:** 20/09/2026
**Repositório:** `faabio3131/fm-ai-platform`
**Branch:** `feat/web-parity-v1-total-original-migration`
**PR:** #118 — OPEN/DRAFT
**HEAD de entrada:** `2f25dcec54a07ccbff9ec4e29d76c519a187a2a1`
**Pré-condição:** WP-031K certificado; HEAD documental 27/27 workflows SUCCESS.

## CURRENT comprovado

- PDV Web cria Pedido via `ComandoCheckoutV1 -> executar_checkout_v1`.
- Delivery Próprio converge benefícios antes de delegar ao mesmo Checkout V1 transacional.
- Salão/Garçom reutiliza `core/pagamentos` para obrigação e confirmação financeira; não possui pagamento paralelo.
- Marketplaces convertem eventos externos para Pedido interno por `PedidosInternosMarketplaceSQLAlchemy`; não possuem domínio fiscal próprio.
- O Fiscal outbound nasce de `venda.criada`, produzido pela autoridade financeira canônica após reconhecimento de venda.
- Canais operacionais não devem importar `kordena_fiscal` nem application fiscal para executar regra fiscal local.
- Cognitive Fiscal permanece consulta read-only com autorização fiscal adicional.

## Decisão WP-031L

Não criar nova autoridade, adapter comercial ou fluxo fiscal por canal.

O bloco será fechado por:

1. fitness contract explícito de paridade/autoridade;
2. regressão dirigida de PDV, Salão/Garçom, Delivery/Entrega, Marketplaces, Central/Pedido, Pagamentos e Fiscal;
3. regressão de segurança/tenant/RBAC;
4. regressão Python integral;
5. ESLint, TypeScript, testes Node e Next production build;
6. migration manifest, schema baseline e diff whitespace;
7. matriz completa do HEAD sem falha ou pendência.

## Limites

Esta etapa não declara homologação externa, produção fiscal, merge, deploy, Visual Premium ou V2.


## Certificação

- HEAD funcional: `c990d1e92f87a6eea2110f4bc3141bff4321f6c8`.
- Workflow: `WP-031L Regression Channel Parity`.
- Run: `35556451970` — SUCCESS.
- Matriz do HEAD: 28/28 workflows SUCCESS.
- Fitness de autoridade: 5 passed.
- Operational channel parity: 101 passed / 14 warnings.
- Fiscal + Cognitive parity: 109 passed / 5 warnings.
- Payment + stock + security: 150 passed / 56 warnings.
- Full Python regression: 1642 passed / 5 skipped / 102 warnings.
- Web Node: 6 passed / 0 failed / 0 skipped.
- ESLint: PASS.
- TypeScript: PASS.
- Next production build: PASS.
- Schema baseline: 100 tabelas, SHA-256 `6724f5e6a6b558ac82f9f88e4c964978fb10b0a94eb81e75ee085a76ca6cb645`.
- Diff whitespace: PASS.

O WP-031 permanece PENDING somente até o WP-031 Master Gate. Esta certificação não declara homologação externa nem produção aprovada.
