# Reconciliação canônica de loja legada — SD-1D.3

Este procedimento existe para upgrades históricos que chegam à migration 0027 sem
evidência determinística de ownership. Ele nunca escolhe a primeira loja, não usa
defaults locais e não altera `insumos` diretamente.

## Sequência oficial

1. Preserve o banco original e trabalhe somente em cópia autorizada.
2. Defina explicitamente no ambiente `FM_AI_ENV`, `DATABASE_URL`,
   `FM_AI_TENANT_ID` e `FM_AI_UNIDADE_ID`, sem passar URL ou senha na linha de
   comando. O CLI rejeita test mode, defaults locais e o fallback SQLite local.
3. Execute `python -m scripts.migrate_v1`. No cenário sem ownership, o runner
   preserva as migrations já concluídas até 0026 e para fail-closed na 0027. A
   0020b cria/valida `lojas`; a 0021 cria `fm_unidade_loja_legacy_v1`.
4. Quando a 0027 parar por ausência de evidência, faça STOP e determine humanamente o
   tenant, a unidade, a loja e o nome da loja quando ela ainda não existir.
5. Execute a reconciliação explícita:

   ```powershell
   python -m scripts.reconcile_legacy_store_v1 `
     --admin-email PROPRIETARIO_AUTORIZADO `
     --tenant-id TENANT_AUTORIZADO `
     --unidade-id UNIDADE_AUTORIZADA `
     --loja-id ID_EXPLICITAMENTE_CONFIRMADO `
     --loja-nome "NOME_CONFIRMADO"
   ```

   A senha é lida por `getpass`. O usuário precisa ser `ADMINISTRADOR`, possuir
   `acesso_admin_sensivel=True` e a capability `loja_legada.reconciliar`. Omita
   `--loja-nome` quando a loja já existir, ou informe exatamente o nome canônico.
   O comando valida o ledger até 0026 e grava loja, mapping e auditoria na mesma
   transação. Repetir os mesmos valores é idempotente; qualquer conflito falha
   fechado.
6. Retome `python -m scripts.migrate_v1`. A 0027 fará o backfill determinístico e
   a 0028 aplicará o hardening de validade.
7. Confirme ledger até 0028, `integrity_check`, `foreign_key_check` e preservação
   dos dados históricos.

Não use esta ferramenta depois da 0027, não invente ownership e não reconcilie
diretamente em produção sem gate e autorização humana específicos.
