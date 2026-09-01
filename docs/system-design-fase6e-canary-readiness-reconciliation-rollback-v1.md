# F6-E — System Design — Canary Readiness / Reconciliation / Rollback

Status: IMPLEMENTAÇÃO CANDIDATA — CI pendente
Base: main@9e80138cb398ec69d7ee67e3687b801cc394594d
Autoridades: Documento Mestre §§2, 3, 3.0.1–3.0.3 e Fase 6; System Design Master;
Issue #66; inventário Fase 6.

## 1. Objetivo

Fechar a prontidão operacional do canary antes do F6-F: observar por
modo/terminal, detectar divergências sem autocorreção, permitir decisão
conservadora de coorte, provar retry/concorrência e manter rollback explícito
para LEGACY.

## 2. Source of truth e boundaries

Não muda:
- Pedido: domínio canônico de Pedidos;
- Pagamento/VendaFinanceira: domínio canônico de Pagamentos;
- estoque: ledger/reservas canônicos;
- UoW: owner transacional;
- reconciliação: evidência diagnóstica, nunca autoridade de reparo.

F6-E adiciona apenas:
- read model de readiness sobre pdv_reconciliacoes_v1;
- telemetria estruturada no boundary de rollout;
- CLI operacional somente leitura;
- runbook de coorte/rollback.

## 3. Métricas

Persistentes: shadow/canary já gravam reconciliação com
pdv:<terminal>:<checkout>:reconciliacao. O read model agrupa por modo + terminal,
com limite máximo de 10.000 linhas por consulta.

Operacionais: todo resultado do orquestrador emite pdv_rollout_resultado com
tenant, unidade, terminal, modo, sucesso, idempotência e motivo seguro. Nenhum
produto, cliente, conteúdo de pagamento, segredo ou credencial é logado.

## 4. Recomendação de coorte

- qualquer divergência, reparo necessário ou chave inválida: reduzir_coorte;
- amostra vazia ou pendência financeira: manter_coorte;
- amostra válida, sem divergências/reparos/pendências: ampliacao_elegivel.

A recomendação é assistiva. Não existe mutação automática de allowlist ou modo.

## 5. Rollback

O rollback operacional é:
1. definir FM_AI_PDV_MODE=legacy;
2. desligar FM_AI_PDV_COMMERCIAL_CANARY_ENABLED;
3. reiniciar/recarregar o runtime do terminal;
4. verificar que carregar_rollout_ambiente resolve LEGACY;
5. preservar todos os dados canônicos já gravados.

Remover terminal da allowlist enquanto o processo continua solicitando canary
não é rollback: isso falha fechado por design.

## 6. Concorrência e retry

- constraints canônicas continuam impedindo Pedido/Pagamento/Venda duplicados;
- reconciliação permanece única por tenant/unidade/idempotency key;
- replay serial do mesmo checkout retorna idempotente=True;
- o teste concorrente com duas sessões deve deixar uma única reconciliação.

## 7. Tenant/unidade/RBAC/auditoria

Readiness recebe tenant/unidade do runtime/contexto e filtra ambos na query.
Não há parâmetro de CLI para trocar tenant/unidade. O PDV continua exigindo
PDV_OPERAR; F6-E não amplia permissão.

## 8. Persistência/migrations

Nenhuma migration nova. O desenho reutiliza a chave persistente existente e
preserva history/manifest imutáveis.

## 9. Falhas/retries/fail-closed

- chave de reconciliação malformada é bloqueio de ampliação;
- limite de consulta inválido falha fechado;
- divergência nunca dispara UPDATE/DELETE;
- erro do checkout continua propagado e recebe telemetria somente com tipo de
  exceção, sem mensagem potencialmente sensível.

## 10. Desempenho

Consulta bounded, uma única query tenant/unidade e agregação local linear.
Sem N+1, cache, fila ou materialização nova.

## 11. Gate

F6-E exige compile/Ruff/mypy; unitários de métricas/telemetria/rollback;
integração de retry e read-only; concorrência; rollback atômico e divergência
existentes; regressão completa do PDV; F6-D comercial PostgreSQL/browser e
matriz transversal no mesmo SHA antes do fechamento.
