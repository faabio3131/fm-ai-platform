# KCA-12 — Implementation Record

## Escopo

FM Control Center — Integração + Commercial Control Plane, conforme o Prompt Mestre Kordena/FM Control Center e o Cronograma Mestre KCA.

O KCA-12 integra o Kordena ao FM Control Center por contratos governados sem transferir a autoridade operacional/comercial do Kordena para o FMCC.

## Candidates funcionais certificados

### Kordena / FM Commercial Platform

- Repositório: `faabio3131/fm-ai-platform`.
- Base: `staging/kordena-premium` @ `87f4e2f47abcc5bd0be372c477bec612aed0a482`.
- Branch: `feat/kordena-commercial-kca12-fmcc-control-plane`.
- PR: #128 — OPEN/DRAFT durante a certificação.
- Candidate funcional: `b35ba198ecd9a667f0473829c16562e2474a1f31`.

### FM Control Center

- Repositório canônico: `faabio3131/FM-CONTROL-CENTER`.
- Base da integração: `main` @ `9632dd3871790a8b709fa5bc11211b9649b943fa`.
- Branch: `feat/fmcc-kordena-commercial-control-plane`.
- PR: #16 — OPEN/DRAFT durante a certificação.
- Candidate funcional: `5d4843d4bd5ac403c59a0d491413f4482a0318f9`.

Branches históricas que incorporavam artefatos FMCC no Kordena foram auditadas e classificadas como históricas/conflitantes com a decisão posterior de separação. Nenhum Shared Core cross-product foi restaurado.

## Persistência / schema

- Nenhuma migration nova foi necessária no KCA-12 do Kordena.
- Nenhuma migration nova específica da integração Kordena foi necessária no FMCC.
- O Kordena preserva o schema baseline em **132 tabelas**.
- SHA-256 do baseline Kordena: `9fccb9f26f04f92fb104f0eebef885c0f5a8556ef9816670e8e4fafdf594beb3`.
- Migration manifest: PASS.
- Schema baseline: PASS.

## Read model / contrato canônico

O Kordena expõe `kordena.fmcc.commercial.v1` por boundary server-to-server autenticado.

A projeção fornece, sem contato PII/credenciais:

- clientes e classificação `INTERNAL_TEST`;
- Product Accounts e tenant associado;
- trials, inclusive início, expiração, conversão/revogação quando existentes;
- assinaturas e estados atuais, incluindo ACTIVE/PAST_DUE/SUSPENDED/CANCELED;
- preço contratado e período atual;
- transações de billing;
- pagamentos confirmados e falhas;
- referência segura de provider account;
- reconciliation status;
- entitlement, revisão, validade, modo de acesso e stale state;
- contagens minimizadas de usuários/memberships e unidades;
- catálogo dos quatro planos canônicos;
- facts correlacionáveis para ingestão pelo Integration Fabric.

Contas `INTERNAL_TEST` permanecem visíveis administrativamente, mas são excluídas dos facts destinados a KPIs comerciais.

## Dashboard FMCC

A base funcional do dashboard KCA-12 apresenta dados canônicos disponíveis para:

- clientes;
- trials ativos;
- assinaturas ativas;
- past due/vencimentos;
- pagamentos confirmados;
- falhas de pagamento;
- usuários;
- unidades;
- catálogo/planos.

Campos ainda sem fonte ou semântica aprovada não são convertidos em zero. Permanecem explicitamente **Indisponíveis** com dependência governada:

- MRR;
- ARR;
- churn;
- inadimplência monetária;
- saúde operacional;
- custos;
- suporte.

Saúde/observabilidade avançada permanece dependência do KCA-13. Custos e suporte permanecem dependentes de fontes dedicadas. Nenhuma métrica foi fabricada.

A métrica `subscription.active.count` do Metric Engine requer semântica stateful/as-of para não contar assinaturas posteriormente canceladas em armazenamento append-only. O KCA-12 usa o snapshot canônico atual para o dashboard; não foi introduzido um fact incorreto apenas para satisfazer o registry.

## Administração governada

O FMCC administra somente o catálogo comercial autorizado do Kordena:

- `KORDENA_PLAN_A`;
- `KORDENA_PLAN_B`;
- `KORDENA_PLAN_C`;
- `KORDENA_PLAN_D`.

O fluxo é:

```text
FMCC
→ command server-side
→ boundary Kordena
→ AplicacaoCatalogoComercialV1
→ validação/transição canônica
→ persistência canônica
→ audit trail
→ outbox/read model
```

Cobertura certificada via boundary FMCC inclui:

- nome;
- descrição;
- benefícios/capabilities;
- limites;
- preço;
- periodicidade;
- promoção;
- validação;
- preview/diff;
- publicação;
- data futura de ativação;
- versionamento;
- idempotência;
- audit trail.

O control plane **não expõe** mutações de customer ou Product Account e não possui SQL/ORM de escrita próprio.

## Autoridade canônica

O boundary `http_api/fmcc_commercial_control.py` instancia e delega para `AplicacaoCatalogoComercialV1`.

Fitness test dedicado prova:

- uso da autoridade canônica para create/validate/preview/publish de plano, preço e promoção;
- ausência de `sqlalchemy`, `infra.comercial`, `.execute(` e `.add(` no boundary;
- ausência de comandos de mutação de customer/Product Account no catálogo de ações FMCC.

Teste de integração prova que repetir o mesmo comando de criação com a mesma idempotency key:

- retorna o mesmo `plan_version_id`;
- mantém uma única versão persistida;
- mantém um único registro canônico de auditoria;
- preserva `version_number = 1`;
- registra o ator individual propagado pelo FMCC.

