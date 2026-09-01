# Fase 6 — Inventário Current → Target — PDV / Pedido / Pagamento / Estoque V1

**Data de abertura:** 01/09/2026  
**Base auditada:** `main` @ `64b99bec2be2d87d0f216302010d7b877cf1efd5`  
**Programa de recuperação:** Issue #62  
**Regra:** preservar patrimônio canônico já construído; corrigir composição/cutover, não reescrever domínio válido.

## 0. Checkpoints de execução

- F6-A fechada em `8ce3eba882d65af78822a35dae23c97e0e8ad628`: matriz 20/20 verde e reexecução extra do PR11 E2E principal verde.
- F6-B fechada em `c9a2a06fa68bb2404e0fd7b9dbbc058cd334af68`: gate dedicado + matriz 21/21 verdes.
- F6-C fechada em `f635495049657230391adc452d4571239b5b85b2`: gate dedicado + matriz transversal 22/22 verdes, sem falhas ou pendências.
- F6-D fechada em `db422035c2339f9a8b9743f5138149fc205168d4`: gate comercial dedicado + matriz transversal 25/25 verdes; Playwright comercial 3/3 (dinheiro, cartão presencial e Pix fail-closed); migration PostgreSQL `VARCHAR(30) -> VARCHAR(64)` comprovada; evidência pós-browser com 2 pedidos e 2 pagamentos canônicos persistidos.

## 1. Resultado executivo

A Fase 6 não começa do zero. Pedido, checkout, Pagamento/VendaFinanceira, ledger/reserva de Estoque, UoW, eventos/outbox/auditoria, reconciliação e o executor canônico do PDV já existem e possuem gates verdes.

F6-A removeu o bloqueio estrutural que impedia promoção governada fora do harness de teste. O canary comercial agora depende de autorização server-side, Active Execution Scope e terminal allowlisted. F6-B removeu o fallback econômico legado de total zero. F6-C conteve o adapter legado como projeção/ponte de catálogo, sem autoridade de baixa de estoque no caminho canônico.

A prova operacional do F6-D foi concluída em runtime comercial de staging, PostgreSQL e navegador real, sem `FM_AI_TEST_MODE`. O próximo bloco técnico previsto no inventário é o F6-E — Canary Readiness / Reconciliation / Rollback.

## 2. Current → Target

| Área | Current comprovado | Target Fase 6 | Ação |
|---|---|---|---|
| Pedido | `core/pedidos` autoritativo, CAS, idempotência, tenant/unidade | única autoridade de pedido do PDV | preservar |
| Checkout | `application/checkout.py` cria Pedido, obrigação e reserva na mesma UoW | fronteira canônica do PDV comercial | preservar |
| Pagamento | obrigação, confirmação, webhook, reconciliação e VendaFinanceira | autoridade financeira do PDV | preservar/compor |
| Estoque | ledger + reserva canônicos; consumo pertence ao início da produção | retirar autoridade econômica do checkout legado | preservar/completar cutover |
| PDV | executor canônico já é o executor público do canary | permitir canary comercial governado | F6-A |
| Rollout | canary comercial server-side allowlisted | prova E2E sem harness de teste | F6-D |
| Terminal | identidade server-side por `FM_AI_PDV_TERMINAL_ID` + allowlist | manter fail-closed | preservar |
| Venda legada | projeção compatível sem execução/baixa de estoque no caminho canônico | borda de compatibilidade, nunca autoridade | F6-C |
| Total zero | contrato canônico sem fallback econômico legado | manter idempotência/rollback | preservar |
| Pix | Control Plane seguro; provider externo depende de homologação | manter fail-closed por provider sem bloquear dinheiro/cartão | F6-D/F6-E |
| UI | `app.py` instancia executor canônico quando o modo resolve canary | mesma UI, sem toggle de autoridade pelo operador | preservar |
| Banco | runtime comercial exige migrations e `assert_schema_current`; não cria schema silencioso | prova PostgreSQL real | F6-D |
| E2E | canary browser em modo de teste já verde | staging/commercial runtime sem harness de autoridade | F6-D |

## 3. Fatos que não devem ser reabertos

