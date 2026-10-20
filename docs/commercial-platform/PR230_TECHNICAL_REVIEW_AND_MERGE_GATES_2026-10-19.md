# PR #230 — Revisão técnica e gates de merge
Data 2026-10-19. Status: REVISÃO TÉCNICA DO EXECUTOR, NÃO REVISÃO INDEPENDENTE.

## Âncora de evidências
- Repositório faabio3131/fm-ai-platform; PR https://github.com/faabio3131/fm-ai-platform/pull/230
- Head revisado 01b6bcd4bc88a82972f4dd3547ce142fd872c832; base da PR d300ab1e2e01b004b45152c1c91d099731a4d6e0.
- CI do head: 20 workflows completed/success; nenhuma falha restante na rodada consultada.
- PR já retirada de Draft, mergeable=true em consulta; reviews de GitHub: [] e threads: [].
- A main consultada em 19/10: 9a047f98d45574eb7dbf171a9fff8fe5a79fcb2d, diferente da base da PR. Exige conciliação explícita de ancestralidade/base atual e regressão no SHA definitivo; não usar mergeable como substituto de gate.

## Escopo auditado
Inspeção estática de application/ai_budget_provision.py, infra/ai_budget_guard.py, infra/ai_budget_policy_resolver.py e infra/ai_budget_sqlalchemy.py, além da lista dos 29 arquivos alterados, AGENTS.md e status do CI. Não configura auditoria exaustiva de cada arquivo nem avaliação externa.

## Achados positivos verificados
1. _sync_entitlement chama provisionamento apenas quando assinatura ativa. Provisionamento exige assinatura, produto/tenant e plan_version compatíveis com entitlement, capability habilitada, USD e scope unit, e membership KORDENA ativa com unidades explícitas.
2. AI Budget Guard exige revisão de política; a reserva leva expected_revision para o UPDATE condicional, que limita consumido+reservado+valor <= limite. Replay é negado antes da chamada faturável do provider.
3. Falhas/timeout sem custo conhecido permanecem pending_reconciliation. Custos internos não são expostos no contrato de visão do cliente.
4. Resolver exige tenant+unidade local, entitlement vigente, capability autorizada, uma franquia ativa sem ambiguidade e budget revision igual ao entitlement.
5. Os sete testes de regressão que falhavam em 18/10 foram corrigidos sem relaxar revisao_politica e voltaram a passar na suíte integral.

## Riscos ainda a verificar em revisão independente
A. Confirmar provas de PostgreSQL real de concorrência e rollback (não inferir de SQLite), inclusive sync política concorrente, mudança de entitlement no meio da reserva e release pós-timeout; risco financeiro.
B. Conferir se identidade membership/unidade revogada não consegue continuar consumindo entre projeções; testes negativos por tenant, unidade e produto em E2E real.
C. Reconciliar o conjunto de commits que entraram em main depois da base e sua eventual sobreposição com os 29 arquivos da PR. Resolver conflitos sem overwrite/force push; repetir todos gates afetados.
D. Revisar migration 0070 e schema baseline fresh/upgrade/rollback em PostgreSQL descartável, integridade, backup/restore proporcional ao risco.
E. Certificar as 29 mudanças e rotas HTTP/ACL, bypass/trial, cron job/telemetria, vazamento de custo, finalização/idempotência e versões contratadas por outro revisor autorizado.
F. Evidência humana de revisão APPROVED na PR por reviewer autorizado. Um relatório de auto-revisão do executor não satisfaz essa condição.

## Decisão do executor
MERGE NÃO LIBERADO nesta revisão, apesar de 20/20 workflows SUCCESS: falta aprovação independente e verificação de reconciliação no SHA final após base atual. Nenhum deploy, migration real ou billing real é autorizado.

## Próximas ações
- Submeter esta matriz ao revisor autorizado; registrar cada evidência faltante e eventuais correções.
- Concluir atualização não destrutiva da branch com main apenas após inspecionar conflito/overlap; rodar 100% gates obrigatórios no SHA resultante.
- Obter APPROVED de reviewer distinto; verificar policies obrigatórias; depois merge do SHA exato sob autorização vigente; checar push CI pós-merge.
