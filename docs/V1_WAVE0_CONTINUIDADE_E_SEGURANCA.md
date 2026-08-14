# V1 — Continuidade, autenticação e segredos

Este documento é o runbook operacional da Onda 0. Ele define o que precisa estar
verdadeiramente configurado antes de promover módulos da V1 para runtime comercial.

## 1. Banco comercial

Em `staging` e `production` o sistema exige:

- `FM_AI_ENV=staging` ou `FM_AI_ENV=production`;
- `DATABASE_URL` apontando para banco servidor;
- `FM_AI_TENANT_ID` e `FM_AI_UNIDADE_ID` explícitos;
- SQLite comercial é recusado por padrão.

Exemplo de driver suportado pela fundação atual:

```text
postgresql+psycopg://usuario:senha@host:5432/gerente_ai
```

A URL é configuração de infraestrutura e não deve ser exibida em tela ou log.

## 2. Migrações

Antes de iniciar uma instância comercial:

```bash
python -m scripts.migrate_v1
```

O runner mantém `fm_schema_migrations`, aplica somente versões pendentes e não
executa downgrade destrutivo automaticamente.

## 3. Primeiro administrador

Depois das migrações:

```bash
python -m scripts.create_admin_v1 --email proprietario@empresa.com
```

A senha é solicitada de forma interativa por `getpass` e nunca deve ser passada
como argumento de linha de comando, variável versionada ou arquivo do repositório.

## 4. Referências de segredos

Tokens e chaves de Meta, WhatsApp, iFood, 99Food, Keeta, Maps e gateways não devem
ser persistidos em texto puro. O banco guarda apenas referências como:

```text
env:IFOOD_CLIENT_SECRET
env:META_WHATSAPP_TOKEN
env:GOOGLE_MAPS_API_KEY
```

A camada `SecretStore` resolve a referência no momento de uso. A rotação cria uma
nova versão de referência, desativa a anterior e registra usuário e correlation ID.

## 5. Backup

Criar backup:

```bash
python -m scripts.backup_v1 /backups/gerente-ai-YYYYMMDD-HHMM.dump
```

Cada backup gera manifesto com SHA-256 e tamanho. Um arquivo sem manifesto válido
ou com checksum divergente não pode ser usado em restore.

A política local padrão da fundação é configurável por:

- `FM_AI_BACKUP_KEEP_LAST` — padrão técnico: 30;
- `FM_AI_BACKUP_MAX_AGE_DAYS` — padrão técnico: 90;
- `FM_AI_TARGET_RPO_MINUTES` — meta inicial de engenharia: 60;
- `FM_AI_TARGET_RTO_MINUTES` — meta inicial de engenharia: 120.

RPO/RTO são **metas de operação**, não garantias produzidas apenas pelo código. O
go-live comercial fica bloqueado até o ambiente real demonstrar, em exercício de
restore, que consegue atender às metas configuradas.

## 6. Restore

O restore exige o nome exato do banco-alvo:

```bash
python -m scripts.restore_v1 /backups/arquivo.dump --confirm-database gerente_ai
```

Procedimento obrigatório de contingência:

1. declarar incidente e impedir novas escritas no banco comprometido;
2. identificar o último backup com manifesto e checksum válidos;
3. restaurar primeiro em ambiente isolado quando o incidente permitir;
4. executar migrations pendentes após o restore;
5. validar healthcheck, contagem/amostras de dados e login administrativo;
6. validar pedido, pagamento, estoque e financeiro antes de liberar tráfego;
7. registrar horário do último dado recuperado (RPO observado) e tempo total de
   recuperação (RTO observado);
8. somente então reabrir o ambiente comercial.

## 7. Regra de ativação de módulos

Fora de `FM_AI_TEST_MODE`, uma flag de módulo não basta. O registry exige também
que todos os adapters reais requeridos estejam declarados como configurados. Isso
impede que uma UI respaldada por `Runtime*Teste`, fake ou sandbox seja promovida
acidentalmente para um restaurante.

Exemplo conceitual:

```text
FM_AI_DELIVERY_V1=1
FM_AI_ADAPTER_ORDERS=sqlalchemy
FM_AI_ADAPTER_PAYMENTS=sqlalchemy
FM_AI_ADAPTER_DELIVERY=production
FM_AI_ADAPTER_AUTH=production
```

O nome `production`/`sqlalchemy` nesse registry significa que a composição real foi
instalada; ele não substitui os testes de integração nem as credenciais necessárias.

## 8. Gate de go-live da Onda 0

A Onda 0 só pode ser marcada como concluída quando:

- o app usa o engine comercial e não o `create_engine` SQLite ad-hoc;
- login real substitui o usuário fixo no runtime comercial;
- menus e ações respeitam RBAC/tenant/unidade;
- campos legados de segredo não são a fonte autoritativa em produção;
- backup + restore foram exercitados no ambiente de homologação;
- workflow da Onda 0 e suíte completa estão verdes.
