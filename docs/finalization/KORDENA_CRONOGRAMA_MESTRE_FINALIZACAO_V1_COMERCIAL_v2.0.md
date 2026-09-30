# KORDENA — CRONOGRAMA MESTRE DE FINALIZAÇÃO V1 COMERCIAL

**Versão:** 2.0 — Final Reconciliada  
**Data-base:** 30/09/2026  
**Empresa:** Nova FM Tecnologia  
**Produto:** Kordena  
**Escopo:** conclusão integral do Kordena V1 para operação comercial controlada.  
**Exclusão deliberada:** integração/cutover Kordena → NFCore. Essa integração será executada posteriormente em cronograma próprio.

---

## 1. ORDEM EXECUTIVA

A execução seguirá continuamente:

```text
CONFIRMAR CURRENT
→ EXECUTAR
→ CORRIGIR
→ TESTAR
→ AUDITAR
→ CERTIFICAR
→ MERGEAR QUANDO APLICÁVEL
→ VALIDAR PÓS-MERGE
→ ATUALIZAR CURRENT
→ PRÓXIMO BLOCO
```

Não solicitar autorização a cada PR/bloco. Interromper somente em STOP condition real ou em ação que dependa de decisão humana/externa obrigatória, como autorização de release público, contratação/ativação de provider, KYC, credencial real, mudança destrutiva, operação financeira real ou alteração crítica de produção.

Nenhum bloco pode ser marcado PASS somente porque o código existe ou a CI está verde. Quando a fase exigir runtime real, provider real, integração real, staging real, produção real ou evidência externa, essa evidência deve existir.

---

## 2. AUTORIDADE DE CONTINUIDADE — CURRENT CANÔNICO

```text
PROJECT:
Kordena

REPOSITORY:
faabio3131/fm-ai-platform

ACTIVE BRANCH:
staging/kordena-premium

CURRENT HEAD:
57bbf18cacdc443d329308e6d9328c57aa55ed0a

OPEN PR:
nenhuma

MAIN:
5a17b0c8a1cb6dad576ce5b089166748b138900c

BRANCH RELATION:
staging 896 commits à frente da main
staging 0 commits atrás

RAILWAY PROJECT:
diplomatic-expression

RAILWAY SERVICE:
fm-ai-platform

RAILWAY STATUS:
SUCCESS

POSTGRES:
SUCCESS

PUBLIC RELEASE:
NÃO AUTORIZADO

PUBLIC SIGNUP/TRIAL:
desabilitado por padrão até gate final

FISCAL KORDENA:
Fiscal V1 atual permanece a autoridade fiscal

NFCORE:
FORA DESTE CRONOGRAMA

FM COMMAND:
produto funcionalmente concluído / pre-premium certificado
não reconstruir
```

Sempre que houver troca de chat, dispositivo, sessão ou handoff, este bloco deve ser reconciliado com GitHub/Railway antes de escrever código.

---

## 3. ESTADO JÁ CONCLUÍDO — NÃO REFAZER

### 3.1 Linha comercial KCA

```text
KCA-00 → KCA-16 = PASS
KCA-17 technical readiness = PASS / MERGED
KCA-G17 public release = BLOCKED_EXTERNALLY
```

O KCA-16 já comprovou em staging efêmero a jornada comercial completa com sandbox, incluindo signup, verificação, tenant/unidade, trial, entitlement, login, operação, expiração, paywall, checkout sandbox, webhook, reconciliation, subscription ACTIVE, restauração de acesso, atualização do FMCC e observabilidade.

O KCA-17 já comprovou readiness técnico, backup/restore isolado, schema, health, secret scan, regressão integral, segurança e rollback técnico.

Portanto: **não reconstruir KCA-00→17.** As fases deste cronograma são fechamento de release sobre o CURRENT atual e resolução dos bloqueios externos restantes.

### 3.2 Web Parity / funcionalidades

Os 33 Work Packages funcionais da V1 estão certificados internamente. Não reabrir funcionalidade certificada sem regressão objetiva no CURRENT.

### 3.3 Gemini e Google Maps

```text
Gemini platform_managed = HOMOLOGADO
Google Maps platform_managed = HOMOLOGADO
Platform Integration Control = IMPLEMENTADO
```

