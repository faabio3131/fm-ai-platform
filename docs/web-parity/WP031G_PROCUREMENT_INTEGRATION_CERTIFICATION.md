# WP-031G — Procurement Integration — Certificação

**Data:** 20/09/2026

**PR:** #118 — OPEN/DRAFT

**Branch:** `feat/web-parity-v1-total-original-migration`

**HEAD funcional:** `040d26154d3eb344e7b81b070ad619d22ff42357`

**Gate dedicado:** `WP-031G Procurement Integration` run `35510517704` — SUCCESS

## Resultado

O WP-031G está **IMPLEMENTADO E CERTIFICADO INTERNAMENTE**. A integração de compras agora possui:

- autoridade única de fornecedores, pedidos, aprovação, recebimentos e vínculos de produto;
- matching determinístico entre pedido, XML/DF-e oficial e confirmação física humana;
- estados completo, parcial, divergente e rejeitado;
- idempotência forte por tenant, unidade, ambiente e chave do comando;
- concorrência replay-safe sem dupla entrada física;
- movimento transacional no ledger canônico de estoque somente após aceite físico;
- devolução ao fornecedor sem apagar o histórico de recebimento;
- custo de aquisição histórico append-only, sem sobrescrever silenciosamente catálogo;
- isolamento completo entre homologação e produção;
- eventos e auditoria sanitizada;
- migration aditiva `0047_fiscal_procurement_integration_v1`;
- schema baseline convergente com 97 tabelas.

## Autoridade e efeitos

- XML/DF-e é a autoridade documental; a confirmação humana é a autoridade física.
- IA e captura visual não aprovam recebimento nem movimentam estoque.
- Somente recebimentos aceitos na partição `production` criam entrada no estoque.
- Divergência, rejeição e homologação não alteram o saldo operacional.
- O custo confirmado é histórico; não altera preço de catálogo silenciosamente.
- Nenhum efeito financeiro ou contábil foi criado neste bloco.

## Evidência de qualidade

- cenário concorrente repetido localmente: **100/100 PASS**;
- testes dirigidos fiscal + estoque + fitness: **114 passed / 3 warnings**;
- regressão integral local e CI: **1621 passed / 5 skipped / 102 warnings**;
- Ruff da superfície WP-031G: PASS;
- Mypy da superfície procurement: PASS;
- manifesto de migrations: PASS;
- schema baseline: `a6a9ce9704ec3d62a6e32f71f2d54e4709fe4b24f3c1e18338d67dc38d43bb10`, 97 tabelas — PASS;
- Fiscal V1 vendored baseline `b336def47ad4f5188307102203f4e04b98406014`: PASS, 45 arquivos preservados;
- gate dedicado run `35510517704`: SUCCESS;
- workflows do HEAD funcional: **23/23 SUCCESS**.

## Correção adversarial durante o gate

O primeiro head candidato expôs no CI uma corrida real no repositório em memória: leitura concorrente do histórico podia ocorrer durante a gravação. O head não foi certificado. A causa raiz foi corrigida com snapshot protegido por lock e reconciliação idempotente dentro da fronteira atômica; toda a matriz foi então reiniciada e aprovada no head funcional acima.

## Limites preservados

Esta certificação não declara efeito financeiro/contábil, assinatura fiscal, uso de certificado real, integração real com provider/SEFAZ, homologação externa nem readiness de produção. Permanecem fora do WP-031G:

- Financial / Tax Bridge — WP-031H;
- signer, certificado e gateway/provider fiscal real — WP-031I;
- Web/UX funcional — WP-031J;
- Cognitive Fiscal — WP-031K;
- paridade de canais e regressão final — WP-031L;
- Master Gate, Visual Premium, merge e deploy.

## Estado após o gate

- WP-031G: `CERTIFIED_INTERNAL`;
- WP-031: `PENDING`, pois os blocos H→L e o Master Gate ainda não foram executados;
- WP-031H: `PENDING / NÃO INICIADO`;
- PR #118: permanece OPEN/DRAFT, sem merge e sem deploy.
