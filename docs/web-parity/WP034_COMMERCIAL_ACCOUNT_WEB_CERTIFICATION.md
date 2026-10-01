# WP-034 — Certificação Conta Comercial / Plano e Assinatura Web

**Data:** 01/10/2026  
**PR:** #172  
**Branch:** `feat/kordena-wp034-plano-assinatura-web`  
**HEAD funcional certificado:** `23c78e9cee8a375258a27140122bc0934e1206d1`  
**Workflow:** `Web Parity WP034 Commercial Account`  
**Run:** `36873075897` — **SUCCESS**

## Gap reconciliado

A auditoria produto × SaaS identificou que a linha KCA já possuía a autoridade comercial de:

- access/entitlement;
- catálogo versionado de planos e preços;
- assinatura;
- checkout provider-neutral;
- paywall e restauração de acesso;

porém o Kordena Web não possuía uma superfície dedicada para uma conta ativa consultar plano e assinatura. O paywall existia apenas no estado de acesso restrito.

## Migração Web

Foi adicionada a rota:

`/admin/assinatura`

A superfície reutiliza exclusivamente:

- `GET /v1/commercial/access`;
- `GET /v1/commercial/plans`;
- `GET /v1/commercial/subscription`;
- `POST /v1/commercial/checkout`.

A página apresenta entitlement, modo de acesso, assinatura atual, período contratado e catálogo publicado. Não existe preço, nome de plano ou entitlement hardcoded.

## Segurança e autoridade

- módulo restrito à área Proprietário por `admin.acessar`;
- `/admin` preserva o `AdminStepUpGuard`;
- tenant continua derivado da sessão autenticada;
- nenhuma regra comercial foi movida para React;
- nenhuma segunda autoridade de billing foi criada;
- Billing SaaS permanece separado de Pagamentos/PIX operacionais do estabelecimento;
- checkout só é habilitado nesta superfície quando o acesso operacional está restrito, evitando duplicidade de contratação enquanto o entitlement atual estiver válido;
- a tela não inventa cancelamento, confirmação financeira, mudança de plano ou ativação local.

## Gate certificado

No run `36873075897`:

- instalação Python: PASS;
- regressão HTTP comercial: PASS;
- State Ledger: PASS;
- instalação Web: PASS;
- contrato WP-034: PASS;
- regressão Node completa: PASS;
- ESLint: PASS;
- TypeScript: PASS;
- Next production build: PASS;
- diff whitespace: PASS.

## Limites preservados

Esta certificação não configura nem homologa provider de billing de produção e não executa cobrança real. O blocker externo de billing de produção permanece separado da conclusão funcional da superfície Web.

## Resultado

`WP-034 = CERTIFIED`

A capacidade que estava construída no backend/arquitetura KCA e ausente da Web passa a integrar explicitamente o inventário canônico do Kordena.