Regras absolutas:

- não configurar Gemini novamente;
- não homologar Gemini novamente;
- não configurar Maps novamente;
- não homologar Maps novamente;
- uso de Gemini/Maps em teste E2E é somente regressão de consumo de serviço já homologado;
- somente reabrir a integração se surgir regressão técnica objetiva.

### 3.4 Visual Premium

```text
Visual Premium Kordena = IMPLEMENTADO
```

Não executar redesign global. O que resta é QA visual final e correções cirúrgicas.

### 3.5 FM Command

```text
FUNCIONAL = DONE
F20 = DONE
F21 = DONE
PRE-PREMIUM = CERTIFIED
```

Não reconstruir o Command. Para o Kordena, falta somente fechar o runtime real Kordena ↔ Command e provar health/sync/provenance.

---

## 4. ESCOPO DESTA FINALIZAÇÃO

Este cronograma deve fechar tudo que seja necessário para declarar:

```text
KORDENA_V1_COMMERCIAL_READY = TRUE
```

Inclui:

- fechamento do CURRENT;
- regressão do delta posterior ao KCA-17;
- Gerente IA em jornada real governada;
- Kordena ↔ FM Command runtime live;
- billing SaaS de produção;
- e-mail transacional de produção;
- Termos/Privacidade/LGPD aplicáveis;
- suporte operacional;
- domínio/DNS/TLS/bindings;
- secrets/runtime config;
- observabilidade e alertas;
- backup/restore/rollback de release;
- Fiscal V1 no escopo de lançamento realmente suportado;
- integrações tenant-managed anunciadas no lançamento;
- segurança/RBAC/tenancy/dados;
- QA Visual Premium;
- E2E comercial final;
- release candidate;
- promoção staging → main;
- deploy do SHA certificado;
- release público controlado;
- estabilização e certificação final.

---

## 5. ÚNICA EXCLUSÃO DELIBERADA — NFCORE

Durante todo este cronograma é proibido iniciar:

```text
KordenaFiscalContractPack
FM Fiscal Bridge
NFCore client
NFCore cutover
dual-read
shadow traffic
NFCore migration rehearsal
writer freeze para NFCore
NFCore production activation
```

O Kordena será finalizado utilizando o Fiscal V1 atual.

Somente depois de:

```text
KORDENA V1 FINALIZADO
+
NFCORE FINALIZADO
+
NFCORE HOMOLOGADO EXTERNAMENTE
```

será aberto um novo projeto:

```text
CRONOGRAMA MESTRE — KORDENA → NFCORE CUTOVER
```

---

# 6. KF-00 — CURRENT FREEZE + RECONCILIAÇÃO FINAL

## Objetivo

Criar a baseline exata da release final e eliminar qualquer pendência falsa herdada de documentos históricos.

## Executar

1. confirmar `staging/kordena-premium@57bbf18...`;
2. confirmar `main@5a17b0c...`;
3. confirmar relação `ahead=896 / behind=0` ou registrar novo CURRENT se tiver mudado;
4. confirmar zero PR aberta inesperada;
5. confirmar deployment Railway do Kordena;
6. confirmar PostgreSQL saudável;
7. conferir migrations e schema atual;
8. conferir workflows obrigatórios;
9. conferir KCA Execution Tracker;
10. conferir State Ledger Web Parity;
11. confirmar KCA-00→16 PASS;
12. confirmar KCA-17 technical PASS;
13. confirmar Gemini HOMOLOGADO;
14. confirmar Maps HOMOLOGADO;
15. confirmar Visual Premium implementado;
16. confirmar ausência de NFCore no runtime Kordena;
17. listar apenas gaps de release ainda não provados.

## Proibido

- transformar histórico em pendência;
- reabrir Gemini/Maps;
- refazer KCA;
- iniciar redesign;
- iniciar NFCore.

## Gate KF-G00

```text
CURRENT_CONFIRMED
NO_PROJECT_DRIFT
NO_FALSE_PENDING_ITEMS
NO_UNEXPECTED_NFCORE_COUPLING
RELEASE_BASELINE_FROZEN
```

---

# 7. KF-01 — AUDITORIA DO DELTA PÓS-KCA-17

