# KCA-13 — Implementation & Certification Record

## Status

**KCA-G13 — PASS CANÔNICO**

Candidate funcional Kordena certificado:

`10cb4ac5da96947e0298616af9a3e56c37fccb23`

HEAD pré-merge final recertificado:

`72cb89feadc2930bf08a22d57edd31afc9bb7c54`

A recertificação pré-merge terminou com todos os gates obrigatórios em SUCCESS: Runtime Readiness #1140, KCA Commercial Gate #294, WP-031 Master Gate #303, WP-031L Regression Channel Parity #313, PR Superseded Runs Cleanup #840 e Vercel SUCCESS.

Merge Kordena KCA-13 em `staging/kordena-premium`:

`05c65c16ef380158b4602780511a9997e08cb5bb`

Pós-merge no SHA exato: Vercel SUCCESS + Railway SUCCESS.

**KCA-13 está INTEGRADO E ENCERRADO. KCA-14 permanece NÃO INICIADO.**

## 1. Bases reconciliadas

### Kordena / FM Commercial Platform

- Repositório: `faabio3131/fm-ai-platform`.
- Base: `staging/kordena-premium`.
- Base inicial confirmada: `9c52fd998e04c4d723171917f3776c9da7295858`.
- HEAD canônico pós-merge: `05c65c16ef380158b4602780511a9997e08cb5bb`.
- Branch: `feat/kordena-commercial-kca13-observability-antiabuse-finops`.
- PR: #130 — MERGED em `staging/kordena-premium`.
- Candidate funcional: `10cb4ac5da96947e0298616af9a3e56c37fccb23`.

### FM Control Center

A execução começou sobre a `main@5b433832e599f07a7b39c373c508733775d78406`.

Durante o KCA-13 ocorreram dois avanços concorrentes legítimos do CURRENT do FMCC:

1. PR #18 foi mergeada e levou a `main` para `221e8866c5d07f488dceb1861d44bf0771a75c0a`;
2. a branch KCA-13 foi reconciliada com essa nova `main` por merge não destrutivo, sem force push e sem rebase destrutivo;
3. o candidate FMCC KCA-13 atingiu `5def840f7a42686ae11df16406fcc68d54bb9647`;
4. PR #19 foi posteriormente mergeada de forma concorrente/externa a esta execução;
5. a `main` FMCC passou a `0e37eecb69d00361216468891c7442b74b993b29`.

O tree do candidate `5def840f...` e o tree do merge `0e37eecb...` são idênticos:

`591d6888afd400ac70fb76151445747475ad06b2`.

O Foundation Gate pós-merge foi executado exatamente em `main@0e37eecb...` e terminou SUCCESS.

## 2. CURRENT descoberto antes da implementação

O CURRENT já possuía:

- Commercial Registry;
- Product Accounts;
- Public Signup;
- Provisioning Saga;
- Trial Engine;
- Subscription Engine;
- Billing Provider Abstraction;
- Webhook Inbox + Reconciliation;
- Entitlement Authority + projeção local;
- KCA-12 / FMCC Control Plane;
- audit trail comercial com correlation IDs;
- AI usage metering;
- AI FinOps Read Model persistente;
- exclusão de INTERNAL_TEST dos facts comerciais KCA-12.

Portanto o KCA-13 não criou:

- segunda autoridade comercial;
- segundo sistema de FinOps;
- novo Billing Ledger;
- novo mecanismo de auditoria;
- nova migration;
- provider fictício;
- fonte fictícia de custo de infraestrutura;
- nova autoridade para o Core Cognitivo.

## 3. Implementação

Foi criada uma projeção comercial **read-only**:

`application/commercial_observability.py`

Contrato:

`kordena.observability.kca13.v1`

A projeção entrega:

- métricas comerciais;
- sinais de antiabuso;
- health operacional;
- alertas determinísticos;
- AI FinOps;
- tracing/correlation IDs;
- proveniência;
- quality status;
- cobertura/limitações explícitas.

O snapshot KCA-12 `kordena.fmcc.commercial.v1` foi preservado e recebeu o bloco opcional/aditivo `observability`, mantendo compatibilidade de rollout.

## 4. Métricas governadas

Janela padrão: rolling 30 dias, UTC.

Implementadas:

- `signup_started`;
- `signup_completed`;
- `tenant_provisioned`;
- `trial_started`;
- `trial_active`;
- `trial_expiring`;
- `trial_expired`;
- `trial_converted`;
- `conversion_rate`;
- `subscription_active`;
- `past_due`;
- `churn`;
- `mrr`;
- `arr`;
- `payment_success`;
- `payment_failure`.

Regras importantes:

- ausência de denominador não vira zero;
- dado indisponível permanece `unavailable`;
- MRR/ARR não fazem conversão FX inventada;
- moedas permanecem separadas;
- periodicidade desconhecida produz qualidade `partial`;
- churn é reconstruído por eventos e exige base ACTIVE anterior válida;
- métricas de trial/subscription são escopadas por `product_account_id` do Kordena.

## 5. Correção cross-product descoberta na auditoria

Durante a revisão foi identificado risco real de um mesmo `fm_customer_id` possuir Kordena e outro produto, como IRON, e os KPIs absorverem dados do produto irmão.

Correção aplicada antes da certificação:

- trials filtrados por Kordena `product_account_id`;
- subscriptions filtradas por Kordena `product_account_id`;
- billing derivado somente das subscriptions Kordena;
- churn filtrado pelo `product_account_id` Kordena.

Teste de regressão cria um mesmo cliente FM com Kordena + IRON e comprova que:

- trial IRON não entra no Kordena;
- assinatura IRON não entra no Kordena;
- MRR IRON não entra no Kordena.

## 6. INTERNAL_TEST

Os KPIs comerciais excluem `INTERNAL_TEST`.

Além do filtro explícito, foi verificado e protegido por fitness test que o Public Signup:

- delega ao Provisioning Orchestrator;
- cria cliente com `ClasseContaComercial.TRIAL`;
- não possui caminho público para criar `INTERNAL_TEST`.

## 7. FinOps

O KCA-13 reutiliza a autoridade existente:

`fm_ai_finops_daily_v1`

Disponível:

- custo de IA por tenant;
- known/unknown cost events;
- uso de IA por plano;
- tokens/attempts;
- moedas separadas.

Custo de infraestrutura:

`infra_cost_per_tenant = unavailable`

Motivo:

`infrastructure_cost_source_not_configured`

Nenhum valor foi inventado.

### Limitação conhecida e explícita

`usage_by_plan` associa o uso da janela ao plano presente na projeção corrente de entitlement no `as_of`.

Ele **não reconstrói historicamente** o plano efetivo de cada evento caso um tenant tenha mudado de plano dentro da janela.

Essa limitação não invalida o KCA-G13, mas deve permanecer explícita até existir necessidade de atribuição histórica de custo/uso por versão de plano.

## 8. Antiabuso

Sinais implementados:

- signup rate na última hora;
- resends de verificação;
- clientes com múltiplos registros históricos de trial;
- overrides administrativos de antiabuso;
- provisioning em `FAILED_RETRYABLE`.

Não foi criado score probabilístico arbitrário:

- `risk_score = null`;
- thresholds permanecem `not_configured` até política formal.

## 9. Health e alertas

Health considera:

- entitlement stale;
- webhook `DEAD_LETTER`;
- webhook `FAILED_RETRYABLE`;
- provisioning `FAILED_RETRYABLE`;
- eventos de AI FinOps com custo desconhecido.

Alertas são determinísticos e somente são emitidos quando o estado correspondente existe.

## 10. Segurança / boundaries

PASS:

- módulo de observabilidade read-only;
- nenhuma escrita SQL nova;
- nenhuma migration nova;
- nenhum secret na projeção;
- nenhuma PII de contato adicionada;
- INTERNAL_TEST excluído dos KPIs;
- correlation IDs reutilizados;
- FMCC sem SQL direto no banco operacional Kordena;
- Core Cognitivo recebe observabilidade como fato read-only;
- contrato FMCC falha fechado quando o bloco KCA-13 presente é malformado;
- proveniência vazia é rejeitada;
- alertas malformados são rejeitados;
- tracing incompleto é rejeitado;
- cross-product isolation dos KPIs protegida por teste.

## 11. Falhas encontradas e corrigidas durante a execução

### F1 — Ruff F841

Variável local não utilizada no primeiro candidate.

Correção: removida. Nenhuma regra de lint foi suprimida.