Nenhuma segunda autoridade comercial foi criada.

## Segurança

### Kordena boundary

- Bearer token técnico dedicado, comparação constant-time;
- ausência/configuração inválida: fail-closed;
- token nunca retorna em payload;
- step-up recebido deve ser fresco (janela máxima de 15 minutos);
- actor limitado a owner/admin;
- payloads Pydantic com `extra="forbid"`;
- correlation/idempotency preservadas.

### FMCC

- `commercial:write` somente owner/admin;
- leitura comercial separada da mutação;
- password reauthentication server-side via Better Auth;
- prova de step-up vinculada ao usuário da sessão;
- publicação exige preview/diff antes da confirmação da UI;
- Audit Ledger registra success/denied/failure;
- secret reference fixo: `env:FMCC_KORDENA_CONTROL_PLANE_TOKEN`;
- origins Kordena restritas por `FMCC_KORDENA_ALLOWED_ORIGINS`;
- apenas `FMCC_KORDENA_CONTROL_TENANT_ID` pode usar o conector Kordena;
- source de outro tenant é negada;
- tentativa de apontar para outro segredo de ambiente é negada;
- tentativa de exfiltrar token para origin não allowlisted é negada;
- snapshot incompleto/contract drift falha fechado em vez de virar zero.

## Cross-tenant

Durante a auditoria foi encontrado um risco real: o `ConnectorRuntime` genérico poderia, sem um segundo controle, permitir que outro tenant FMCC registrasse uma source Kordena própria e tentasse usar o token global.

Correção aplicada no conector:

- o tenant corrente precisa ser exatamente o tenant interno configurado em `FMCC_KORDENA_CONTROL_TENANT_ID`;
- a proteção vale para health, sync, snapshot e command;
- teste adversarial com source e token válidos em outro tenant é negado.

Resultado: **cross-tenant fail-closed**.

## Integration Fabric / events / replay

O FMCC reutiliza o Integration Fabric canônico:

- Source Registry tenant-scoped;
- Connector Runtime;
- idempotency key por sync;
- durable sync execution;
- canonical facts;
- dedupe por tenant/source/externalId/mappingVersion;
- retry somente para erros classificados;
- provenance/correlation;
- falha externa sanitizada.

A regressão KCA-04/KCA-10 continua cobrindo duplicate/out-of-order/replay nas autoridades de entitlement e billing events. O KCA-12 não cria um segundo mecanismo de eventos.

## Evidência Kordena — candidate funcional

Candidate: `b35ba198ecd9a667f0473829c16562e2474a1f31`.

### KCA targeted

- **202 passed**
- **1 warning**

### Full Python regression

- **1803 passed**
- **5 skipped**
- **101 warnings**

### Static / schema

- compileall: PASS
- Migration manifest: PASS
- Schema baseline: PASS — 132 tabelas
- Ruff: PASS
- mypy: PASS — 81 source files
- diff whitespace: PASS

### Web

- ESLint: PASS
- TypeScript: PASS
- Node tests: **16 passed / 0 failed / 0 skipped**
- Next production build: PASS

### CI

No candidate funcional:

- Kordena KCA Commercial Gate: SUCCESS
- WP-031 Master Gate: SUCCESS
- WP-031J Web UX Functional: SUCCESS
- WP-031L Regression Channel Parity: SUCCESS
- Web Parity WP022 Certification: SUCCESS
- Commercial Runtime Readiness V1: SUCCESS
- PR Superseded Runs Cleanup: SUCCESS
- Vercel: SUCCESS

Resultado: **7/7 GitHub Actions SUCCESS + Vercel SUCCESS**.

## Evidência FMCC — candidate funcional

Candidate: `5d4843d4bd5ac403c59a0d491413f4482a0318f9`.

- FMCC Foundation Gate: SUCCESS.
- Lint: PASS.
- Typecheck: PASS.
- Migration/schema verification: PASS.
- Versioned migration application: PASS.
- Test Files: **33 passed**.
- Tests: **118 passed**.
- KCA-12 connector tests: **6 passed**.
- KCA-12 commercial security tests: **3 passed**.
- Next production build: PASS.
- Docker image build sem runtime secrets: PASS.
- Runtime dependency audit com `--audit-level=high`: PASS.
- Auditoria npm registrou 4 advisories moderados transitivos de esbuild; nenhum HIGH/CRITICAL bloqueou o gate.

## Diff audit

Confirmado:

- sem acesso direto do FMCC ao banco operacional do Kordena;
- sem autoridade comercial duplicada;
- sem segredo real versionado;
- sem provider financeiro real;
- sem cobrança real;
- sem preço hardcoded no frontend como autoridade;
- sem alteração de `main` do Kordena;
- sem KCA-13 antecipado integralmente;
- sem Core cross-product restaurado.

## Pendências reais fora do KCA-G12

Não fazem parte do KCA-G12 e permanecem explícitas:

- configurar valores reais de runtime apenas em ambiente autorizado;
- homologar provider/billing real em gate próprio;
- definir/calcular MRR/ARR/churn/inadimplência quando suas semânticas/fontes forem aprovadas;
- KCA-13 Observability/Antiabuse/FinOps;
- bloco cognitivo do FMCC, separado do KCA-G12;
- rollout público e produção real continuam proibidos.

## Gate

**KCA-G12: PASS no conjunto de candidates funcionais Kordena `b35ba198ecd9a667f0473829c16562e2474a1f31` + FMCC `5d4843d4bd5ac403c59a0d491413f4482a0318f9`.**

Este registro e o tracker criam HEAD(s) documentais novos. O KCA-G12 somente será considerado **encerrado** depois da recertificação desses HEADs documentais, conforme o Prompt Mestre.
