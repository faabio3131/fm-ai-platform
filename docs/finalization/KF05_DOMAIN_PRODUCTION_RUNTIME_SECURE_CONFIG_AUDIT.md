# KF-05 — Certificação de domínio, runtime de produção e configuração segura

Data: 2026-09-30  
Branch base: `staging/kordena-premium`  
Baseline auditada: `577babfa977463929d66387c60f75fb68a079494`

## Resultado executivo

O trabalho interno de KF-05 foi auditado com evidência real de GitHub e Railway.

Status do gate KF-G05:

- `DOMAIN_DNS_TLS_PASS`: **BLOCKED_EXTERNAL / NOT PROVEN**
- `PRODUCTION_RUNTIME_CONFIG_PASS`: **PASS**
- `SECRETS_PASS`: **PASS**
- `HEALTH_READY_PASS`: **PASS**
- Backup/PITR: **EVIDENCE PENDING**
- Gate agregado KF-G05: **BLOCKED_EXTERNAL**

Nenhum PASS foi atribuído a DNS, TLS, binding de frontend ou backup sem evidência.

## Evidências confirmadas

### Runtime/deploy

Serviço Railway:
- projeto: `diplomatic-expression`
- serviço: `fm-ai-platform`
- environment interno: `production`
- source: `faabio3131/fm-ai-platform`
- branch implantada: `staging/kordena-premium`
- deployment auditado: `160fdf35-5ea2-415f-a2ed-197361d309e8`
- commit implantado: `577babfa977463929d66387c60f75fb68a079494`
- deployment: `SUCCESS`
- 1 réplica online, 0 crashes no estado auditado
- região da aplicação: `us-east4-eqdc4a`

O nome interno do environment Railway não é usado como autoridade de release público. A branch implantada permanece `staging/kordena-premium`.

### Migrations

O pre-deploy executa:

```text
python -m scripts.migrate_v1
```

No deployment auditado, o pre-deploy concluiu sem erro e registrou o schema comercial V1 já atualizado.

### Health/readiness

O serviço possui `/healthz` configurado como healthcheck Railway.

Evidência do deployment:
- etapa HEALTHCHECK: completed;
- Railway: `Healthcheck succeeded!`;
- `GET /healthz`: HTTP 200;
- resposta externa verificada no domínio Railway:
  `{"ok":true,"backend":"postgresql","detail":"database_ready"}`.

O endpoint consulta a saúde do banco e retorna 503 quando o backend não está pronto.

### Banco

Postgres Railway:
- service id `510d9999-7599-4fdb-b1ba-32881a993919`;
- deployment atual auditado: `SUCCESS`;
- 1 réplica online, 0 crashes;
- volume persistente montado em `/var/lib/postgresql/data`;
- conexão da aplicação por referência Railway `DATABASE_URL`;
- sem warnings/criticals ativos no estado auditado.

### Secrets e configuração segura

Variáveis sensíveis permanecem no secret/config store Railway; valores não foram registrados nesta certificação.

Foram confirmadas por nome:
- `FM_AI_SESSION_SECRET`;
- `FM_AI_SECRET_MASTER_KEY`;
- `FM_AI_FMCC_CONTROL_PLANE_TOKEN`;
- `DATABASE_URL`;
- `FM_AI_ENV`;
- escopo de tenant/unidade.

O audit de KF-04 já removeu a variável cujo nome aparentava conter material secreto.

A sessão web usa:
- cookie `HttpOnly`;
- `Secure` em runtime comercial;
- `SameSite=Lax`.

CORS localhost é habilitado apenas fora de staging/production; runtime comercial permanece fail-closed para essas origens.

### Logs e observabilidade

Foram auditados logs recentes de build/deploy sem identificar exposição de tokens, passwords, API keys ou connection strings.

Railway mantém:
- logs de build/deploy;
- healthcheck;
- estado de réplicas;
- notificações de falha/crash;
- histórico de deployments.

No estado auditado não existem alertas ativos.

## Domínio oficial

Domínio previsto:

```text
kordenaia.com.br
```

A API específica `list_domains` do Railway confirma um custom domain cadastrado:

- domain id: `f9865c90-788c-4865-8371-6e229d84a13e`;
- domain: `kordenaia.com.br`;
- target port: `8080`.

Entretanto, a resolução pública do domínio não pôde ser comprovada nos verificadores utilizados. Portanto DNS/TLS não recebe PASS.

Além disso, o custom domain está associado ao serviço FastAPI. O runtime FastAPI retorna 404 em `/`, enquanto o frontend Kordena existe separadamente em `web/` como aplicação Next.js. Assim, o requisito de **domínio de frontend** permanece não provado e não deve ser confundido com o binding do backend.

## Public signup

`FM_AI_PUBLIC_SIGNUP_ENABLED` não está definido no runtime auditado. Pelo contrato atual, o default é `false`.

Portanto o cadastro público permanece fechado.

## Backups/PITR

O Postgres usa volume persistente, porém a configuração de schedules de backup e PITR não é exposta pelas APIs Railway disponíveis nesta sessão.

Railway documenta que:
- schedules são verificados na aba Backups do serviço;
- PITR pode ser verificado pelo comando `railway postgres pitr status`.

Sem essa evidência, backup/restore/PITR não é certificado.

## Pendências externas/operacionais para fechar KF-G05

1. provar resolução DNS pública de `kordenaia.com.br`;
2. provar emissão/estado TLS válido;
3. definir e provar o binding correto do domínio oficial ao frontend Kordena;
4. validar HTTP→HTTPS e headers no domínio oficial após propagação;
5. validar callback/base URLs e links de e-mail quando os providers de KF-04 forem configurados;
6. obter evidência de backup schedule e/ou PITR, conforme política adotada;
7. manter `PUBLIC_SIGNUP` desligado até os gates comerciais anteriores estarem verdes.

## Decisão

KF-05 não é promovido a PASS total.

A infraestrutura interna comprovada está saudável e apta a continuar as atividades independentes do Cronograma Mestre. O fechamento agregado permanece bloqueado exclusivamente onde falta evidência externa/operacional real.
