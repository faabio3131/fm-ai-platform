# ADR-KCA-001 — Customer × Product Account × Tenant
Status: ADOTADO

## Contexto
O Kordena já usa `tenant_id` como escopo operacional, mas a Nova FM precisa identificar um cliente comercial global e sua relação com cada produto.

## Decisão
Criar três identidades distintas:
- `fm_customer_id`: cliente comercial global;
- `product_account_id`: relação customer-produto;
- `tenant_id`: isolamento operacional do produto.

## Alternativas
Reutilizar `tenant_id` como customer global foi rejeitado porque acoplaria identidade comercial à topologia interna de um produto.

## Consequências
Um customer pode consumir vários produtos; cada produto preserva seu tenant e domínio.

## CURRENT / migração
Adicionar estruturas comerciais sem remover `tenant_id` atual.

## Rollback
Forward-fix; não apagar dados comerciais automaticamente.
