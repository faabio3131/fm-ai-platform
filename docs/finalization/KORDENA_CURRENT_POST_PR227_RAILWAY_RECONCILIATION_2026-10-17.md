# Kordena — CURRENT pós-PR #227 e reconciliação de infraestrutura (2026-10-17 UTC)

> Registro operacional de evidência pontual; não substitui os gates KF-G00 a KF-G13 nem autoriza lançamento público.

## Identidade / HEAD

- Repositório: `faabio3131/fm-ai-platform`
- Branch canônica de homologação Kordena: `staging/kordena-premium`
- HEAD de staging conferido via GitHub Git Tree: `d300ab1e2e01b004b45152c1c91d099731a4d6e0` (PR #227 integrada).
- `main` conferida: `9a047f98d45574eb7dbf171a9fff8fe5a79fcb2d`, commit `feat(kordena): implantar Central de Operações certificada`.
- Compare `main...staging`: **ahead=1232, behind=1, diverged** (ponto de leitura 2026-10-17 UTC). A única alteração exclusiva de `main` corresponde à Central de Operações e seus testes/configuração; não realizar merge/rebase cego. O valor histórico 896/0 do Cronograma não é mais o CURRENT.
- Staging permanece o source branch do serviço Web Railway. A promoção para `main` continua condicionada aos gates KF-00…KF-11.

## Railway — ambiente `production` técnico de homologação, NÃO lançamento comercial

Projeto: `diplomatic-expression` / `8cfbcd0f-a20b-4c9e-bc91-00e210d7f4e4`.
Environment: `119102c9-0a72-4f20-970a-29934584792c`.

Após exclusão controlada de recursos temporários, `environment_status(includeSuccessful=true)` retornou **3 serviços**, **0 com problemas**, **0 falhas recentes** e `pendingWork=[]`:

| Serviço | ID | Estado confirmado |
|---|---|---|
| `fm-ai-platform` | `669ca37e-1afa-4069-8344-b61ce1bc2646` | online; deploy SUCCESS; 1 replica |
| `Postgres` | `510d9999-7599-4fdb-b1ba-32881a993919` | online; deploy SUCCESS |
| `kordena-session-cleanup-cron` | `c75f8e16-3915-497a-96e4-0155582eaede` | cronReady; deploy SUCCESS |

Serviços temporários **removidos no mesmo environment** via Railway, remoção concluída e sem volumes destacados:
- `kordena-session-role-bootstrap-temp` (`b04e16d2-aca5-4335-bfde-48aaef099298`): provisionamento one-shot verificado nos logs `cleanup_role.provisioned_with_minimum_table_grants`; comando posterior já desativado; removido para não reter segredo administrativo de bootstrap.
- `kordena-pr200-ci-temp` (`c37f8b6b-ef81-456f-b604-c55142a01b3f`): serviço CI legado isolado da PR #200; removido, sem alteração no Web/Postgres/Cron.

## Cron — evidência e limite de certificação

- Serviço separado, sem servidor HTTP; comando `python -m scripts.cleanup_expired_operational_sessions`.
- Configuração confirmada: `cronSchedule="0 5 * * *"` (05:00 UTC / 02:00 America/Sao_Paulo), `restartPolicyType="NEVER"`; sem alteração staged.
- Logs Railway da execução real 2026-10-17 00:05 UTC: `Starting Container` e `expired_sessions_deleted=1`; deployment SUCCESS.
- A role dedicada `fm_session_cleanup_v1` e os limites de 500 por lote/10.000 por rodada são definidos pelo runbook PR #227. Esta inspeção não leu valores de segredos.
- **RECORRÊNCIA PROGRAMADA = PENDENTE DE PROVA**: execução manual/de deploy com sucesso não prova disparo agendado às 05:00 UTC nem a segunda execução idempotente; a API Railway indicou `cronJob=null`, não uma execução agendada conclusiva. Não atestar KF-G00 completamente enquanto faltar evidência.
- Condição de fechamento: após o próximo horário 05:00 UTC, obter execução identificável como agendada, log de contagem agregada, sucesso da tarefa e ausência de falhas; zero exclusões é válido. Se não houver execução, investigar schedule e falha antes de mudar configuração.

## PRs abertas — classificação, sem merge/close indiscriminado

Inventário via GitHub API em 2026-10-17 UTC:
- #224 `diag/kordena-pdv-sql-70-attribution-20261016`: DRAFT, diagnóstico de SQL, **não é gate de runtime do Cron**; revisar sobreposição com #225/#226 antes de fechar ou integrar.
- #217 `fix/assistente-homologacao-historico-30min-20261013`: OPEN, fluxo de homologação; confirmar E2E/integração no Render antes da decisão.
- #207 `fix/kordena-gerente-ia-503-safe-diagnostics-20261012`: DRAFT; comparar com #219 já integrado para evitar duplicidade.
- #203 `migration/kordena-render-completo-20261012`: DRAFT, homologação Render/central de operações; validar paridade e deploy antes de integrar.
- #202 `chore/kordena-render-homologacao-isolada-20261011`: DRAFT contra `main`; plano histórico não autoriza deploy.
- #200 `fix/kordena-voice-runtime-reconciliation`: OPEN; encerramento do serviço **CI temporário** não equivale a merge/fechamento da PR; avaliar branch contra CURRENT e suas migrations.
- #199 `fix/kordena-gerente-ia-voice-mobile`: OPEN; verificar se alterações já existem em staging antes de qualquer merge.

Nenhuma dessas PRs foi alterada neste registro. Não afirmar zero PRs inesperadas sem reconciliação individual por diff/checks.

## Gates e continuidade

- **PASS observado**: Web/Postgres/Cron saudáveis; 2 serviços temporários removidos; nenhum staged restante; Cron com execução real; fonte e cron schedule confirmados.
- **PENDING**: comprovação do disparo recorrente agendado; análise de diffs/checks das PRs antigas; verificações completas KF-G00 (migrations/schema/workflows/State Ledger, etc.); reconciliação de Central de Operações no fluxo de release; KF-01 e posteriores.
- **PROIBIDO**: promover `main`, rodar migrations ou alterar segredo de produção sem os gates aplicáveis; relançar homologação Gemini/Maps já certificada; iniciar NFCore no Kordena V1; declarar `KORDENA_V1_COMMERCIAL_READY` sem a matriz de release.
- **Rollback**: PR documental sem runtime; apagar/fechar esta branch/PR não afeta Railway. Serviços temporários excluídos podem ser reconstruídos a partir de configuração auditada se necessidade real surgir, mas suas credenciais nunca devem ser reutilizadas sem validação.

Referências: `docs/KORDENA_SESSION_CLEANUP_CRON_LEAST_PRIVILEGE_RUNBOOK_2026-10-16.md`; `docs/finalization/KORDENA_CRONOGRAMA_MESTRE_FINALIZACAO_V1_COMERCIAL_v2.0.md`; `docs/commercial-platform/KCA_EXECUTION_TRACKER.md`.
