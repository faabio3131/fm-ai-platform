# Kordena V1 — Ciclo WP-029 + WP-030

## Estado do ciclo

- PR oficial: **#118 — OPEN / DRAFT / NÃO MERGEADA**.
- Branch: `feat/web-parity-v1-total-original-migration`.
- Base preservada: `731f6db17ec46a8173d10dd29897c8c623e52f16`.
- HEAD funcional certificado do WP-029: `9d082a397d6fa0b08ed67e08f80ec818167961a8`.
- HEAD funcional certificado do WP-030: `c74595637deb6e31a578e95975445d34064a6b07`.
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

### Evidência de certificação WP-029

Workflow `Web Parity WP028-WP030 Gate`, run `34905146574`:

- `py_compile`: PASS;
- Ruff: PASS;
- mypy: PASS;
- matriz Python WP-028 + WP-029 + regressões de pagamentos/PagBank/PIX: **54 passed, 0 failed**;
- ESLint: PASS;
- TypeScript `tsc --noEmit`: PASS;
- Next.js production build: PASS;
- `git diff --check`: PASS.

WP-029 está certificado como **MIGRADO / 100% VERDE**. Nenhuma promoção para merge, deploy ou produção foi feita.

---

## WP-030 — Cardápio Digital público / Autosserviço

**Status: MIGRADO / CONCLUÍDO / 100% VERDE.**

### Decisão de produto que removeu o bloqueio

O proprietário definiu que cliente, matriz, filial e unidade são dados configuráveis do SaaS e jamais podem exigir mudança de código por contratação. Um cliente pode possuir uma única unidade, matriz + filiais ou múltiplas unidades independentes; a publicação pública deve ser administrável pela própria plataforma.

A decisão arquitetural resultante foi:

- cada unidade possui uma identidade pública própria;
- `public_id` opaco, estável e gerado pelo servidor é a autoridade pública;
- `slug` é legível e configurável, mas não é autoridade de segurança;
- estado `publicada` controla disponibilidade pública;
- `(tenant_id, unidade_id)` possui uma única identidade pública;
- navegador nunca escolhe `tenant_id` ou `unidade_id` internos como autoridade;
- headers `X-Tenant-ID`/`X-Unit-ID` enviados pelo visitante não alteram o escopo resolvido;
- o servidor resolve `public_id` -> tenant/unidade confiáveis e só então acessa catálogo/checkout canônicos.

### Persistência pública dedicada

A solução intermediária baseada em JSON genérico de parâmetros operacionais foi descartada antes da certificação por não ser suficientemente robusta para escala multi-tenant. A solução final usa persistência dedicada e indexada:

- `infra/cardapio_publico/modelos_orm.py`;
- `infra/cardapio_publico/repositorio_sqlalchemy.py`;
- migration oficial `0041` em `migrations/cardapio_publico_identity_v1.py`;
- integração ao runner/fingerprint oficial de migrations.

Invariantes preservadas:

- `public_id` globalmente único;
- `(tenant_id, unidade_id)` único;
- concorrência otimista por versão;
- nenhuma exposição pública de IDs internos.

### Superfície administrativa por unidade

A gestão do link foi integrada à área existente **Empresa / Matriz / Filiais / Unidades**, sem criar segunda administração:

- `web/src/features/backoffice/empresa/components/CardapioPublicoAdmin.tsx`;
- integração em `EmpresaWorkspace.tsx`;
- GET/PUT administrativo em `http_api/cardapio_publico.py`;
- sessão assinada + `admin.acessar` + step-up administrativo preservados.

O proprietário pode selecionar cada matriz/filial/unidade, configurar o slug, publicar/despublicar e copiar/abrir o link público sem intervenção técnica ou mudança de código.

### Cardápio público e isolamento

A jornada anônima usa:

- rota Next.js `/cardapio/{publicId}/{slug}`;
- `CardapioPublicoWorkspace.tsx`;
- `cardapio-publico-api.ts`;
- façade HTTP pública dedicada;
- `CatalogoDeliverySQLAlchemy` como projeção canônica de catálogo/disponibilidade.

A rota `/cardapio/...` é a única exceção pública adicionada aos guards globais; as demais rotas continuam fail-closed.

A resposta pública expõe somente dados necessários ao consumidor. `tenant_id` e `unidade_id` não são serializados.

### Autosserviço sobre o checkout canônico

O Cardápio Público não criou segundo Pedido, Checkout, Pagamento ou Catálogo.

O autosserviço entra pela fronteira canônica:

`ComandoCheckoutV1 -> executar_checkout_v1`

