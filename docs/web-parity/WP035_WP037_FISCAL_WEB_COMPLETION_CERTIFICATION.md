# WP-035 → WP-037 — Fiscal Web Completion

**Data:** 01/10/2026
**PR:** #173
**Branch:** `feat/kordena-wp035-wp037-fiscal-web-completion`
**Estado:** CERTIFIED

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

## Certificação final

**HEAD funcional certificado:** `71fd559170c8efa3952232d6b0245d317bf3dfec`

**Workflow dedicado:** `Web Parity WP035-WP037 Fiscal Web Completion`
**Run:** `36896722715` — SUCCESS

Matriz dirigida comprovada:

- compile Python — PASS;
- Ruff — PASS;
- contrato HTTP WP-035→WP-037 — PASS;
- regressão fiscal/procurement — PASS;
- State Ledger — PASS;
- contrato Web WP-035→WP-037 — PASS;
- regressão Node completa — PASS;
- ESLint — PASS;
- TypeScript — PASS;
- Next production build — PASS;
- diff whitespace — PASS.

Matriz ampliada da PR no mesmo HEAD: **23/23 workflows GitHub Actions SUCCESS**, incluindo WP-031 Master, WP-031E→L, KCA-15/16/17, KF-02, Visual Premium, Commercial Runtime, State Ledger, WP-022 e WP-034.

**Vercel:** SUCCESS no mesmo HEAD.

Conclusão: WP-035, WP-036 e WP-037 estão certificados internamente como paridade Web do Fiscal V1. Esta certificação não declara homologação externa SEFAZ/provider nem inicia NFCore/cutover.