## Objetivo

O KCA-17 técnico foi certificado antes das últimas mudanças da branch. Auditar somente o delta posterior ao candidate KCA-17 até o HEAD atual, sem refazer o projeto inteiro.

## Foco obrigatório

- centralização `platform_managed` de Gemini/Maps;
- Control Plane do Command;
- mudanças de integração;
- correções de escopo operacional tenant/unidade;
- mappings de unidade → loja legada;
- compactação visual/workspaces;
- Gerente IA;
- rotas administrativas afetadas;
- qualquer migration pós-KCA17;
- qualquer alteração de auth/RBAC/step-up;
- qualquer alteração em billing/comercial/fiscal.

## Executar

- diff audit;
- targeted tests por área tocada;
- migration/schema validation;
- secret scan;
- dependency audit proporcional;
- regressão dos contratos afetados;
- confirmar que Gemini/Maps continuam HOMOLOGADOS e consumíveis pelo runtime atual sem nova homologação.

## Gate KF-G01

```text
POST_KCA17_DELTA_AUDITED
ZERO_UNEXPLAINED_CHANGE
ZERO_CRITICAL_REGRESSION
```

---

# 8. KF-02 — GERENTE IA / CORE — RELEASE E2E NO CURRENT

## Objetivo

Validar o Gerente IA no HEAD atual, reutilizando Gemini/Maps já homologados.

## Jornada

```text
usuário autorizado
→ Kordena
→ tenant/unidade server-side
→ Gerente IA
→ contexto governado
→ Gemini já homologado
→ ferramentas permitidas
→ dados canônicos
→ Maps já homologado quando necessário
→ resposta
→ provenance/correlation/audit
```

## Gate KF-G02

```text
GERENTE_IA_RELEASE_E2E_GREEN
ZERO_CROSS_TENANT
ZERO_AUTH_BYPASS
ZERO_SECRET_EXPOSURE
```

---

# 9. KF-03 — KORDENA ↔ FM COMMAND RUNTIME LIVE

## Objetivo

Fechar o bloqueio `fmcc_operational_runtime` sem reconstruir o Command.

## Arquitetura

```text
FM COMMAND
→ connector server-to-server
→ /v1/control-plane/fmcc
→ autoridades canônicas Kordena
```

Nunca:

```text
Command → SQL direto → banco Kordena
```

## Gate KF-G03

```text
KORDENA_COMMAND_RUNTIME_CONNECTED
HEALTH_PASS
SYNC_PASS
PROVENANCE_PASS
NO_DIRECT_DB_ACCESS
```

---

# 10. KF-04 — BLOQUEADORES COMERCIAIS EXTERNOS OBRIGATÓRIOS

Fechar com evidência real: billing SaaS de produção, e-mail transacional, Termos/Privacidade/LGPD, suporte operacional e baseline de clientes externos.

Nenhuma cobrança real deve ocorrer sem autorização explícita para o teste financeiro real.

## Gate KF-G04

```text
BILLING_PRODUCTION_READY
TRANSACTIONAL_EMAIL_READY
LEGAL_TERMS_READY
SUPPORT_READY
LIVE_CUSTOMER_BASELINE_KNOWN
```

---

# 11. KF-05 — DOMÍNIO + RUNTIME DE PRODUÇÃO + CONFIGURAÇÃO SEGURA

Domínio oficial: `kordenaia.com.br`.

Certificar DNS, HTTPS/TLS, bindings, CORS/cookies/callbacks, health/readiness, deploy identity, secrets, banco, migrations, backups, observabilidade e logs sanitizados.

## Gate KF-G05

```text
DOMAIN_DNS_TLS_PASS
PRODUCTION_RUNTIME_CONFIG_PASS
SECRETS_PASS
HEALTH_READY_PASS
```

---

# 12. KF-06 — FISCAL V1 + INTEGRAÇÕES DE LANÇAMENTO

NFCore está fora. Para Fiscal V1 e integrações tenant-managed, anunciar somente o que possuir evidência real; o restante permanece sandbox-only, configurável ou desabilitado/não anunciado.

Gemini e Maps já estão HOMOLOGADOS; apenas smoke de regressão quando necessário.

