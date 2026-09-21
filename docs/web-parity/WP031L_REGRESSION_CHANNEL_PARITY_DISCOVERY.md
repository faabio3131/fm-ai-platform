# WP-031L — Regression / Channel Parity — CURRENT Discovery

**Status:** DISCOVERY concluída / implementação do gate autorizada
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
