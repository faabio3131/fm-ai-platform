# Fase 6 — Inventário Current → Target — PDV / Pedido / Pagamento / Estoque V1

**Data de abertura:** 01/09/2026  
**Base auditada:** `main` @ `64b99bec2be2d87d0f216302010d7b877cf1efd5`  
**Programa de recuperação:** Issue #62  
**Regra:** preservar patrimônio canônico já construído; corrigir composição/cutover, não reescrever domínio válido.

## 0. Checkpoints de execução

- F6-A fechada em `8ce3eba882d65af78822a35dae23c97e0e8ad628`: matriz 20/20 verde e reexecução extra do PR11 E2E principal verde.
- F6-B aberta após o checkpoint F6-A, sem merge/deploy e sem reabrir decisões já aprovadas.

## 1. Resultado executivo

A Fase 6 não começa do zero. Pedido, checkout, Pagamento/VendaFinanceira, ledger/reserva de Estoque, UoW, eventos/outbox/auditoria, reconciliação e o executor canônico do PDV já existem e possuem gates verdes na `main`.

O gap principal é operacional: o loader atual do PDV força `LEGACY` fora de `FM_AI_TEST_MODE=1`. Portanto o caminho canônico existe, está ligado à UI pelo alias `ExecutorAutoritativoSQLAlchemy -> ExecutorAutoritativoCanonicoSQLAlchemy`, mas não pode ser promovido por configuração normal de staging/produção.

## 2. Current → Target

| Área | Current comprovado | Target Fase 6 | Ação |
|---|---|---|---|
| Pedido | `core/pedidos` autoritativo, CAS, idempotência, tenant/unidade | única autoridade de pedido do PDV | preservar |
| Checkout | `application/checkout.py` cria Pedido, obrigação e reserva na mesma UoW | fronteira canônica do PDV comercial | preservar |
| Pagamento | obrigação, confirmação, webhook, reconciliação e VendaFinanceira | autoridade financeira do PDV | preservar/compor |
| Estoque | ledger + reserva canônicos; consumo pertence ao início da produção | retirar autoridade econômica do checkout legado | preservar/completar cutover |
| PDV | executor canônico já é o executor público do canary | permitir canary comercial governado | F6-A |
| Rollout | canary somente em `FM_AI_TEST_MODE=1` | staging/produção explicitamente allowlisted e fail-closed | F6-A |
| Terminal | `app.py` ainda deriva terminal de `FM_AI_TEST_TERMINAL`/default | identidade de terminal server-side comercial | F6-A |
| Venda legada | projeção de compatibilidade ainda necessária para telas/relatórios antigos | borda de compatibilidade, nunca autoridade do novo domínio | F6-B/F6-C |
| Total zero | `finalizar_venda_pdv` ainda faz fallback explícito para legado | eliminar fallback econômico legado | F6-B |
| Pix | Control Plane seguro já cria/consulta cobrança; provedores externos dependem de homologação | manter fail-closed por provider sem bloquear dinheiro/cartão | F6-D/F6-E |
| UI | `app.py` já instancia o executor canônico quando o modo resolve canary | mesma UI, sem toggle de autoridade pelo operador | preservar |
| Banco | runtime comercial exige migrations e `assert_schema_current`; não cria schema silencioso | mesma regra | preservar |
| E2E | canary browser em modo de teste já verde | provar staging/commercial runtime sem harness de autoridade | F6-D |

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

### F6-B — Economic Edge Cleanup — CANDIDATA EM VALIDAÇÃO
- remover fallback de total zero para Venda legada;
- fechar contrato canônico para pedido de valor zero;
- provar idempotência/rollback sem criar obrigação fictícia.

### F6-C — Legacy Projection Containment
- classificar `LegacyPDVSQLAlchemyAdapter` somente como projeção/ponte de catálogo;
- eliminar qualquer baixa de estoque legada do caminho canônico;
- garantir que cashback/projeções compatíveis sejam efeitos idempotentes e não autoridade financeira.

### F6-D — Commercial Runtime E2E
- PostgreSQL;
- `FM_AI_ENV=staging` ou produção controlada, sem `FM_AI_TEST_MODE`;
- autenticação/RBAC reais;
- caixa allowlisted;
- jornada dinheiro/cartão;
- Pix sem provider homologado permanece bloqueado/fail-closed;
- navegador físico automatizado no mesmo SHA.

### F6-E — Canary Readiness / Reconciliation / Rollback
- métricas por modo/terminal;
- reconciliação sem autocorreção destrutiva;
- rollback por configuração para LEGACY;
- runbook de ampliação/redução de coorte;
- evidência de concorrência e retry.

### F6-F — Fechamento
- matriz transversal verde;
- checkpoint no mesmo SHA;
- external blockers discriminados;
- merge somente após autorização e gates verdes.

## 5. Definition of Done da Fase 6

A Fase 6 só fecha quando o runtime comercial puder executar o PDV canônico de forma governada, sem Fake no caminho comercial, sem autoridade de estoque/pagamento duplicada, com rollback explícito, navegador real e regressões verdes. Pendências de provedores externos permanecem separadas e não podem ser mascaradas.
