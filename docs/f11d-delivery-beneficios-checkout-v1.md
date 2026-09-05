# F11-D — Contrato operacional de benefícios no Checkout do Delivery Próprio

## Autoridades preservadas

- `core.delivery` continua calculando e reservando cupom/cashback.
- `application.checkout` continua sendo a única fronteira de Pedido/Pagamento/Reserva.
- Active Scope e contexto autenticado continuam definindo tenant/unidade/cliente.
- A UoW do chamador continua dona de `commit()`/`rollback()`.
- Nenhuma migration, schema paralelo ou pagamento artificial é introduzido.

## Decisão comercial

`application/delivery_checkout_comercial.py` recebe o benefício já resolvido no carrinho e só o aplica quando:

1. o escopo do Pedido, carrinho e contexto comercial é o mesmo;
2. a origem do Pedido é `DELIVERY_PROPRIO`;
3. a política de benefícios está disponível e ativa;
4. o método de pagamento pertence ao conjunto elegível recebido pela política;
5. o benefício não excede o total corrente do Pedido.

Origem marketplace/bridge, método inelegível e benefício inativo/indisponível seguem fallback neutro: o Checkout continua com o comando econômico original. A única exceção é quando uma política recebida declara explicitamente o benefício obrigatório; nesse caso a falha é fechada antes de persistência.

Se o cashback/desconto elegível zerar o Pedido, o boundary remove a obrigação financeira do comando e deixa o Checkout V1 seguir o fluxo canônico de total zero, sem inventar Pagamento.

## Observabilidade

Cada avaliação registra, na mesma UoW do Checkout:

- evento `delivery.beneficio.checkout.avaliado.v1`;
- aceitação ou fallback;
- motivo da decisão;
- origem do Pedido;
- método de pagamento;
- cupom, cashback e benefício total aplicados;
- total antes/depois;
- auditoria `avaliar_beneficio_delivery_checkout`.

Se a transação falhar, evento, auditoria e Checkout permanecem sujeitos ao mesmo rollback do chamador.

## Gates permanentes

- integração: owned delivery, marketplace/bridge, método elegível/inelegível, ativo/inativo, indisponibilidade, política obrigatória e total zerado;
- fitness: proíbe runtime demo/test-only, `commit()`/`rollback()` escondidos e exige convergência para `executar_checkout_em_transacao`;
- CI PR16 passa a executar Ruff, mypy e testes F11-D.

## Limites desta etapa

F11-D não faz deploy, não converte a UI e não remove `delivery_runtime_teste` nem `delivery_demo_scope`. Esses itens permanecem para F11-E/F11-F/F11-G conforme o inventário mestre da Fase 11.
