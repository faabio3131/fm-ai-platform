# KCA-13 — Implementation Record

## Status

**EM EXECUÇÃO / GATE KCA-G13 PENDENTE DE CI E RECERTIFICAÇÃO**

Este registro não declara KCA-G13 aprovado.

## Base reconciliada

### Kordena / FM Commercial Platform

- Repositório: `faabio3131/fm-ai-platform`.
- Base certificada: `staging/kordena-premium` @ `9c52fd998e04c4d723171917f3776c9da7295858`.
- Branch: `feat/kordena-commercial-kca13-observability-antiabuse-finops`.
- KCA-12 já integrado na base: PASS.
- KCA-14: NÃO INICIADO.

### FM Control Center

- Repositório: `faabio3131/FM-CONTROL-CENTER`.
- Base certificada: `main` @ `5b433832e599f07a7b39c373c508733775d78406`.
- Branch preparada: `feat/fmcc-kca13-kordena-observability`.
- PR #18 existente permanece paralela e não é dependência do KCA-13.

## CURRENT descoberto antes da implementação

O CURRENT já possuía:

- Commercial Registry, Product Accounts, signup, provisioning, trial, subscription, billing, entitlement e KCA-12;
- audit trail comercial com correlation ID;
- Webhook Inbox e reconciliation;
- AI usage metering + AI FinOps Read Model já persistente e certificado;
- projeção KCA-12 para o FMCC com exclusão de INTERNAL_TEST dos facts comerciais;
- FMCC com Metric Registry, Metric Engine, Source Registry, Alerts, Audit Ledger e Core Cognitivo governado.

Portanto o KCA-13 **não cria**:

- segunda autoridade comercial;
- segundo sistema de FinOps;
- novo billing ledger;
- novo mecanismo de auditoria;
- nova fonte de custos de infraestrutura;
- provider fictício;
- migration sem necessidade demonstrada.

## Escopo congelado

Implementar de forma aditiva e read-only:

1. projeção governada de observabilidade comercial;
2. métricas KCA-13 com semântica explícita;
3. exclusão de INTERNAL_TEST dos KPIs comerciais;
4. antiabuso baseado em sinais observáveis, sem score inventado;
5. health operacional derivado de estados autoritativos;
6. alertas determinísticos sobre falhas observadas;
7. reutilização do AI FinOps existente;
8. `infra_cost_per_tenant` indisponível até existir fonte governada;
9. tracing por correlation IDs existentes;
10. extensão aditiva do contrato KCA-12 por `observability`;
11. integração FMCC preservando ausência != zero.

## Semântica das métricas

Janela operacional padrão desta projeção: rolling 30 dias, com `as_of` em UTC.

- `signup_started`: intents públicos criados na janela.
- `signup_completed`: intents públicos que atingiram READY na janela.
- `tenant_provisioned`: sagas READY ligadas a cliente não INTERNAL_TEST.
- `trial_started`: trials não INTERNAL_TEST iniciados na janela.
- `trial_active`: estado atual ACTIVE com `ends_at > as_of`.
- `trial_expiring`: ACTIVE com término nos próximos 7 dias.
- `trial_expired`: trials atualmente EXPIRED atualizados na janela.
- `trial_converted`: `converted_at` na janela.
- `conversion_rate`: conversões da coorte de trials iniciados na janela / trials iniciados na janela; coorte vazia = unavailable.
- `subscription_active`: estado atual ACTIVE.
- `past_due`: estado atual PAST_DUE.
- `churn`: gross logo churn de 30 dias reconstruído por eventos: cancelamentos, dentro da janela, de assinaturas que estavam ACTIVE imediatamente antes do início da janela / base ACTIVE inicial. Base vazia = unavailable.
- `MRR` / `ARR`: apenas assinaturas ACTIVE com períodos reconhecidos. Moedas permanecem separadas; nenhuma conversão FX é fabricada. Períodos não reconhecidos tornam a qualidade partial.
- `payment_success` / `payment_failure`: transações de pagamento na janela.

## FinOps

A implementação reutiliza `fm_ai_finops_daily_v1`.

Entregas:

- AI cost per tenant;
- uso por plano a partir da projeção de entitlement;
- cobertura known/unknown de custo de IA;
- currencies separadas.

`infra_cost_per_tenant` permanece:

`unavailable / infrastructure_cost_source_not_configured`

até existir uma fonte governada real.

## Antiabuso

Sinais observáveis:

- signup rate na última hora;
- quantidade de resends na janela;
- clientes com mais de um registro histórico de trial;
- overrides administrativos de antiabuso registrados no audit trail;
- provisioning em FAILED_RETRYABLE.

Nenhum risk score arbitrário foi criado. Thresholds de política permanecem `not_configured` até decisão própria.

## Health e alertas

Health considera:

- entitlement stale;
- billing webhook DEAD_LETTER;
- webhook FAILED_RETRYABLE;
- provisioning FAILED_RETRYABLE;
- eventos AI FinOps com custo desconhecido.

Alertas são determinísticos e somente aparecem quando o respectivo estado/falha existe.

## Persistência / migrations

**Nenhuma migration nova necessária.**

O KCA-13 somente lê autoridades persistentes existentes.

## Segurança / boundaries

- read-only;
- nenhuma escrita SQL no módulo de observabilidade;
- nenhum secret na projeção;
- nenhuma PII de contato adicionada;
- INTERNAL_TEST excluído dos KPIs comerciais;
- correlation IDs reutilizados;
- sem acesso direto do FMCC ao banco do Kordena;
- sem alteração de autoridade do Core Cognitivo.

## Evidência já adicionada no candidate

- `application/commercial_observability.py`;
- extensão aditiva de `application/fmcc_commercial_projection.py`;
- `tests/unit/comercial/test_commercial_observability_kca13.py`;
- `tests/fitness/test_kca13_observability.py`;
- extensão do teste HTTP KCA-12;
- KCA commercial gate atualizado para incluir os artefatos KCA-13.

## Pendente para certificação

- integração do contrato no FMCC;
- testes FMCC;
- PRs Draft;
- CI completo dos dois repositórios;
- correção de qualquer falha;
- recertificação;
- registro dos SHAs finais;
- KCA-G13 PASS somente após evidência.

Nenhum merge, deploy, KCA-14 ou abertura pública está autorizado por este registro.
