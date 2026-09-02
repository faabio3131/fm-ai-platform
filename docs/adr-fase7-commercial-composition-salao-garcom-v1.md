# ADR F7-001 — Composition comercial de Salão/Garçom

**Status:** ADOTADO  
**Data:** 02/09/2026  
**Issue:** #71

## Problema

Salão e Garçom possuem domínios válidos, mas os renderers atuais ainda criam
schema/contexto de teste; o Salão também injeta pagamento de teste. A registry
já permite adapters reais, criando risco de ativar um harness de teste no
runtime comercial.

## Alternativas

### A. Reescrever Salão/Garçom
Rejeitada. Duplicaria domínio, UoW, idempotência, RBAC e regras já válidas.

### B. Criar nova migration/tabelas F7
Rejeitada no estado atual. A migration oficial
`0012_restaurant_operations_runtime_v1` já cria `SalaoBase` no runtime
canônico.

### C. Fazer cutover apenas do composition root
**Adotada.** Preserva domínio e troca somente identidade/schema/pagamento/UI
necessários ao runtime comercial.

## Decisões

1. Commercial default deriva `ContextoExecucao` da identidade autenticada.
2. Contexto/schema artificial só pode existir em E2E com `FM_AI_TEST_MODE=1`.
3. `migrations/salao_v1.py` continua test-only e não entra no commercial path.
4. O Salão só projeta Pagamento canônico previamente confirmado.
5. Garçom mantém sua matriz atual e não recebe permissão financeira.
6. Garçom opera mesa/comanda e solicita conta; Caixa/Gerente/Admin executam o
   fechamento financeiro conforme RBAC.
7. Nenhuma nova autoridade ou tabela é criada.
8. Rollback operacional futuro é por flags, preservando dados.

## Consequências

- menor delta e menor risco de regressão;
- recuperação do patrimônio PR11/PR12;
- elimina test harness do produto sem apagar E2Es isolados;
- requer Commercial Runtime E2E novo para provar a composição;
- eventual schema drift descoberto interrompe o trabalho e exige ADR/migration
  forward específica.

## Evidência exigida

- fitness anti-test-runtime;
- PostgreSQL fresh/upgrade/current;
- RBAC negativo;
- pagamento canônico + fechamento;
- Garçom mobile/tablet;
- KDS integrado;
- Commercial Runtime E2E;
- matriz final no mesmo SHA.
