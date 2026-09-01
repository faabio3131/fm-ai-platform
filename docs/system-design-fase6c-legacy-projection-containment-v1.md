# F6-C — System Design — Legacy Projection Containment

**Base de abertura:** `c9a2a06fa68bb2404e0fd7b9dbbc058cd334af68`  
**F6-A/F6-B:** fechadas e verdes.

## Objetivo

Conter o legado como borda de compatibilidade. O caminho canônico não pode
receber capacidades de execução LEGACY nem de baixa de estoque legado.

## Capability boundary

O adapter completo `LegacyPDVSQLAlchemyAdapter` continua existindo somente
porque `LEGACY` permanece o rollback operacional do canary.

O executor autoritativo recebe
`PonteProjecaoCompatLegadaPDVSQLAlchemy`, que expõe somente:

- validação/leitura necessária para ancorar o snapshot de cutover;
- projeção idempotente da Venda legada;
- projeção idempotente de cashback legado.

A ponte não expõe `executar()` nem `baixar_estoque_uma_vez()`.

## Estoque

`application/pdv_legacy_projection.py` deixa de possuir qualquer caminho de
baixa de estoque. Liquidação financeira não pode alterar saldo físico legado.

A única projeção transitória de consumo legado continua em
`application/legacy_stock_projection.py`, acionada depois que o ledger
canônico registra o consumo no marco real de produção/KDS. O ledger canônico
permanece a autoridade.

## Financeiro

Venda/cashback legados são projeções de compatibilidade e não criam decisão de
pagamento. Pedido/Pagamento/VendaFinanceira canônicos permanecem autoridade.

## Rollback

O modo `LEGACY` não é removido nesta etapa. O full adapter continua disponível
apenas no ramo LEGACY. A contenção se aplica ao caminho autoritativo.

## Gate

F6-C exige compile, Ruff, mypy, fitness de capability boundary e regressões de
canary dinheiro, Pix assíncrono, total zero e rollback.
