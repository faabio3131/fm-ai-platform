# Kordena V1 — Ciclo WP-029 + WP-030

## Estado do ciclo

- PR oficial: **#118 — OPEN / DRAFT / NÃO MERGEADA**.
- Branch: `feat/web-parity-v1-total-original-migration`.
- Base preservada: `731f6db17ec46a8173d10dd29897c8c623e52f16`.
- HEAD funcional certificado do WP-029: `9d082a397d6fa0b08ed67e08f80ec818167961a8`.
- Regra de avanço: nenhum WP seguinte começa antes de o atual estar literalmente 100% verde.

## WP-029 — Pagamentos / PIX / Provedores

**Status: MIGRADO / 100% VERDE.**

### Autoridades canônicas preservadas

A migração Web não criou segundo checkout, segundo fluxo PIX, segundo webhook nem segundo ledger. A superfície nova reutiliza:

- `core/pagamentos/*` para domínio, ledger append-only, idempotência, concorrência e modelos financeiros;
- `application/pagbank.py` para criação/processamento do PIX PagBank;
- `application/pagbank_reconciliacao.py` para reconciliação autenticada com o provedor;
- `infra/pagamentos/pagbank_runtime.py` para resolução tenant/unidade da referência de credencial sem devolver o segredo;
- checkout/pagamento operacional já existente no PDV.

### Superfície Web entregue

- rota Next.js: `/pagamentos`;
- façade HTTP session-aware em `http_api/pagamentos_web.py`;
- Application Web em `application/pagamentos_web.py`;
- cliente Web em `web/src/features/pagamentos/services/pagamentos-api.ts`;
- workspace em `web/src/features/pagamentos/components/PagamentosWorkspace.tsx`;
- registro no Shell sem ampliar privilégios;
- contrato HTTP dedicado em `tests/api/test_pagamentos_web_http_contract.py`.

A consulta exige `financeiro.visualizar`. A reconciliação exige adicionalmente `pagamento.confirmar`. Tenant e unidade vêm da sessão assinada; `X-Tenant-ID` e `X-Unit-ID` não substituem o escopo da sessão. Segredos do PagBank não são serializados para a Web.

### Evidência de certificação

Workflow `Web Parity WP028-WP030 Gate`, run `34905146574`, job `wp028-wp029`:

- `py_compile`: PASS;
- Ruff: PASS;
- mypy: PASS — 4 arquivos sem issues;
- matriz Python WP-028 + WP-029 + regressões de pagamentos/PagBank/PIX: **54 passed, 0 failed**;
- ESLint: PASS;
- TypeScript `tsc --noEmit`: PASS;
- Next.js production build: PASS;
- `git diff --check`: PASS;
- rota `/pagamentos` presente no build de produção.

No mesmo HEAD, os workflows obrigatórios associados à PR também concluíram com sucesso:

- Commercial Runtime Readiness V1: SUCCESS;
- Assistente Fase 4 Gate V1: SUCCESS;
- PR Superseded Runs Cleanup: SUCCESS;
- Web Parity WP028-WP030 Gate: SUCCESS.

### Decisão de fechamento

WP-029 está certificado como **MIGRADO / 100% VERDE** no HEAD funcional `9d082a397d6fa0b08ed67e08f80ec818167961a8`. Nenhuma promoção para merge, deploy ou produção foi feita.

## WP-030 — Cardápio Digital público / Autosserviço

**Status atual: BLOQUEADO POR DECISÃO DE PRODUTO/SEGURANÇA SOBRE IDENTIDADE PÚBLICA DO ESTABELECIMENTO/UNIDADE. Nenhuma implementação funcional foi iniciada.**

Escopo constitucional já registrado:

- obrigatório para V1.0;
- reutilizar Catálogo, Pedido/Checkout, Delivery, Central de Pedidos e Pagamentos;
- não criar segundo catálogo, pedido, checkout ou pagamento;
- não introduzir domínio fiscal;
- a superfície pública não pode confiar em tenant/unidade arbitrários enviados pelo navegador.

### Auditoria de autoridade realizada

A auditoria posterior ao fechamento verde do WP-029 confirmou:

1. `http_api/catalogo.py` é uma superfície autenticada. As leituras de produtos/categorias resolvem identidade pela sessão assinada ou, apenas por compatibilidade legada/M2M, por Basic + `X-Tenant-ID` + `X-Unit-ID`. Portanto essa fronteira não é uma autoridade pública anônima reutilizável.
2. `http_api/delivery.py` também exige identidade operacional autenticada. O próprio boundary documenta que tenant/unidade nunca são aceitos livremente e vêm da sessão assinada ou Basic legado.
3. `application/delivery_contexto_comercial.py` deriva tenant/unidade exclusivamente da `IdentidadeUsuario` autenticada antes de consultar cliente, endereço, catálogo e política de entrega.
4. `infra/delivery/catalogo_sqlalchemy.py` já fornece a projeção canônica de catálogo/disponibilidade por tenant/unidade e deve ser reutilizada, mas pressupõe que o escopo confiável já tenha sido resolvido.
5. `application/checkout.py` é a autoridade canônica de checkout e exige `ContextoExecucao` cujo tenant/unidade coincidem com o pedido. Ele pode ser reutilizado por um futuro canal público somente depois que existir uma forma segura e auditável de resolver esse escopo.
6. `core/administracao/modelos.py` e `infra/administracao/modelos_orm.py` possuem `tenant_id`, `unidade_id` e `codigo` administrativo. O `codigo` é único apenas dentro do tenant; não existe nos modelos um `slug_publico`, `public_token`, domínio/host público ou outro identificador global explicitamente classificado como autoridade pública.
7. O Streamlit legado (`app.py`) exige autenticação antes das superfícies operacionais; não há nele jornada pública de autosserviço que possa ser migrada mecanicamente.
8. O HTTP canônico possui webhooks externos que incluem tenant/unidade na URL, mas a confiança é estabelecida por credenciais/assinaturas específicas do provedor (Meta/WhatsApp e PagBank). Esses mecanismos não constituem um resolvedor público genérico reutilizável para Cardápio Digital.
9. O inventário mestre continua classificando WP-030 como `GAP HTTP/WEB/PÚBLICO` e manda reutilizar futuramente Catálogo, Pedido/Checkout, Delivery, Central de Pedidos e Pagamentos; não define qual identificador público seleciona o estabelecimento/unidade.
10. A árvore atual não contém módulo/rota dedicada de cardápio público nem autoridade explícita de `slug`/token público a ser preservada.

### Conclusão arquitetural

A regra de negócio posterior ao resolvedor está suficientemente definida e possui autoridades reutilizáveis. O bloqueio não é falta de código de catálogo/checkout: é a ausência de uma decisão canônica de **como um visitante anônimo seleciona uma unidade sem transformar IDs internos ou headers arbitrários em autoridade de escopo**.

Criar autonomamente um novo slug, token público, domínio por tenant, tabela de aliases ou outra política de resolução mudaria a arquitetura de exposição pública e a política de segurança. Isso está fora da autorização de correção técnica do ciclo.

Consequentemente, conforme a missão, a execução deve parar antes do código do WP-030 e solicitar decisão do proprietário. WP-031/WP-032/WP-033 não podem ser iniciados enquanto WP-030 não estiver concluído e 100% verde.

## No-go

- PR #118 permanece Draft e não mergeada;
- sem deploy/produção;
- sem force push/rebase/reset destrutivo;
- sem segredo real no Git;
- nenhum tenant/unidade interno será promovido silenciosamente a identificador público;
- WP-031 Fiscal permanece backlog futuro e não deve ser implementado por este ciclo.