### F2 — fixture temporal na fronteira exata de 30 dias

O teste posicionava pagamento exatamente em `now - 30d`, mas o snapshot obtinha um `now` posterior por milissegundos.

Correção: fixture movida para 29 dias.

A regra real de janela de 30 dias não foi alterada.

### F3 — risco cross-product

Trial/subscription inicialmente podiam ser filtrados pelo cliente global e misturar produtos.

Correção: escopo por `product_account_id` Kordena + regressão Kordena/IRON.

## 12. Evidência Kordena — candidate funcional

Candidate:

`10cb4ac5da96947e0298616af9a3e56c37fccb23`

Workflows SUCCESS:

- Commercial Runtime Readiness V1 #1134;
- Kordena KCA Commercial Gate #288;
- WP-031 Master Gate #297;
- WP-031L Regression Channel Parity #307;
- PR Superseded Runs Cleanup #834.

Resultados:

- KCA targeted: **212 passed**, 1 warning;
- Full Python: **1813 passed**, 5 skipped, 101 warnings;
- Web Node: **16 passed**;
- Ruff: PASS;
- mypy: PASS;
- Migration Manifest: PASS;
- Schema Baseline: PASS;
- ESLint: PASS;
- TypeScript: PASS;
- Next production build: PASS;
- diff/whitespace gate: PASS;
- security / tenancy / RBAC / fail-closed matrices: PASS.

## 13. Evidência FMCC — pós-merge

Main certificada:

`0e37eecb69d00361216468891c7442b74b993b29`

Foundation Gate pós-merge #391:

**SUCCESS**

Resultados:

- Test Files: **48 passed**;
- Tests: **185 passed**;
- lint: PASS;
- TypeScript: PASS;
- schema/no drift: PASS;
- migration: PASS;
- high-confidence secret scan: PASS — **232 tracked files**;
- production build: PASS;
- Browser E2E: **6 passed**;
- runtime smoke: PASS;
- Docker build sem runtime secrets: PASS;
- runtime dependency audit com threshold HIGH: PASS.

Dependências:

- **4 advisories MODERATE transitivos**;
- nenhum HIGH/CRITICAL bloqueou o gate.

O candidate PR-head FMCC também havia passado Foundation + Cognitive Governed Intelligence Gate antes do merge, e seu tree é idêntico ao tree pós-merge.

## 14. Persistência / migrations

**Nenhuma migration nova foi necessária no KCA-13.**

A implementação deriva observabilidade de autoridades persistentes existentes.

## 15. Gate

**KCA-G13 — PASS CANÔNICO.**

- Candidate funcional: `10cb4ac5da96947e0298616af9a3e56c37fccb23`.
- HEAD documental recertificado: `8325913147bb2019b617249e66410ff14c0beba7`.
- Runtime Readiness #1135: SUCCESS.
- KCA Commercial Gate #289: SUCCESS.
- WP-031 Master Gate #298: SUCCESS.
- WP-031L Regression Channel Parity #308: SUCCESS.
- PR Superseded Runs Cleanup #835: SUCCESS.

Condições satisfeitas:

- observabilidade com proveniência;
- métricas comerciais governadas;
- INTERNAL_TEST excluído;
- health;
- alertas;
- tracing/correlation IDs;
- antiabuso mínimo observável;
- AI FinOps reutilizado;
- ausência != zero;
- cross-product isolation;
- FMCC consumindo o contrato e certificado pós-merge.

A recertificação do HEAD documental foi concluída. O KCA-G13 está formalmente fechado sem alteração funcional posterior ao candidate certificado.

## 16. Fechamento pós-merge

- PR Kordena #130: **MERGED** em 2026-09-23T22:59:08Z.
- HEAD pré-merge recertificado: `72cb89feadc2930bf08a22d57edd31afc9bb7c54`.
- Merge commit / HEAD de staging: `05c65c16ef380158b4602780511a9997e08cb5bb`.
- Pós-merge Vercel: **SUCCESS**.
- Pós-merge Railway: **SUCCESS**.
- Nenhum cliente real, provider/credencial/cobrança real ou abertura pública foi criado por este fechamento.
- **KCA-G13: PASS, INTEGRADO E ENCERRADO.**
- **KCA-14: NÃO INICIADO** neste registro; deve nascer do CURRENT pós-merge certificado.
