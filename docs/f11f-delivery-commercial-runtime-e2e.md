# F11-F — Delivery Próprio Commercial Runtime E2E

## Autoridade

Documento Mestre + issue #84 + `docs/inventario-fase11-delivery-proprio-cutover-v1.md`.

A F11-F não cria novo domínio. Ela prova no runtime comercial o patrimônio concluído em F11-B/C/D/E.

## Escopo da prova

O gate dedicado executa em PostgreSQL 16 descartável, com migrations oficiais, `FM_AI_ENV=staging`, `FM_AI_TEST_MODE` ausente e o `app.py` real iniciado pelo launcher comercial já usado nos gates anteriores.

A jornada cobre:

1. login pela autenticação SQLAlchemy real;
2. tenant/unidade derivados da identidade e limitados ao escopo configurado do runtime;
3. cliente CRM e endereço cifrado previamente validado;
4. catálogo/ficha legado sob mapping governado da unidade;
5. carrinho SQLAlchemy comercial;
6. taxa/SLA pela política persistida do Delivery;
7. benefício previamente resolvido atravessando o boundary F11-D;
8. Checkout V1 criando Pedido, Pagamento e Reserva canônicos;
9. Entrega V1 no mesmo `pedido_id`;
10. tracking lido da autoridade logística;
11. cancelamento reconciliando Pagamento pendente, Pedido, Reserva e Entrega;
12. endereço fora da área falhando fechado;
13. RBAC negativo para GARCOM sem `cliente.visualizar`;
14. identidade válida de outro tenant recusada pelo runtime configurado para tenant A;
15. evidência final consultada diretamente do PostgreSQL depois do browser.

## Benefício no gate

A UI continua sem botão fake de cupom/cashback. `scripts/prepare_f11f_resolved_benefit.py` é fixture exclusiva de staging descartável que representa a saída de uma autoridade promocional já resolvida e grava apenas o snapshot do benefício no carrinho comercial via `RepositorioCarrinhosDeliverySQLAlchemy.salvar_cas`.

O fixture:

- recusa `FM_AI_TEST_MODE=1`;
- recusa ambiente diferente de staging;
- não cria nem altera Pedido, Pagamento, Reserva ou Entrega;
- não decide elegibilidade econômica final.

A decisão final permanece em `application.delivery_checkout_comercial`, que registra `delivery.beneficio.checkout.avaliado.v1` e auditoria `avaliar_beneficio_delivery_checkout` na mesma UoW do checkout.

## Evidência durável esperada

Para o cliente principal, após confirmação e cancelamento:

- carrinho: `confirmado`, vinculado ao Pedido canônico;
- Pedido: origem/canal `delivery_proprio`, subtotal 32.00, taxa 7.00, desconto 5.00, total 34.00, status `cancelado`;
- Pagamento: método `pagamento_na_entrega`, valor previsto 34.00, `recebimento_posterior=true`, status `cancelado`;
- Reserva: status `liberada` e timestamp de resolução;
- saldo canônico: físico preservado e reservado zerado após compensação;
- Entrega: `cancelada`, com eventos `entrega.criada` e `entrega.cancelada`;
- outbox do benefício: `aceito=true`, motivo `beneficio_aplicado`;
- auditoria: política `f11-d-delivery-beneficios-v1`, resultado `permitido`;
- cliente fora da área: nenhum Pedido criado;
- identidade do tenant B existe e autentica suas credenciais, mas falha fechado ao tentar assumir o escopo ativo tenant A/unidade A.

## Limites e rollback

- nenhuma migration nova é criada pela F11-F;
- nenhum readiness/blocker é removido nesta fase; isso pertence à F11-G;
- nenhum deploy é autorizado ou executado;
- rollback do bloco é o revert da PR F11-F;
- falha em qualquer gate mantém F11-G bloqueada.
