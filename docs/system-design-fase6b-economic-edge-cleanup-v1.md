# F6-B — System Design — Economic Edge Cleanup

**Base de abertura:** `8ce3eba882d65af78822a35dae23c97e0e8ad628`  
**F6-A:** fechada, 20/20 verde + reexecução extra PR11 E2E verde.

## Objetivo

Eliminar o fallback histórico do PDV autoritativo para LEGACY quando o total líquido do pedido é zero, sem criar Pagamento, obrigação, transação, critério ou VendaFinanceira fictícios.

## Regra econômica

Pedido zerado é válido apenas quando a composição já produziu total líquido zero de forma legítima (ex.: cashback cobrindo integralmente o subtotal). O checkout:

1. cria Pedido canônico;
2. reserva estoque normalmente;
3. não cria obrigação financeira;
4. transiciona o Pedido de `aguardando_confirmacao` para `confirmado` por critério explícito `saldo_zero_sem_obrigacao`;
5. mantém projeção legada idempotente apenas para compatibilidade;
6. não cria `VendaFinanceira` nem link financeiro legado;
7. registra reconciliação com `pagamento_id=None` e `venda_financeira_id=None`.

## Invariantes

- total positivo continua exigindo obrigação de pagamento;
- total zero nunca usa Fake para simular liquidação;
- estoque continua apenas reservado no checkout;
- consumo físico continua pertencendo ao início da produção/KDS;
- rollback da UoW remove Pedido, reserva, projeções, eventos e auditoria juntos;
- replay do mesmo checkout não duplica Pedido, venda legada, cashback ou reconciliação;
- projeção legada de venda zerada usa `forma_pagamento=Cashback`, evitando afirmar Pix/cartão/dinheiro que não ocorreu.

## Fora de escopo

- remoção completa do adapter legado: F6-C;
- Commercial Runtime E2E: F6-D;
- homologação PagBank/Mercado Pago: externa, não mascarada;
- migrations: nenhuma necessária para F6-B.
