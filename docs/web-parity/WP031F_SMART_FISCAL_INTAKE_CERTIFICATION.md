# WP-031F — Smart Fiscal Intake — Certificação

**Data:** 20/09/2026

**PR:** #118 — OPEN/DRAFT

**Branch:** `feat/web-parity-v1-total-original-migration`

**HEAD funcional:** `b3a5424d74497a55c96046585793d271e658887f`

**Gate dedicado:** `WP-031F Smart Fiscal Intake` run `35487571304` — SUCCESS

## Resultado

O WP-031F está **IMPLEMENTADO E CERTIFICADO INTERNAMENTE**. O intake fiscal agora possui:

- pipeline único para DF-e, XML, PDF, imagem e câmera;
- DF-e/XML normalizados como fonte oficial, reaproveitando a fundação inbound do WP-031E;
- PDF, imagem e câmera tratados somente como evidência preliminar;
- arquivo original imutável e captura preliminar persistidos atomicamente;
- extração por IA atrás de boundary injetável, com JSON estruturado estrito e validação local de mídia;
- idempotência por tenant, unidade, ambiente e chave de captura;
- falha de extração durável, sanitizada e retomável;
- reconciliação determinística `MATCHED`, `PARTIAL` ou `DIVERGENT` contra o documento oficial;
- isolamento completo por tenant, unidade e ambiente;
- migration aditiva `0046_fiscal_smart_intake_v1`;
- schema baseline convergente com 92 tabelas.

## Autoridade e efeitos

- A IA não cria verdade fiscal e não substitui XML/DF-e oficial.
- Reconciliação não altera o documento oficial.
- O intake não movimenta estoque, não cria procurement e não produz efeitos financeiros ou contábeis.
- A leitura visual legada de estoque permanece histórica e não foi reutilizada como autoridade fiscal.

## Evidência de qualidade

- testes dirigidos WP-031F: **11 passed**;
- fiscais + fitness de migration/schema: **87 passed**;
- regressão integral local: **1601 passed / 5 skipped / 102 warnings**;
- Ruff da superfície fiscal: PASS;
- Mypy da superfície WP-031F: PASS;
- manifesto de migrations: PASS;
- schema baseline: `aa85a7c9cfedce5c86d2960d6c2c0e18ea354e25d49d73306edf0a8118258665` — PASS;
- Fiscal V1 vendored baseline `b336def47ad4f5188307102203f4e04b98406014`: PASS, 45 arquivos preservados;
- gate dedicado run `35487571304`: SUCCESS;
- workflows do HEAD funcional: **22/22 SUCCESS**.

## Limites preservados

Esta certificação não declara precisão de OCR em produção, homologação SEFAZ/provider nem readiness de produção. Permanecem fora do WP-031F:

- procurement, recebimento físico e efeitos de estoque — WP-031G;
- efeitos financeiros/contábeis — WP-031H;
- signer, certificado e gateway/provider fiscal real — WP-031I;
- Web/UX funcional — WP-031J;
- Cognitive Fiscal — WP-031K;
- paridade de canais, Master Gate, Visual Premium, merge e deploy.

## Estado após o gate

- WP-031F: `CERTIFIED_INTERNAL`;
- WP-031: `PENDING`, pois os blocos G→L e o Master Gate ainda não foram executados;
- WP-031G: `PENDING / NÃO INICIADO`;
- PR #118: permanece OPEN/DRAFT, sem merge e sem deploy.
