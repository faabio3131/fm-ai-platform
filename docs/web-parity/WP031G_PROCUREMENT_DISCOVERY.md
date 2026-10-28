# WP-031G — Procurement Integration — Discovery e decisão arquitetural

**Data:** 20/09/2026

**Branch:** `feat/web-parity-v1-total-original-migration`

**PR:** #118 — OPEN/DRAFT
**Estado:** IMPLEMENTADO — AGUARDANDO CI

## CURRENT comprovado antes da mudança

A descoberta dirigida no tree pós-WP-031F não localizou autoridade materializada de fornecedor, ordem de compra ou recebimento físico. Existiam:

- `Permissao.COMPRA_APROVAR`, sem domínio ou persistência consumidora;
- documento inbound oficial, itens e XML autoritativo do WP-031E;
- Smart Fiscal Intake preliminar do WP-031F, explicitamente sem efeitos operacionais;
- ledger append-only de estoque em `core/estoque`, com idempotência, CAS, auditoria e eventos;
- nenhuma tabela canônica de supplier, purchase order, receipt, product binding ou acquisition cost.

## Decisão

Foi criada uma única autoridade de Procurement V1 em `core/procurement`, com adapter durável em `infra/procurement`. Não foi criado segundo ledger de estoque, segunda autoridade fiscal nem qualquer ledger financeiro.

Autoridades preservadas:

1. XML/DF-e oficial: verdade documental fiscal.
2. Confirmação humana: verdade sobre quantidade e condição física recebida.
3. Procurement: fornecedor, ordem, matching e recebimento.
4. `core/estoque`: única autoridade de saldo e movimentos.
5. Serviço determinístico: decide efeitos; IA não participa da confirmação.

## Boundary e fluxo

`Pedido aprovado → NF-e oficial → confirmação física → three-way match → recebimento persistido → entrada idempotente no estoque → histórico governado de custo`

- NF-e isolada nunca movimenta estoque.
- Divergência ou rejeição nunca movimenta estoque.
- `HOMOLOGATION` persiste e valida Procurement, mas nunca altera saldo operacional.
- Somente a partição fiscal `PRODUCTION` pode produzir efeito no ledger de estoque.
- Replay com mesmo payload é idempotente; mesma chave com payload diferente falha fechado.
- Atualização de custo é histórico append-only com política explícita; catálogo/custo corrente não é sobrescrito silenciosamente.
- Nenhuma obrigação financeira é criada no WP-031G.

## Persistência e migration

Migration aditiva `0047_fiscal_procurement_integration_v1`:

- `procurement_suppliers_v1`;
- `procurement_purchase_orders_v1`;
- `procurement_receipts_v1`;
- `procurement_product_bindings_v1`;
- `procurement_acquisition_costs_v1`.

Todas as identidades persistentes são particionadas por `tenant_id + unit_id + environment`. Fresh install e upgrade usam a mesma migration oficial; nenhuma migration histórica foi reescrita.

## RBAC, auditoria e eventos

- aprovação/cadastro/matching: `compra.aprovar`;
- visualização: `fiscal.compras.visualizar`;
- recebimento/devolução: `fiscal.compras.receber`;
- menor privilégio e escopo tenant/unidade falham fechado;
- recebimentos produzem auditoria sanitizada e eventos `fiscal.recebimento.confirmado`, `fiscal.divergencia.detectada` ou `fiscal.recebimento.rejeitado`;
- estoque produz seus eventos canônicos, inclusive `estoque.devolvido_fornecedor`.

## Riscos e rollback

- A migration é somente aditiva. Rollback operacional é desabilitar o wiring do boundary; nenhuma tabela histórica precisa ser reescrita.
- Provider/SEFAZ, financeiro, Web/UX, Cognitive Fiscal, Visual Premium, merge e deploy permanecem fora deste bloco.
- O efeito de estoque requer uma `Session`/Unit of Work compartilhada no adapter SQL para atomicidade; o adapter foi desenhado para participar da mesma sessão do ledger canônico.

## Fitness exigido

- completo, parcial, divergente e rejeitado;
- replay igual e replay divergente;
- concorrência;
- isolamento tenant/unidade/ambiente;
- entrada única em estoque;
- homologação sem contaminação de saldo;
- devolução ao fornecedor;
- migration manifest e schema baseline;
- regressão fiscal, estoque, RBAC e suíte integral.
