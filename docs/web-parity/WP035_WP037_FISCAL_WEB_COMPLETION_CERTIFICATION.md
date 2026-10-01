# WP-035 → WP-037 — Fiscal Web Completion

**Data:** 01/10/2026
**PR:** #173
**Branch:** `feat/kordena-wp035-wp037-fiscal-web-completion`
**Estado:** IMPLEMENTED_UNCERTIFIED

## Gap reconciliado

A auditoria produto × SaaS identificou que o WP-031 Fiscal havia sido certificado internamente quanto às autoridades e capacidades do backend, porém a superfície Web atual ainda não expunha toda a operação fiscal de entrada, procurement e bridge financeiro-fiscal construída no produto.

Esta entrega não cria novo domínio fiscal e não substitui o Fiscal V1. Ela migra capacidades já existentes para a Central Fiscal Web.

## WP-035 — Fiscal Inbox / Smart Intake / Manifestação Web

A superfície passa a oferecer:

- upload de XML/DF-e oficial;
- captura preliminar por PDF/imagem/câmera com Gemini;
- reconciliação da captura preliminar com chave oficial;
- consulta ao provider fiscal configurado;
- manifestação canônica do destinatário.

IA permanece evidência preliminar. XML/DF-e oficial continua autoritativo.

## WP-036 — Procurement Fiscal / Compras / Recebimento Web

A superfície passa a oferecer:

- fornecedores;
- vínculo código do fornecedor → insumo Kordena;
- pedido de compra;
- aprovação;
- recebimento físico;
- devolução ao fornecedor;
- visão de procurement.

A implementação reutiliza `ServicoProcurement`, repositórios canônicos, ledger de estoque e sessão tenant/unidade.

## WP-037 — Bridge Financeiro-Fiscal / Crédito Tributário Web

A superfície passa a oferecer:

- criação de obrigação financeira a partir do recebimento;
- ajuste por devolução/cancelamento;
- decisão versionada de crédito tributário.

A obrigação não executa pagamento. As mutações financeiro-tributárias são fixadas na partição de produção no backend e exigem permissões específicas.

## Segurança e autoridade

- tenant/unidade não são aceitos dos payloads do browser;
- escopo vem da sessão autenticada;
- RBAC é revalidado no backend;
- idempotência é obrigatória nas mutações sujeitas a retry;
- nenhuma homologação SEFAZ/provider externa é presumida;
- NFCore permanece fora do escopo;
- nenhuma segunda autoridade de estoque, compras, financeiro ou fiscal é criada.

## Gate

Workflow dedicado: `Web Parity WP035-WP037 Fiscal Web Completion`.

O estado só poderá ser promovido a `CERTIFIED` depois de:

- contrato HTTP dirigido verde;
- regressão fiscal/procurement verde;
- State Ledger verde;
- contrato Web verde;
- regressão Node verde;
- ESLint verde;
- TypeScript verde;
- Next build verde;
- diff check verde;
- demais gates obrigatórios da PR verdes.
