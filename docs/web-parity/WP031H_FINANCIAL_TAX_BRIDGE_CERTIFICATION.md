# WP-031H — Financial / Tax Bridge — Certificação

**Data:** 20/09/2026

**PR:** #118 — OPEN/DRAFT

**Branch:** `feat/web-parity-v1-total-original-migration`

**HEAD funcional:** `1cd054e4d0748faafeb781cb145d0f4824be2bad`

**Gate dedicado:** `WP-031H Financial Tax Bridge` run `35512559855` — SUCCESS

## Resultado

O WP-031H está **IMPLEMENTADO E CERTIFICADO INTERNAMENTE**. O bridge financeiro/tributário agora possui:

- extensão da autoridade canônica `core/pagamentos`, sem segundo ledger financeiro;
- obrigação de compra originada somente por recebimento físico autorizado;
- reconciliação entre fornecedor, pedido, recebimento, inbound e chave fiscal;
- recebimentos parciais e finais sem duplicação do total documental;
- idempotência por tenant, unidade, ambiente e recebimento;
- concorrência replay-safe;
- ajustes append-only para devolução e cancelamento;
- separação explícita entre obrigação, pagamento e liquidação;
- decisão de crédito tributário determinística, versionada e auditável;
- falha fechada quando regra tributária está ausente ou fora da vigência;
- invalidação de projeção de crédito quando a obrigação muda de versão;
- projeção reconciliável com IDs das fontes canônicas;
- migration aditiva `0048_fiscal_financial_tax_bridge_v1`;
- schema baseline convergente com 100 tabelas.

## Autoridade e efeitos

- Fiscal continua autoridade do documento.
- Procurement continua autoridade da aquisição e do recebimento físico.
- Estoque continua autoridade do saldo e dos movimentos.
- `core/pagamentos` continua autoridade de obrigação e pagamento.
- O bridge cria obrigação, mas nunca cria `Pagamento`, liquidação ou transferência automática.
- Crédito tributário não é inferido genericamente do imposto destacado.
- Homologação nunca cria obrigação operacional.

## Evidência de qualidade

- testes dirigidos WP-031H: **7 passed**;
- fiscal + pagamentos + fitness: **139 passed / 3 warnings**;
- regressão integral local e CI: **1614 passed / 5 skipped / 102 warnings**;
- Ruff da superfície financeira/fiscal: PASS;
- Mypy do bridge e adapter SQL: PASS;
- manifesto de migrations: PASS;
- schema baseline: `6724f5e6a6b558ac82f9f88e4c964978fb10b0a94eb81e75ee085a76ca6cb645`, 100 tabelas — PASS;
- Fiscal V1 vendored baseline `b336def47ad4f5188307102203f4e04b98406014`: PASS, 45 arquivos preservados;
- gate dedicado run `35512559855`: SUCCESS;
- workflows do HEAD funcional: **24/24 SUCCESS**.

## Limites preservados

Esta certificação não declara pagamento automático, liquidação, escrituração contábil/fiscal oficial, assinatura fiscal, uso de certificado real, integração real com provider/SEFAZ, homologação externa nem readiness de produção. Permanecem fora do WP-031H:

- signer, certificado e gateway/provider fiscal real — WP-031I;
- Web/UX funcional — WP-031J;
- Cognitive Fiscal — WP-031K;
- paridade de canais e regressão final — WP-031L;
- Master Gate, Visual Premium, merge e deploy.

## Estado após o gate

- WP-031H: `CERTIFIED_INTERNAL`;
- WP-031: `PENDING`, pois os blocos I→L e o Master Gate ainda não foram executados;
- WP-031I: `PENDING / NÃO INICIADO`;
- PR #118: permanece OPEN/DRAFT, sem merge e sem deploy.