## Gate KF-G06

```text
FISCAL_V1_LAUNCH_SCOPE_TRUTHFUL
NO_FAKE_PROVIDER_HOMOLOGATION
ALL_ADVERTISED_INTEGRATIONS_EVIDENCED_OR_DISABLED
```

---

# 13. KF-07 — REGRESSÃO FUNCIONAL + SECURITY / TENANCY / DATA FINAL

Executar regressão funcional integral, RBAC, adversarial, migrations/schema, Ruff, mypy, Python, Node, ESLint, TypeScript, build, Playwright, accessibility, responsiveness, secret scan e dependency audit.

## Gate KF-G07

```text
FULL_RELEASE_REGRESSION_GREEN
BLOCKER = 0
CRITICAL = 0
HIGH = 0
MEDIUM_BLOCKING = 0
CROSS_TENANT = 0
SECRET_LEAK = 0
```

---

# 14. KF-08 — VISUAL PREMIUM FINAL QA

Não é redesign. Revisar todas as telas, controles clicáveis, responsividade e acessibilidade, sem alterar contratos/autoridades.

## Gate KF-G08

```text
PREMIUM_UI_FINAL_QA_PASS
ZERO_DEAD_CONTROLS
ZERO_FUNCTIONAL_REGRESSION
```

---

# 15. KF-09 — MASTER COMMERCIAL E2E FINAL

Executar no release environment, ainda com signup público fechado, a jornada completa de novo cliente até subscription ACTIVE/restauração de acesso/Command atualizado, sem SQL ou correção manual de dados.

Quando não houver autorização para dinheiro real, usar sandbox controlado até o limite permitido e manter o gate financeiro pendente; nunca fingir pagamento real.

## Gate KF-G09

```text
MASTER_COMMERCIAL_E2E_PASS
NO_MANUAL_DATA_FIX
NO_AUTHORITY_BYPASS
```

---

# 16. KF-10 — PRODUCTION RELEASE CANDIDATE

Pré-condição: KF-G00 → KF-G09 verdes.

Produzir candidate SHA imutável, manifests, relatórios, evidências E2E/runtime/billing/e-mail/Command/Fiscal, backup/restore, rollback e incident runbook. Public signup continua OFF.

## Gate KF-G10

```text
PRODUCTION_CANDIDATE_CERTIFIED
```

---

# 17. KF-11 — PROMOÇÃO `staging/kordena-premium` → `main`

Executar freeze, ancestry/diff, revisão de migrations/workflows, scans/audits/regressões/E2E/security/build/backup/rollback, PR formal, CI exact-head, auditoria, merge sem reescrever história, CI pós-merge e comprovação de deployment do SHA certificado.

## Gate KF-G11

```text
MAIN = CERTIFIED_KORDENA_RELEASE_SHA
DEPLOYMENT_SHA = MAIN_CERTIFIED_SHA
```

---

# 18. KF-12 — RELEASE PÚBLICO CONTROLADO

Somente após autorização humana explícita de release.

Ativar `PUBLIC_SIGNUP OFF → ON`, executar canary e manter kill switch para novos signups/trials.

## Gate KF-G12

```text
CONTROLLED_RELEASE_GREEN
```

---

# 19. KF-13 — ESTABILIZAÇÃO + CERTIFICAÇÃO FINAL

Observar incidentes, signup/provisioning/auth/trial/billing/webhook/entitlement/AI/Maps/Command/Fiscal/DB/retries/suporte/custo e reexecutar jornada real controlada.

Somente declarar `KORDENA_V1_COMMERCIAL_READY = TRUE` quando todos os gates aplicáveis estiverem PASS, produção estiver no SHA certificado, nenhum blocker/critical/high/cross-tenant/secret leak estiver aberto, integrações anunciadas possuírem evidência e NFCore continuar fora do runtime.

---

# 20. MATRIZ DE STATUS INICIAL DESTE CRONOGRAMA

