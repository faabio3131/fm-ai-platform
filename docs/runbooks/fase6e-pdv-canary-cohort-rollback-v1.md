# Runbook F6-E — Ampliação, redução e rollback do canary PDV

## Princípios

- LEGACY permanece rollback durante o canary.
- Nenhuma divergência é autocorrigida.
- Nenhuma recomendação do CLI altera produção.
- Dados canônicos já gravados nunca são apagados para realizar rollback.
- PagBank/Mercado Pago/Meta não homologados permanecem separados.

## 1. Ler readiness

No ambiente correto, com FM_AI_ENV, DATABASE_URL, FM_AI_TENANT_ID e
FM_AI_UNIDADE_ID configurados:

python -m scripts.pdv_canary_readiness --limit 1000

Para um gate automatizado que só passa quando a amostra estiver elegível:

python -m scripts.pdv_canary_readiness --limit 1000 --require-eligible

O CLI é somente leitura e executa assert_schema_current.

## 2. Critério para ampliar coorte

Somente considerar ampliação quando:
- recomendacao=ampliacao_elegivel;
- divergentes=0;
- reparo_necessario=0;
- pendentes=0;
- chaves_invalidas=0;
- CI e Commercial Runtime E2E do SHA candidato estiverem verdes.

A ampliação é humana/operacional: adicionar o terminal autorizado na
configuração server-side e validar o runtime desse terminal. O software não
edita a allowlist sozinho.

## 3. Reduzir coorte

Se a recomendação for reduzir_coorte, congelar novas ampliações e retornar os
terminais afetados para LEGACY. Preservar a evidência divergente para
investigação; não executar UPDATE/DELETE corretivo em lote.

## 4. Rollback por terminal/runtime

Configuração-alvo:

FM_AI_PDV_MODE=legacy
FM_AI_PDV_COMMERCIAL_CANARY_ENABLED=0

Reiniciar/recarregar o runtime e provar que o loader resolve legacy.

Não usar apenas remover da allowlist mantendo FM_AI_PDV_MODE=authoritative_canary:
isso deve falhar fechado e é erro de configuração, não rollback.

## 5. Verificações pós-rollback

- nenhuma nova transação do terminal entra em authoritative_canary;
- Pedidos/Pagamentos/ledger/eventos já canônicos permanecem preservados;
- logs pdv_rollout_resultado passam a indicar pdv_modo=legacy;
- reconciliações históricas continuam consultáveis;
- investigar qualquer divergência antes de reabrir a coorte.

## 6. Roll forward

Após corrigir a causa raiz e obter gates verdes no novo SHA:
1. consultar readiness;
2. reautorizar canary server-side;
3. adicionar/revalidar terminal;
4. executar jornada comercial;
5. acompanhar reconciliação/telemetria;
6. ampliar somente após nova decisão humana.

## 7. Deploy

Este runbook não cria nem simula canal de deploy. Enquanto não existir pipeline
de produção verificável, nenhuma etapa deve ser declarada deploy executado
apenas por merge em main.
