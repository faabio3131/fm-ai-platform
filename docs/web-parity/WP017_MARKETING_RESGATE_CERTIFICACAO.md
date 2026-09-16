# WP-017 — Marketing / Resgate / Campanhas — Certificação

## Estado

**MIGRADO / CERTIFICADO / 100% VERDE**

## Governança

- Repositório: `faabio3131/fm-ai-platform`
- Branch: `feat/web-parity-v1-total-original-migration`
- PR: `#118` — permanece OPEN/DRAFT
- Base preservada: `feat/web-parity-v1-wp010-wp011-delivery-entrega`
- Base SHA: `731f6db17ec46a8173d10dd29897c8c623e52f16`
- HEAD técnico certificado antes deste registro: `f059abe30e69cc1981188a76c040b99dba59874a`
- Workflow: `Web Parity Phase 1 WP017 Certification`
- Run: `35038548147`
- Job: `104613031804`

Nenhum merge, deploy, force push, rebase destrutivo, alteração da `main` ou início de V2 foi realizado neste ciclo.

## Autoridades canônicas preservadas

A certificação preserva e reutiliza as autoridades existentes:

- `application/crm_marketing_comercial.py`;
- `core/crm` e `ServicoCRM`;
- `infra/crm`;
- `LeitorConsentimentosMarketingSQLAlchemy`;
- `CanalMarketing.WHATSAPP`;
- `FinalidadeMarketing.PROMOCOES`;
- transporte WhatsApp comercial existente;
- Outbox V1 persistente já existente em `infra/eventos`;
- `UnitOfWorkV1` como owner transacional canônico;
- `http_api/crm.py`;
- `/admin/crm` e `web/src/features/backoffice/crm`.

Não foi criado segundo CRM, segunda campanha, segunda infraestrutura de consentimento, segunda outbox, segunda sessão, segunda identidade ou nova tabela exclusiva de marketing.

## Gap funcional encontrado

A auditoria encontrou um gap real de idempotência no efeito externo.

O resgate já gerava uma chave diária determinística (`crm-resgate-{legacy_cliente_id}-{data}`), porém o transporte Meta/Graph não oferece uma garantia oficial que torne seguro repetir automaticamente o mesmo POST apenas porque a aplicação reutilizou a mesma chave local. Portanto, após restart, concorrência ou resultado externo incerto, a chave sozinha não era prova suficiente de que um segundo POST seria bloqueado.

A correção foi feita sem arquitetura paralela:

1. a Outbox V1 existente passou a ser reutilizada como ledger durável do efeito externo de marketing;
2. a reserva é persistida por `(tenant_id, unidade_id, idempotency_key)` antes do POST externo;
3. a chave de ledger é derivada da chave de idempotência de marketing e permanece escopada por tenant/unidade;
4. replay de um envio já concluído não chama novamente o transporte e retorna resultado idempotente;
5. replay de uma reserva cujo resultado externo ficou incerto também não repete automaticamente o POST;
6. divergência semântica sob a mesma chave falha fechado;
7. em sucesso, a reserva é marcada como concluída e pode registrar o `mensagem_id` seguro retornado pelo transporte.

Esse desenho implementa proteção local **at-most-once** para o efeito externo sem alegar exactly-once da Meta.

## Ownership transacional

A primeira implementação funcional colocou `commit/rollback` diretamente no wrapper de infraestrutura. A regressão global bloqueou corretamente essa forma através de `tests/fitness/test_af03_transaction_ownership.py`.

A correção final preservou o fitness gate sem allowlist nova:

- `infra/crm/marketing_idempotencia.py` não é owner de transação;
- a camada de aplicação adota a sessão via `UnitOfWorkV1.adotar_session(...)`;
- `uow.commit()` / `uow.rollback()` permanecem na fronteira canônica de aplicação;
- a reserva-before-POST continua garantida.

Nenhum teste de ownership foi enfraquecido, removido ou convertido em exceção.

## Consentimento e segurança preservados

