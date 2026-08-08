# Ledger e reserva de estoque V1

## Limites e modelo

Este módulo é novo, opt-in e não está ligado ao PDV, Venda, KDS, Mica, cashback ou
estoque legado. `InsumoEstoque`, `MovimentoEstoque`, `SaldoEstoque`,
`ReservaEstoque`, snapshots e resultados são contratos puros e imutáveis. Venda
reconhece o financeiro, mas **nunca** chama a baixa. Pedido pode reservar e o
início/aceite de produção consome no máximo uma vez.

## Ledger e saldos

O ledger é append-only: não há API de update ou delete. Correções são novos
movimentos `compensacao`, com `movimento_original_id` em metadata sanitizada.
Consultas sempre exigem tenant e unidade e têm ordem `(occurred_at,
movimento_id)`. O saldo é derivável do histórico:

* `saldo_fisico`: entradas, consumos, perdas, devoluções, ajustes e compensações;
* `saldo_reservado`: reservas ainda não consumidas ou liberadas;
* `saldo_disponivel = saldo_fisico - saldo_reservado`.

Reserva não é consumo. Consumo reduz físico e resolve o reservado; liberação só
resolve o reservado. Saldo físico ou disponível negativo é rejeitado, salvo
override explícito em uma API interna, autorizado e auditável.

## Snapshot, reserva, consumo e liberação

A decisão guarda um `SnapshotFichaEstoque` com pedido, item, produto, insumo,
quantidade unitária/total, unidade, versão e instante. Alterar a ficha corrente
não muda o snapshot histórico. `reservar_estoque` agrega necessidades por insumo
e executa verificação e append sob a mesma seção atômica. `consumir_reserva`
resolve uma reserva ativa; repetição retorna o resultado lógico sem nova baixa.
Cancelamento anterior à produção usa `liberar_reserva` e preserva a reserva
original. Cancelamento posterior não cria devolução automática.

## Perdas, devoluções, ajustes e compensações

Perda, desperdício, quebra, vencimento e erro de produção são movimentos
explícitos, sempre com motivo, ator, correlação e permissão. Devolução somente é
entrada se elegível, inspecionada e permitida pela política; alimento preparado
normalmente deve virar ocorrência/perda. Ajustes positivos/negativos e
compensações exigem motivo, idempotência e `estoque.ajustar`. O Gerente IA pode
preparar uma solicitação, mas não confirma mutação crítica sem humano.

## Idempotência, concorrência e isolamento

Além da chave explícita, a unicidade lógica cobre tenant, unidade, origem tipo e
ID, tipo do movimento, insumo e versão da origem. Reuso com conteúdo divergente
é conflito. O repositório em memória usa lock reentrante ao redor da decisão
inteira. O SQL usa saldo materializado com versão e compare-and-swap; conflito
recebe erro de concorrência, sem retry cego. Assim, duas reservas de 7 sobre 10
não podem reservar 14. Não há `sleep` em testes.

Toda busca inclui tenant e unidade. Um identificador de outro escopo produz o
mesmo resultado de recurso ausente, evitando enumeração IDOR. Tenant e unidade
dos contratos são congelados.

## Eventos e auditoria

Os serviços retornam envelopes da infraestrutura de eventos, sem publicação
externa: `estoque.reservado`, `estoque.baixado`, `estoque.liberado`,
`estoque.perda_registrada`, `estoque.ajustado` e `estoque.devolvido`. Preservam
evento, agregado, origem no payload, tenant/unidade, correlação, causação,
idempotência, instante e versão. Audit intents contêm ator, papel efetivo, ação,
insumo, quantidade, origem, motivo, política, correlação e timestamp. Metadata é
sanitizada e nunca deve receber credenciais ou dados de pagamento.

## Persistência, migration e rollback

A migration cria somente `estoque_ledger_v1`, `estoque_saldos_v1` e
`estoque_reservas_v1`, seus índices, checks e unique constraints. Não lê
`DATABASE_URL`, não altera tabelas antigas, não faz backfill e não converte
histórico. `upgrade` e `downgrade` aceitam somente SQLite em memória ou arquivo
cujo nome declare teste e recusam expressamente `banco_erp_local.db`. Downgrade
remove apenas essas três tabelas V1 em banco efêmero autorizado.

## Limitações SQLite, riscos e não escopo

SQLite não representa todos os lock levels de bancos servidor. A regra de corrida
é validada deterministicamente com threads e repositório concorrente, enquanto o
adapter SQL valida o update condicional. Antes de ativação futura, o CAS deve ser
testado no SGBD escolhido e transações multi-insumo devem receber implementação
SQL completa (a V1 SQL expõe o ledger/saldo, enquanto a orquestração pura usa a
porta atômica). Override negativo existe só como parâmetro interno e deve ganhar
workflow de aprovação persistido antes de qualquer integração.

Não fazem parte desta entrega: UI, ativação de flags, integração com Venda/PDV,
KDS, Mica, cashback, migração de saldo histórico, publicação externa, deploy ou
alterações no banco real. O principal risco futuro é integrar consumo em mais de
um ponto; a única origem admitida deve continuar sendo a transição de produção.