| Área | Estado inicial | Ação |
|---|---|---|
| KCA-00→KCA-16 | PASS | preservar |
| KCA-17 técnico | PASS / MERGED | preservar |
| KCA-G17 release público | BLOCKED_EXTERNALLY | fechar neste cronograma |
| Gemini | HOMOLOGADO | não refazer |
| Google Maps | HOMOLOGADO | não refazer |
| Platform Integration Control | IMPLEMENTADO | validar regressão |
| Gerente IA | certificado historicamente | smoke/E2E release no current |
| Visual Premium | IMPLEMENTADO | QA final |
| Railway Kordena | SUCCESS | reconciliar release role/SHA |
| PostgreSQL | SUCCESS | backup/restore/release evidence |
| Command funcional | DONE | conectar runtime live |
| Billing SaaS produção | PENDING_EVIDENCE | obrigatório |
| E-mail transacional produção | PENDING_EVIDENCE | obrigatório |
| Termos/Privacidade | PENDING_EVIDENCE | obrigatório |
| Suporte | PENDING_EVIDENCE | obrigatório |
| DNS/TLS/app binding | PENDING_EVIDENCE | obrigatório |
| Cliente externo existente | PENDING_EVIDENCE | auditar runtime |
| Fiscal V1 launch scope | certificação interna | definir/provar escopo externo anunciado |
| Integrações tenant-managed | certificação varia | provar ou desabilitar/não anunciar |
| Public release authorization | DEFERRED | decisão humana final |
| NFCore integration | DEFERRED_BY_DESIGN | cronograma futuro |

---

# 21. EVIDÊNCIA OBRIGATÓRIA POR BLOCO

Nenhum bloco fecha sem registrar PROJECT, REPOSITORY, BRANCH, HEAD_INICIAL, HEAD_FINAL, PR, FILES_CHANGED, MIGRATIONS, SCHEMA, TESTS, PASS, FAIL, SKIP, CI_RUNS, SECURITY_RESULT, SECRET_SCAN, DEPENDENCY_AUDIT, DEPLOYMENT_SHA, DATABASE_STATUS, EXTERNAL_EVIDENCE, KNOWN_LIMITATIONS, ROLLBACK e GATE. Itens não aplicáveis devem ser `N/A + motivo`.

---

# 22. STOP CONDITIONS GLOBAIS

Interromper progressão e corrigir a causa em caso de cross-tenant/cross-unit, secret leak, auth/RBAC/step-up bypass, corrupção/perda de dados, duplicidade comercial, migration destrutiva não governada, SHA errado deployado, CI crítico vermelho, HIGH/CRITICAL aberto, provider/cobrança real não autorizado, webhook sem verificação, documentação divergente do CURRENT, acesso SQL direto Command→Kordena, fake homologation, feature anunciada sem evidência, NFCore prematuro, LLM mutacional sem gate humano/determinístico ou ausência de backup/rollback.

---

# 23. DEFINIÇÃO DE PRONTO — KORDENA V1

```text
FUNCTIONAL = PASS
COMMERCIAL = PASS
SECURITY = PASS
TENANCY = PASS
RBAC = PASS
DATA = PASS
GERENTE_IA = PASS
GEMINI = HOMOLOGATED
MAPS = HOMOLOGATED
COMMAND_RUNTIME = PASS
BILLING = PASS
TRANSACTIONAL_EMAIL = PASS
LEGAL = PASS
SUPPORT = PASS
DOMAIN_TLS = PASS
FISCAL_V1_LAUNCH_SCOPE = PASS/EXPLICITLY_LIMITED
ADVERTISED_INTEGRATIONS = PASS/EXPLICITLY_DISABLED
VISUAL_PREMIUM_QA = PASS
BACKUP_RESTORE_ROLLBACK = PASS
MASTER_COMMERCIAL_E2E = PASS
MAIN_PROMOTION = PASS
CONTROLLED_RELEASE = PASS
STABILIZATION = PASS
NFCORE_INTEGRATION = DEFERRED_BY_DESIGN
```

Resultado final:

```text
KORDENA_V1_COMMERCIAL_READY = TRUE
```

---

# 24. PRÓXIMO PROJETO APÓS O FECHAMENTO

Depois de o Kordena V1 estar comercialmente pronto e o NFCore estar finalizado/homologado, abrir `CRONOGRAMA MESTRE — KORDENA → NFCORE CUTOVER`. Nada disso pertence ao cronograma atual.
