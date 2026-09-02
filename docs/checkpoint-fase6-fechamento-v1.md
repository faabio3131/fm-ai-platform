# F6-F — Checkpoint Final da Fase 6

**Status:** EM VALIDAÇÃO FINAL  
**Branch:** `feature/f6e-canary-readiness-reconciliation-rollback`  
**Base integrada:** `main@9e80138cb398ec69d7ee67e3687b801cc394594d`  
**Checkpoint F6-E documental revalidado:** `716a4c465caa46b729fe64b12f67469cfd7f941d`

## 1. Escopo encerrado até F6-E

- F6-A: Production Rollout / Canonical PDV Cutover Gate;
- F6-B: Economic Edge Cleanup;
- F6-C: Legacy Projection Containment;
- F6-D: Commercial Runtime E2E;
- F6-E: Canary Readiness / Reconciliation / Rollback.

## 2. Provas consolidadas

No checkpoint F6-E documental:
- matriz transversal 23/23 workflows verde;
- F6-E dedicado: compile, Ruff e mypy verdes;
- F6-E focados: 20 passed;
- regressão PDV: 49 passed;
- F6-D PostgreSQL comercial: migration 0037 30→64 comprovada;
- F6-D regressões: 25 passed;
- Playwright comercial: 3/3;
- evidência pós-browser: 2 pedidos e 2 pagamentos;
- PR11 rerun isolado verde no mesmo SHA após timeout flutuante do Playwright;
- nenhuma falha funcional persistente aberta.

## 3. Definition of Done da Fase 6

O candidato atual comprova:
- Pedido canônico como autoridade do PDV;
- Pagamento/VendaFinanceira canônicos como autoridade financeira;
- estoque canônico sem dupla autoridade econômica;
- canary comercial server-side e allowlisted;
- terminal server-side fail-closed;
- dinheiro e cartão presencial operacionais no canônico;
- Pix sem provider homologado fail-closed;
- reconciliação diagnóstica e não destrutiva;
- métricas/readiness por modo e terminal;
- retry e concorrência idempotentes;
- rollback operacional explícito para LEGACY;
- browser comercial e PostgreSQL reais no gate;
- nenhuma migration nova no F6-E.

## 4. Blockers externos e operacionais

Estes itens NÃO invalidam as provas internas da Fase 6, mas impedem declarar
homologação externa ou produção efetivamente implantada:

1. PagBank — homologação/configuração externa pendente.
2. Mercado Pago — homologação/configuração externa pendente.
3. Meta — configuração/homologação externa pendente.
4. Canal de deploy de produção — inexistente no repositório atual; os workflows
   de `main` são CI/gates e não executam implantação em plataforma externa.

Consequências:
- nenhum provider externo acima é declarado homologado;
- nenhum deploy de produção é declarado executado;
- LEGACY permanece rollback operacional enquanto o cutover não for promovido;
- Pix sem provider válido permanece bloqueado/fail-closed.

## 5. Merge e deploy

Este checkpoint não autoriza merge por si só. O merge depende de:
1. revalidação integral do SHA deste checkpoint final;
2. autorização explícita do proprietário.

Mesmo após merge, deploy só poderá ser declarado quando houver um canal
operacional real e verificável de implantação.

## 6. Gate final

O SHA que contém este documento deve executar novamente a matriz transversal.
F6-F só poderá ser promovido de EM VALIDAÇÃO FINAL para FECHADA após:
- todos os workflows aplicáveis concluírem com SUCCESS;
- zero falhas/pending;
- evidência registrada no mesmo SHA.
