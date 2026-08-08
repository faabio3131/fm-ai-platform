# Central de Pedidos V1

## Objetivo e fonte de verdade

A Central oferece lista, filtros e detalhe operacional exclusivamente a partir de
`PedidoORM`, itens, observações e eventos V1. Ela não persiste uma projeção e nunca
cria Pedido a partir da tabela legada `vendas`. Uma Venda legada aparece apenas
quando existe vínculo PR8 com um Pedido real.

## Projeções, filtros e paginação

Os contratos são dataclasses imutáveis e preservam `Decimal` e instantes UTC. A
consulta sempre recebe `ContextoExecucao`, fixa tenant/unidade antes de aplicar
status, canal, intervalo, IDs, busca permitida, alertas e situação financeira.
A busca limita tamanho e escapa curingas. A paginação é obrigatória (máximo 100),
com ordenação `criado_em DESC, id DESC`; contagem de itens é subconsulta SQL e os
relacionamentos do detalhe usam `selectinload`, evitando N+1.
Os filtros derivados de situação financeira e existência de alertas são expressões
correlacionadas `EXISTS`/agregadas aplicadas antes de `COUNT`, `LIMIT` e `OFFSET`;
assim, total e páginas representam exatamente o mesmo conjunto filtrado.

## Financeiro e compatibilidade PR8

O resumo consulta Pagamento, VendaFinanceira, vínculo com Venda legada e a última
reconciliação no mesmo escopo. Somente `PagamentoORM.status == pago`, com valor
líquido suficiente, permite a situação `confirmado`. QR Pix, VendaFinanceira ou
Venda legada isolados não comprovam pagamento. Assim, canary mostra seus vínculos,
shadow continua sem financeiro inventado e Venda legada pura nunca aparece.

## Alertas

`PAGAMENTO_PENDENTE`, `RECONCILIACAO_DIVERGENTE` e
`PEDIDO_SEM_ATUALIZACAO` são determinísticos, timezone-aware e apenas informativos.
O limiar de inatividade é injetável e não representa SLA de cozinha.

## Comandos, RBAC, tenant e auditoria

Consultas exigem `pedido.visualizar`. Comandos usam somente transições já definidas
em `core.estados`, validam escopo, RBAC, versão e idempotência, atualizam através de
`RepositorioPedidosSQLAlchemy`, persistem evento com correlation ID e enviam a
auditoria minimizada ao repositório configurado. Não existe atualização SQL de
status na Central. ID conhecido fora do escopo resulta em não encontrado.

## Flag, rollout e rollback

`order_center_v1_enabled()` começa desligada. Nesta V1, ela somente liga quando
`FM_AI_TEST_MODE=1` **e** `FM_AI_ORDER_CENTER_V1=1`; não há controle no navegador.
O rollout inicial é teste isolado e posterior habilitação server-side poderá ser
adicionada em entrega própria. Desligar a flag remove a aba sem modificar Pedido,
pagamento ou legado.

Em produção, os comandos da UI permanecem indisponíveis até existir identidade
humana autenticada confiável. Exclusivamente em `FM_AI_TEST_MODE`, o contexto
server-side explícito permite demonstrar comando autorizado, negação RBAC,
optimistic locking, evento e auditoria; nenhum widget pode habilitar a flag.

## Métricas, riscos e não escopo

O contrato de métricas aceita contadores de consulta/erro/quantidade, comando
executado/negado, alerta por tipo e latência, sem labels de PII. A composição deve
ligá-lo ao coletor da implantação. Risco: as tabelas financeiras PR7/PR8 precisam
existir no schema em que a flag for habilitada.

Não fazem parte desta entrega: KDS, SLA de cozinha, mesas/comandas, garçom,
expedição, impressão, delivery, marketplaces, Mica, voz ou Gerente IA.
