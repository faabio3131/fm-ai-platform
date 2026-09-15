# WP-016 — CRM / Clientes / Cashback — Certificação

## Estado

**MIGRADO / CERTIFICADO / 100% VERDE**

## Governança

- Repositório: `faabio3131/fm-ai-platform`
- Branch: `feat/web-parity-v1-total-original-migration`
- PR: `#118` — permanece OPEN/DRAFT
- Base da PR: `feat/web-parity-v1-wp010-wp011-delivery-entrega`
- Base SHA: `731f6db17ec46a8173d10dd29897c8c623e52f16`
- HEAD técnico certificado: `d0fe8480c58449c54024c2dbb1fd9ca6b8747746`
- Workflow: `Web Parity Phase 1 WP016 Certification`
- Run: `35035019313`
- Job: `104602071970`

Nenhum merge, deploy, force push, rebase destrutivo ou alteração da `main` foi realizado neste ciclo.

## Autoridade canônica preservada

A auditoria confirmou que o WP-016 reutiliza as autoridades existentes:

- `core/crm`
- `application/crm_cashback_comercial.py`
- `application/crm_cashback_transacoes.py`
- `infra/crm`
- `http_api/crm.py`
- ledger canônico de cashback
- mapping governado CRM ↔ cliente legado
- `web/src/features/backoffice/crm`

O ledger CRM permanece a autoridade econômica. A coluna legada `clientes.saldo_cashback` é apenas projeção de compatibilidade e nunca fallback de saldo.

## Gap encontrado e correção

O primeiro gate direcionado encontrou **16 PASS / 1 FAIL**. A falha estava somente no novo teste de contrato Web: ele assumia que `build_crm_router` era composto diretamente em `http_api/app.py`.

A composição real e canônica ocorre em `http_api/frontend_app.py`, que constrói o `build_http_app` e inclui `build_crm_router` reutilizando o mesmo `session_factory` e `auth_runtime`.

Correção aplicada:

- nenhum código funcional do CRM foi alterado;
- o teste foi corrigido para validar a composição real;
- as verificações de sessão, RBAC, `ADMIN_ACESSAR`, step-up, ledger, idempotência e boundary HTTP foram preservadas.

## Segurança certificada

A matriz existente + contrato Web certificam:

- sessão operacional autenticada;
- tenant/unidade derivados da identidade autenticada;
- spoofing de `X-Tenant-ID` / `X-Unit-ID` não amplia escopo;
- leitura exige `CLIENTE_VISUALIZAR`;
- crédito manual exige `CLIENTE_EDITAR`;
- mutação Web exige `ADMIN_ACESSAR`;
- mutação Web exige step-up administrativo ativo;
- cliente/cashback cross-unit falham fechado;
- ausência de mapping CRM/legado falha fechado;
- membership não é ampliada pela operação;
- saldo legado divergente não substitui o ledger canônico.

## Jornadas certificadas

- `GET /v1/crm/clientes`
- `GET /v1/crm/clientes/{cliente_id}/cashback`
- `POST /v1/crm/clientes/{cliente_id}/cashback/creditos`
- listagem CRM da unidade ativa
- consulta de saldo e histórico
- crédito manual governado
- `Idempotency-Key`
- replay sem duplicação de movimento
- projeção legada transacional do saldo final
- fail-closed sem mapping
- troca de unidade na superfície Web
- ausência de lógica financeira duplicada no React

## Gate final

No HEAD técnico `d0fe8480c58449c54024c2dbb1fd9ca6b8747746`:

- Compile: **PASS**
- Ruff: **PASS**
- mypy: **PASS** (`3 source files` sem issues)
- matriz direcionada CRM/Cashback: **17 PASS / 0 FAIL**
- regressão Python completa: **1505 PASS / 5 SKIP / 0 FAIL**
- warnings Python: `98` — sem falha nova
- ESLint CRM: **PASS**
- TypeScript `npx tsc --noEmit`: **PASS**
- Node/backoffice navigation: **3 PASS / 0 FAIL**
- Next production build: **PASS**
- rota `/admin/crm` presente no build: **PASS**
- `git diff --check`: **PASS**

## Limitações deliberadas

Este ciclo não cria segundo CRM, segundo ledger de cashback, segunda identidade, segunda sessão ou persistência paralela. O WP-017 (Marketing / Resgate / Campanhas) permanece uma certificação independente e deve respeitar consentimento, idempotência e transporte canônicos.

## Conclusão

WP-016 está **MIGRADO / CERTIFICADO / 100% VERDE**. O avanço para WP-017 só é permitido depois da recertificação do HEAD que contém este documento.