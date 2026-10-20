# Kordena — Cron independente de expurgo de sessões / privilégio mínimo

**Escopo:** pré-comercial, homologação Kordena; não confundir o ambiente Railway chamado `production` com lançamento comercial.
**Objetivo:** expurgar linhas de `fm_operational_sessions_v1` já expiradas sem conceder ao job acesso à identidade, tenants, pedidos, pagamentos, auditoria ou outros dados.

## Contrato protegido
- A validade e revogação de sessões continuam verificadas pelo HTTP independentemente do Cron. A ausência de limpeza NÃO reativa sessões expiradas.
- Worker: `python -m scripts.cleanup_expired_operational_sessions`. Não possui servidor HTTP, endpoint, volume nem domínio público.
- Execução limitada: 20 lotes de 500 sessões (no máximo **10.000 exclusões** por rodada); cada lote é transacional, com `lock_timeout=2s` e `statement_timeout=15s`. Saída de logs apenas `expired_sessions_deleted=N`.
- Conta exclusiva, **nome fixo `fm_session_cleanup_v1`**, não superusuário, sem criação de roles, schemas ou databases, limite 2 conexões; `SELECT(session_id,expira_em)` e `DELETE` apenas em `public.fm_operational_sessions_v1`; `USAGE` schema e `CONNECT` database. Nunca dar SELECT(email,tenant_id,usuario_id), UPDATE ou acesso a `fm_usuarios_v1`.
- Antes de cada rodada o job confere automaticamente `current_user` e as permissões com `has_table_privilege/has_column_privilege`; se o login estiver com privilégio excessivo, **falha fechada sem apagar nada**. Jamais utilizar o `DATABASE_URL` do serviço Web.

## Sequência de ativação na Railway
1. Passar no gate PostgreSQL 16 `Kordena Session Cleanup Restricted PostgreSQL Gate` e em todas as regressões da PR; merge em `staging/kordena-premium`.
2. Criar segredo criptograficamente aleatório de no mínimo 40 caracteres em canal seguro; guardar no secret manager, sem commit, ticket, screenshot, log ou resposta de chat.
3. Com conexão **administrativa restrita à operação de provisionamento**, executar **uma única vez** `FM_AI_SESSION_CLEANUP_PASSWORD=... python -m scripts.provision_session_cleanup_role --provision`. O script falha se a role já existir; nunca faz rotação silenciosa. Retirar variável de provisionamento e credencial admin após uso.
4. Construir URI PostgreSQL interna para o login `fm_session_cleanup_v1` e o segredo criado. Usar `DATABASE_URL` *exclusivo do Cron*; não copiar o URL administrativo da aplicação nem persistir senha em GitHub.
5. Criar serviço separado `kordena-session-cleanup-cron` no mesmo projeto/ambiente Railway; vincular ao repositório/branch `staging/kordena-premium` ou SHA promovido. Configurar **startCommand** `python -m scripts.cleanup_expired_operational_sessions`, **cronSchedule** `0 5 * * *` (05:00 UTC; 02:00 de São Paulo) e política de restart `NEVER`. Não configurar preDeployCommand, healthcheck HTTP ou domínio. Criar variáveis `DATABASE_URL` restrito, `FM_AI_ENV=staging`, `FM_AI_TENANT_ID=session-cleanup`, `FM_AI_UNIDADE_ID=session-cleanup`, `FM_AI_DB_POOL_SIZE=1`, `FM_AI_DB_MAX_OVERFLOW=0`.
6. Antes de habilitar recorrência, validar `verify_database_role` no banco real, confirmar `rolsuper=false`, `rolcreaterole=false`, `rolcreatedb=false`, conta sem leitura de `fm_usuarios_v1` e sem UPDATE/INSERT de sessão. Um job real com zero exclusões é sucesso quando não há sessões expiradas. Não inserir sessões falsas no banco do Kordena para testar.
7. Acompanhar no Railway logs `expired_sessions_deleted=N`, conclusão do container com código 0, última execução do cron; observar erro `session_cleanup.database_role_not_least_privilege`, conexões e locks. Testar segunda execução idempotente quando possível; não confundir deploy SUCCESS com uma execução Cron real bem-sucedida.
8. **Rollback:** desabilitar `cronSchedule` ou serviço Cron e revogar credencial exclusiva, sem tocar na aplicação Web nem nos dados válidos. Não reverter a correção do HTTP que removeu DELETE por request.

## Proibições
- Não reutilizar usuário do PostgreSQL `postgres`, `fm-ai-platform` ou conta de migrations no Cron.
- Não expor Postgres em proxy TCP público para provisionamento, sem um gate de rede separado.
- Não rodar migrations no Cron nem guardar senhas em logs, repositório ou documentação.
- Não declarar o Cron ativo ou certificado por execução real até confirmação explícita nos logs Railway.

## Certificação
Evidência mínima: PR/HEAD e workflow verde, permissões SQL restritas comprovadas, configuração Railway do serviço Cron, deployment e **execução** com status conclusivo, log apenas de contagem agregada e escopo de banco correto. A contagem pode ser zero; não realizar DELETE forçado ou dados artificiais no ambiente real.
