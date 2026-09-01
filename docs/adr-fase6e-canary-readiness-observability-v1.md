# ADR F6-E — Readiness do Canary sem nova autoridade de métricas

Status: ADOTADO PARA IMPLEMENTAÇÃO CANDIDATA
Base: main@9e80138cb398ec69d7ee67e3687b801cc394594d
Fase: F6-E — Canary Readiness / Reconciliation / Rollback

## Problema

O F6-E exige métricas por modo/terminal, reconciliação não destrutiva, rollback
para LEGACY e evidência de concorrência/retry. O runtime já possui reconciliação
persistente e a chave canônica de idempotência inclui o terminal.

## Alternativas consideradas

1. Criar nova tabela de métricas. Rejeitada: duplicaria estado operacional e
   adicionaria migration sem necessidade.
2. Alterar pdv_reconciliacoes_v1 para acrescentar terminal_id. Rejeitada: a
   informação já está na chave canônica e a alteração aumentaria risco de
   schema/history sem ganho de autoridade.
3. Reutilizar reconciliação + telemetria estruturada. ADOTADA.

## Decisão

- Pedido, Pagamento, Estoque e VendaFinanceira permanecem autoridades.
- pdv_reconciliacoes_v1 continua evidência persistente de saúde do
  shadow/canary; nunca é usada para corrigir dados automaticamente.
- O terminal é extraído da chave pdv:<terminal>:<checkout>:reconciliacao.
  EntradaPDV passa a rejeitar terminal vazio, com whitespace lateral ou dois
  pontos, preservando proveniência não ambígua.
- Um read model bounded/tenant-scoped agrega reconciliações por modo/terminal e
  produz apenas recomendação: manter, reduzir ou ampliação elegível.
- O orquestrador emite log estruturado para todos os modos, inclusive LEGACY,
  sem produto, cliente, credencial ou segredo.
- Nenhuma recomendação altera variável de ambiente, allowlist ou dados.
- Rollback continua sendo configuração para FM_AI_PDV_MODE=legacy; dados
  canônicos persistidos não são removidos.

## Consequências

Positivas: zero migration, zero nova autoridade, consultas bounded, telemetria
cross-mode e rollback simples. Risco residual: logs dependem da plataforma de
observabilidade para retenção/agregação; por isso a decisão de coorte usa também
a reconciliação persistente.

## Migração/rollback

Não há migration. Rollback do código remove o read model/telemetria sem tocar
dados. Rollback operacional do canary é exclusivamente de configuração.

## Evidências exigidas

Ruff, mypy, testes unitários, retry idempotente, duas sessões concorrentes,
rollback atômico existente, divergência fail-closed, F6-D PostgreSQL/browser e
matriz transversal.
