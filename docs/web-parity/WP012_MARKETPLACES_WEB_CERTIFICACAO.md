# WP-012 — Certificação técnica Marketplaces Web

**Data:** 18/09/2026  
**Branch:** `feat/web-parity-v1-total-original-migration`  
**PR:** #118  
**SHA certificado:** `e4ce2c1e2e315811425535c5ca74b5a56570050b`  
**Workflow:** `Web Parity WP012 Marketplaces`  
**Run:** `35369209616` — **SUCCESS**

## Escopo certificado

A superfície Web de marketplaces foi integrada à Central de Pedidos/Pedido autoritativos sem criar segunda máquina de estados. A API dedicada usa o prefixo `/v1/marketplaces`; a experiência operacional permanece centralizada em `/pedidos`.

## Autoridades reutilizadas

- `core/marketplaces` para contratos/adapters e sincronização.
- `core/central_pedidos` e Pedido canônico para estado operacional.
- Outbox, Inbox/DLQ, auditoria e `UnitOfWorkV1` para durabilidade e ownership transacional.
- Control Plane de integrações + cofre de segredos para configuração e credenciais.

## Persistência e migration

A migration `0042_marketplace_orders_web_v1` registra a proveniência externa sem substituir o Pedido interno. O schema baseline e as expectativas oficiais de migration foram reconciliados e passaram no gate integral.

## Segurança e isolamento

- sessão assinada e escopo tenant/unidade;
- leitura governada por permissões de Pedido;
- sincronização sensível exige gerenciamento de integração e step-up administrativo;
- identidade técnica do marketplace possui somente `PEDIDO_CRIAR`, `PEDIDO_ALTERAR` e `PEDIDO_CANCELAR`;
- transaction ownership preservado em `UnitOfWorkV1`.

## Resultado do gate

No run `35369209616` passaram: Compile, Ruff, mypy, Migration manifest, matriz direcionada WP-012, regressão Python completa, ESLint, TypeScript, testes Web, Next production build e diff whitespace gate.

## Limites da certificação

Esta evidência certifica a implementação técnica interna Web/HTTP e sua integração às autoridades canônicas. **Não declara homologação real externa** de iFood, Keeta, 99Food ou qualquer outro provider. Operação de rede permanece fail-closed até configuração habilitada, homologação e evidência real correspondentes.