A cadeia certificada continua exigindo:

- mapping CRM ↔ cliente legado no mesmo tenant/unidade;
- consentimento vigente para `WHATSAPP` + `PROMOCOES` antes do transporte;
- bloqueio quando não há consentimento;
- bloqueio quando uma revogação mais recente existe;
- sessão assinada como autoridade de tenant/unidade;
- headers `X-Tenant-ID` / `X-Unit-ID` incapazes de ampliar escopo;
- `CLIENTE_VISUALIZAR` + `CAMPANHA_CRIAR` na preparação;
- `CLIENTE_VISUALIZAR` + `CAMPANHA_CRIAR` + `CAMPANHA_APROVAR` no despacho;
- `ADMIN_ACESSAR` + step-up ativo para mutação via sessão Web;
- correlação preservada;
- falha fechada sem mapping ou autoridade válida.

## Jornadas certificadas

A matriz cobre, entre outros pontos:

- seleção de clientes inativos no escopo da unidade;
- corte temporal original e status `Inativo`;
- sugestão Gemini;
- fallback quando Gemini retorna vazio, inválido ou falha;
- ausência de chamada ao provider quando Gemini está desabilitado;
- despacho por WhatsApp com consentimento vigente;
- bloqueio sem consentimento;
- bloqueio após revogação;
- campanha diária determinística;
- chave diária determinística;
- replay do mesmo despacho sem segundo transporte;
- resultado externo incerto sem retry automático perigoso;
- isolamento tenant/unidade;
- composição única entre Streamlit legado, HTTP e application boundary;
- reutilização da rota `/admin/crm`, sem segunda rota CRM.

## Gate final — HEAD técnico `f059abe30e69cc1981188a76c040b99dba59874a`

Workflow `Web Parity Phase 1 WP017 Certification`, run `35038548147`, job `104613031804`: **SUCCESS**.

- Compile: **PASS**.
- Ruff: **PASS** — `All checks passed!`.
- mypy: **PASS** — `Success: no issues found in 4 source files`.
- Matriz direcionada CRM Marketing/Resgate: **22 passed / 0 failed**, 20 warnings.
- Regressão Python completa: **1506 passed / 5 skipped / 0 failed**, 99 warnings, em 184.49s.
- ESLint WP-017: **PASS**.
- TypeScript `npx tsc --noEmit`: **PASS**.
- Backoffice navigation: **3 passed / 0 failed**.
- Next production build: **PASS**.
- rota `/admin/crm` presente no build: **PASS**.
- `git diff --check`: **PASS**.

## Histórico das correções deste gate

- `b45c73f122194eaa858dd1cf6462607d1066b98a` — adicionou proteção durável de replay reutilizando Outbox V1 e os testes funcionais correspondentes;
- `e0d9741b75fc41141a7f04a29622ade7f0b8a5b0` — correção exclusivamente de formatação exigida pelo Ruff;
- `f059abe30e69cc1981188a76c040b99dba59874a` — moveu ownership transacional para `UnitOfWorkV1`, preservando o gate AF03 e a reserva-before-POST.

## Limitações deliberadas

- Não há promessa de exactly-once do provider externo.
- Reserva com resultado externo incerto permanece bloqueada para reenvio automático; eventual reconciliação manual/operacional futura deve ser explicitamente governada.
- Nenhum envio real de WhatsApp é executado nos testes.
- Nenhuma nova campanha ou automação promocional além do comportamento V1 foi criada.
- Nenhum WP posterior foi iniciado nesta certificação.

## Conclusão

WP-017 está **MIGRADO / CERTIFICADO / 100% VERDE** no HEAD técnico acima.

A documentação mestre deve refletir que WP-013, WP-014, WP-015, WP-016 e WP-017 já possuem evidência formal de certificação. WP-018 e blocos posteriores permanecem independentes e não são promovidos por este documento.

Após o commit documental, o HEAD resultante deve ser recertificado pelo workflow WP-017 antes do encerramento definitivo deste gate.