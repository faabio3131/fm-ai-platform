# F6-A — System Design — Production Rollout / Canonical PDV Cutover Gate

**Status inicial:** IMPLEMENTAÇÃO CANDIDATA — validação CI pendente  
**Base:** `64b99bec2be2d87d0f216302010d7b877cf1efd5`

## 1. Objetivo

Permitir que staging/produção promovam uma coorte mínima do PDV para o executor canônico já existente, sem alterar a autoridade por ação do operador e sem retirar o rollback LEGACY.

## 2. Contrato de configuração

### Default seguro
Sem configuração adicional, o modo é `legacy`.

### Harness E2E
`FM_AI_TEST_MODE=1` preserva `FM_AI_TEST_TENANT`, `FM_AI_TEST_UNIDADE` e `FM_AI_TEST_TERMINAL`.

### Canary comercial
Para `FM_AI_PDV_MODE=authoritative_canary` fora de teste são obrigatórios:

- runtime `staging` ou `production` já validado por `RuntimeSettings`;
- `FM_AI_PDV_COMMERCIAL_CANARY_ENABLED=1`;
- `FM_AI_PDV_TERMINAL_ID=<terminal atual>`;
- `FM_AI_PDV_ALLOWED_TERMINALS=<allowlist separada por vírgula>`;
- terminal atual presente na allowlist.

Tenant e unidade vêm exclusivamente de `RuntimeSettings.tenant_id/unidade_id`.

Configuração parcial gera `ConfiguracaoRolloutInvalida`. Não existe fallback silencioso para canary incompleto.

## 3. Autoridade

O gate não cria executor novo. O caminho público continua:

`ExecutorAutoritativoSQLAlchemy`
→ alias de `ExecutorAutoritativoCanonicoSQLAlchemy`
→ `application.checkout.executar_checkout_em_transacao`
→ Pedido + Pagamento + Reserva de Estoque + efeitos
→ UoW do chamador.

A projeção legada continua apenas como compatibilidade transitória.

## 4. Segurança

- nenhuma flag de rollout é editável na UI;
- terminal é configuração server-side;
- tenant/unidade são os do runtime autenticado;
- `decidir_modo` ainda compara Active Execution Scope com a coorte;
- terminal fora da allowlist falha fechado;
- canary incompleto falha fechado;
- migrations não são executadas automaticamente no runtime comercial;
- nenhum segredo de provedor é lido pelo loader de rollout.

## 5. Relação com provedores externos

F6-A não declara PagBank, Mercado Pago ou Meta homologados. O cutover canônico pode ser validado com métodos internos/operacionais que não dependem deles. Pix real continua condicionado ao Control Plane, Vault, adapter e homologação do provider, sempre fail-closed.

## 6. Rollback

Rollback operacional é remover/desligar `FM_AI_PDV_COMMERCIAL_CANARY_ENABLED` e voltar `FM_AI_PDV_MODE=legacy`. Dados canônicos já persistidos permanecem preservados; rollback não autoriza apagar Pedido, Pagamento, ledger, eventos ou auditoria.

## 7. Gate CI

A F6-A exige:
- compile;
- Ruff;
- mypy do PDV/runtime;
- testes unitários de rollout;
- fitness provando wiring canônico do app;
- regressão de canary e Active Execution Scope;
- regressão Wave1 transacional disparada pela matriz existente.

E2E comercial sem `FM_AI_TEST_MODE` pertence à F6-D, depois que F6-A provar o contrato de rollout.