O navegador envia apenas:

- `public_id` pela URL;
- produtos e quantidades;
- método de pagamento;
- chave de idempotência.

Tenant, unidade e preços são reconstruídos pelo servidor. O preço do browser não é autoridade. O contexto técnico público é estreito e só é criado depois da resolução confiável da unidade.

### Testes de segurança e escala SaaS

O contrato `tests/api/test_cardapio_publico_http_contract.py` cobre, entre outros:

- sessão + step-up na administração;
- identidade pública estável;
- slug configurável;
- publicação/despublicação;
- concorrência otimista;
- identificador inválido sem vazamento;
- tentativa de spoofing de tenant/unidade;
- matriz + filial no mesmo tenant;
- segundo cliente independente no mesmo banco;
- vínculos explícitos unidade -> loja legada fail-closed;
- ausência de herança indevida de catálogo entre unidades;
- checkout público no escopo canônico;
- preço canônico do servidor;
- idempotência do checkout.

### Evidência de certificação final WP-030

HEAD funcional certificado:

`c74595637deb6e31a578e95975445d34064a6b07`

Workflow `Web Parity WP028-WP030 Gate`, run `34990379750`:

- instalação Python: PASS;
- `py_compile`: PASS;
- Ruff: PASS;
- mypy: PASS;
- matriz Python WP-028/WP-029/WP-030 + regressões financeiras: **61 passed, 0 failed**;
- instalação Web: PASS;
- ESLint: PASS;
- TypeScript: PASS;
- Next.js production build: PASS;
- `git diff --check`: PASS.

No mesmo HEAD, os quatro workflows obrigatórios concluíram **SUCCESS**:

- `Web Parity WP028-WP030 Gate`;
- `Commercial Runtime Readiness V1`;
- `PR Superseded Runs Cleanup`;
- `Assistente Fase 4 Gate V1`.

### Decisão de fechamento

WP-030 está certificado como:

**MIGRADO / CONCLUÍDO / 100% VERDE.**

Não houve merge, deploy, produção, force push ou rebase destrutivo.

---

## Auditoria retrospectiva de documentação

A revisão realizada após o WP-030 encontrou dois tipos distintos de pendência histórica.

### 1. Status documentais atrasados, já comprovadamente migrados

O Inventário Mestre ainda preservava estados antigos para capacidades que documentos posteriores/checklist já registram como migradas. Devem ser reconciliadas no inventário/checklist atual:

- WP-024 — Parâmetros Financeiros;
- WP-025 — Impressão Operacional;
- WP-026 — Integrações e Credenciais;
- WP-027 — Assistente de Atendimento;
- WP-028 — Gerente IA;
- WP-029 — Pagamentos / PIX / Provedores;
- WP-030 — Cardápio Digital público / Autosserviço.

### 2. Implementação presente, mas certificação integrada ainda legitimamente pendente

Não devem ser promovidos apenas por reconciliação documental:

- WP-010 — Delivery Próprio;
- WP-011 — Expedição / Entrega;
- WP-013 — Catálogo administrativo básico;
- WP-014 — Engenharia de Cardápio + Ficha Técnica;
- WP-015 — Estoque / Almoxarifado / Validades;
- WP-016 — CRM / Clientes / Cashback;
- WP-017 — Marketing / Resgate / Campanhas;
- WP-018 — Dashboard Financeiro / Indicadores;
- WP-019 — AI FinOps;
- WP-020 — Área Proprietário / Backoffice;
- WP-022 — Empresa / Matriz / Filiais / Unidades.

Os próprios documentos desses ciclos registram ausência de Smoke Mestre/certificação integrada. Portanto a pendência é real e exige um ciclo específico de certificação; não é apenas texto desatualizado.

### 3. Capacidades ainda não implementadas no escopo Web

- WP-008 — Atendimento do Garçom;
- WP-012 — Marketplaces / pedidos externos;
- WP-032 — Notificações Internas, obrigatória para V1.0;
- WP-033 — Auditoria / Histórico administrativo.

WP-031 — Fiscal / NFC-e / SAT permanece **BACKLOG FUTURO / FORA DA MIGRAÇÃO CONSERVATIVA WEB V1**, sem implementação funcional autorizada.

## No-go preservado

- PR #118 permanece Draft e não mergeada;
- sem deploy/produção;
- sem force push/rebase/reset destrutivo;
- sem segredo real no Git;
- sem promoção artificial de WPs que ainda aguardam certificação integrada;
- WP-031 Fiscal permanece backlog futuro.