1. `ExecutorAutoritativoSQLAlchemy` é alias intencional do executor canônico.
2. Checkout reserva estoque; pagamento/Venda não consomem estoque.
3. Consumo físico da reserva pertence ao início real da produção/KDS.
4. Repositórios permanecem transaction-neutral; UoW/aplicação é dona de commit/rollback.
5. Credenciais externas pertencem ao Control Plane + Vault.
6. Ausência de homologação externa não autoriza Fake e não deve impedir o PDV canônico em métodos que não dependem desses provedores.
7. `LEGACY` continua rollback operacional enquanto o cutover estiver em canary.

## 4. Gaps ordenados

### F6-A — Production Rollout / Canonical PDV Cutover Gate — FECHADA
- permitir `authoritative_canary` em staging/produção somente com autorização server-side;
- usar tenant/unidade do `RuntimeSettings`, não input da UI;
- identificar terminal por `FM_AI_PDV_TERMINAL_ID`;
- exigir allowlist `FM_AI_PDV_ALLOWED_TERMINALS`;
- manter `LEGACY` como default;
- falhar fechado em configuração parcial/inconsistente;
- criar fitness + CI dedicado.

### F6-B — Economic Edge Cleanup — FECHADA
- remover fallback de total zero para Venda legada;
- fechar contrato canônico para pedido de valor zero;
- provar idempotência/rollback sem criar obrigação fictícia.

### F6-C — Legacy Projection Containment — FECHADA
- classificar `LegacyPDVSQLAlchemyAdapter` somente como projeção/ponte de catálogo;
- eliminar qualquer baixa de estoque legada do caminho canônico;
- garantir que cashback/projeções compatíveis sejam efeitos idempotentes e não autoridade financeira;
- matriz transversal 22/22 verde no SHA de fechamento.

### F6-D — Commercial Runtime E2E — FECHADA
- PostgreSQL 16 efêmero no gate;
- `FM_AI_ENV=staging`, sem `FM_AI_TEST_MODE`;
- migrations oficiais + `assert_schema_current`;
- autenticação/RBAC reais com usuário CAIXA persistido;
- terminal `caixa-f6d` allowlisted server-side;
- jornada dinheiro;
- jornada cartão presencial;
- Pix sem provider homologado bloqueado/fail-closed;
- Playwright comercial separado do harness E2E de teste;
- evidência pós-browser nas tabelas canônicas do mesmo PostgreSQL;
- workflow dedicado `Fase 6D Commercial Runtime E2E Gate`;
- fechamento técnico no SHA `db422035c2339f9a8b9743f5138149fc205168d4`;
- matriz transversal integral 25/25 verde no mesmo SHA;
- Playwright comercial 3/3 verde: dinheiro, cartão presencial e Pix sem provider homologado fail-closed;
- migration `0037_pdv_reconciliation_strategy_width_v1` comprovada no PostgreSQL, ampliando `estoque_estrategia` de `VARCHAR(30)` para `VARCHAR(64)`;
- evidência pós-browser no mesmo PostgreSQL: `pedidos_v1 = 2` e `pagamentos_v1 = 2`;
- gate de Administração Fase 5 e demais regressões transversais também verdes no SHA de fechamento.

### F6-E — Canary Readiness / Reconciliation / Rollback — EM VALIDAÇÃO
- métricas por modo/terminal: telemetria estruturada para todos os modos + read model persistente de shadow/canary;
- reconciliação sem autocorreção destrutiva: read model estritamente somente leitura;
- rollback por configuração para LEGACY, preservando dados canônicos;
- runbook de ampliação/redução de coorte;
- CLI operacional somente leitura com recomendação conservadora;
- evidência de concorrência e retry;
- nenhuma migration nova e nenhuma nova autoridade operacional;
- implementação candidata parte de main@9e80138cb398ec69d7ee67e3687b801cc394594d; fechamento depende do gate dedicado, F6-D e matriz transversal no mesmo SHA.

### F6-F — Fechamento
- matriz transversal verde;
- checkpoint no mesmo SHA;
- external blockers discriminados;
- merge somente após autorização e gates verdes.

## 5. Definition of Done da Fase 6

A Fase 6 só fecha quando o runtime comercial puder executar o PDV canônico de forma governada, sem Fake no caminho comercial, sem autoridade de estoque/pagamento duplicada, com rollback explícito, navegador real e regressões verdes. Pendências de provedores externos permanecem separadas e não podem ser mascaradas.
