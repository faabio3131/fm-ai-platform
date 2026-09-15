# WP-010 + WP-011 — Certificação Integrada

Data da certificação: 2026-09-15  
Branch: `feat/web-parity-v1-total-original-migration`  
Base preservada: `feat/web-parity-v1-wp010-wp011-delivery-entrega`  
SHA técnico certificado antes deste registro: `b93a7867d9069937a20222d38f942b81adfab0bd`

## Status

- WP-010 — Delivery Próprio: **MIGRADO / CERTIFICADO / 100% VERDE**.
- WP-011 — Expedição/Entrega: **MIGRADO / CERTIFICADO / 100% VERDE**.

Esta certificação não cria domínio paralelo. O fluxo continua reutilizando as autoridades canônicas já existentes de pedido, checkout, pagamento, KDS, expedição e entrega.

## Correções realizadas durante a certificação

1. A compatibilidade comercial de CRM necessária à regressão total foi preservada/restaurada no HEAD corrente sem substituir o hardening novo do sandbox CRM.
2. `application/cardapio_publico.py` deixou de possuir `commit/rollback` cru de `Session` na configuração da publicação e passou a usar `UnitOfWorkV1`, restaurando o ownership transacional canônico.
3. `scripts/wire_product_legacy_store_compat_v1.py` passou a reconhecer também o estado moderno de importação via `AplicacaoImportacaoCardapioGeminiV1`/`application_importacao_gemini.importar`, mantendo o patch histórico idempotente e evitando downgrade da arquitetura moderna.

Nenhum teste foi removido, afrouxado ou convertido em exceção de baseline para obter verde.

## Evidência do gate WP-010/WP-011

Workflow: `Web Parity Phase 1 WP010-WP011 Certification`  
Run: `35014317666`  
Job: `104533790861`

Resultado integral: **SUCCESS**.

- Compile da superfície canônica WP-010/WP-011: PASS.
- Ruff: PASS (`All checks passed!`).
- mypy: PASS (`Success: no issues found in 28 source files`).
- Matriz HTTP + integração Delivery/Entrega/KDS/Central de Pedidos: **62 passed**.
- Regressão Python completa: **1491 passed, 5 skipped**.
- Playwright Delivery: **3 passed**.
- Playwright Expedição/Entrega: **3 passed**.
- `git diff --check`: PASS.

### Jornadas de navegador comprovadas

Delivery:

1. cliente autenticado conclui jornada própria usando checkout e entrega canônicos;
2. endereço CRM validado fora da área falha fechado sem confirmar o pedido;
3. pagamento na entrega permanece cancelável e reconcilia pedido e logística.

Expedição/Entrega:

1. expedição conclui checklist e atribui entregador sem acessar financeiro;
2. entregador conclui custódia somente quando o financeiro está resolvido;
3. conclusão da entrega não transforma `aguardando_entrega` em pagamento confirmado.

## Evidência transversal no mesmo SHA técnico

Também concluíram com sucesso no SHA `b93a7867d9069937a20222d38f942b81adfab0bd`:

- `Commercial Runtime Readiness V1` — run `35014317696`.
- `PR Superseded Runs Cleanup` — run `35014317679`.
- `Assistente Fase 4 Gate V1` — run `35014317814`.
- `Web Parity WP028-WP030 Gate` — run `35014317766`.

## Governança

- PR #118 permanece OPEN/DRAFT.
- Nenhum merge foi realizado.
- Nenhum deploy foi realizado.
- Nenhuma V2 foi iniciada.
- Não há bloqueio funcional residual conhecido em WP-010 ou WP-011 após esta certificação.

## Próxima etapa autorizada

Com WP-010 e WP-011 certificados, a Fase 1 pode avançar para a auditoria/certificação de WP-013 e WP-014. A reconciliação consolidada do inventário mestre permanece prevista também para a fase documental final do Prompt Mestre.