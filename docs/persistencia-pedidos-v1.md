# Persistência aditiva de Pedidos V1

## Objetivo e compatibilidade

Esta entrega adiciona persistência isolada para `Pedido`, itens, adicionais,
observações e eventos. Ela não importa os novos módulos em `app.py`, não ativa
dupla escrita e não altera `Venda`, PDV, estoque, cashback, CRM, dashboard ou
Mica. Pedido não é Venda. Vendas existentes continuam válidas e não recebem
vínculo nem backfill.

As flags `orders_shadow_write`, `orders_read_projection` e
`orders_authoritative` existem apenas como contratos e têm valor padrão `false`.

## Modelo e campos

* `pedidos_v1`: chave composta `tenant_id, unidade_id, id`; origem, canal,
  status, referência opcional de cliente, timestamps UTC, versão, correlation ID,
  chave de idempotência e `subtotal`, `descontos`, `taxas`, `total`.
* `itens_pedido_v1`: escopo e pedido, ordem, referência opcional de produto,
  snapshot do nome, quantidade, preço, subtotal, observação e versão da ficha.
* `adicionais_item_pedido_v1`: escopo e item, ordem, snapshot de nome,
  quantidade, preço e subtotal.
* `observacoes_pedido_v1`: escopo e pedido, ordem, texto e criação.
* `eventos_pedido_v1`: event/pedido/type, escopo, correlation/causation,
  idempotência, ocorrência, payload JSON e versão. Eventos são armazenados, mas
  não publicados.

Filhos usam FKs compostas, de modo que uma relação não pode cruzar tenant ou
unidade. Não há FK para as tabelas legadas de cliente/produto: seus IDs são
referências nominais opcionais, e o item guarda o snapshot histórico necessário.

## Isolamento, índices e constraints

Toda operação do repository exige `tenant_id` e `unidade_id`; não existe busca
por ID global nem método de hard delete. Cancelamento futuro será transição de
estado. Os índices de pedido são `(tenant_id, unidade_id, id)`,
`(tenant_id, unidade_id, status)`, `(tenant_id, unidade_id, criado_em)` e
`(tenant_id, unidade_id, idempotency_key)`. Filhos e eventos possuem índices
escopados para seus pais.

A idempotência de criação é única por tenant/unidade/chave. Repetição com o
mesmo conteúdo retorna o registro existente; conteúdo diferente lança
`conflito_idempotencia`. Ordens são únicas dentro do pai, quantidades e versões
possuem checks positivos. Eventos têm ID composto escopado e chave idempotente
única por escopo.

## Decimal e concorrência

Valores usam `Dinheiro` no domínio e `Numeric(14, 2)` no ORM. Float é recusado
pelo contrato, e a conversão usa `Decimal`, preservando centavos. Atualizações
executam `UPDATE` condicionado por tenant, unidade, ID e versão esperada. Zero
linhas alteradas lança o erro estável `pedido_concorrente`; não há overwrite
silencioso.

## Migration, rollback e segurança

`migrations/orders_v1.py` realiza somente `create_all` das cinco estruturas
novas. A função exige uma Engine SQLite explicitamente fornecida e aceita apenas
memória ou arquivo cujo nome indique teste; ela não lê `DATABASE_URL`. O
downgrade remove exclusivamente as cinco tabelas novas e é permitido somente
sob a mesma proteção, para banco efêmero/teste. A migration não toca tabelas,
colunas, valores Float ou dados históricos legados.

## Riscos e não escopo

SQLite não oferece o mesmo perfil de concorrência de um banco de produção; a
comparação de versão protege contra perda de atualização, mas o dialeto alvo
deverá ser homologado antes de ativação. Não fazem parte desta entrega:
publicação/outbox persistente, worker, Kafka/Redis/Celery, KDS, pagamento,
estoque, cashback, Venda, migração de legado, UI ou ativação das flags.
