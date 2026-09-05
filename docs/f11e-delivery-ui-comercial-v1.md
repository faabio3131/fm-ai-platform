# F11-E — UI comercial autenticada do Delivery Próprio V1

## Autoridades

- identidade autenticada/Active Scope define `tenant_id` e `unidade_id`;
- CRM V1 define o cliente e o endereço seguro validado;
- catálogo governado da unidade fornece produto/preço/capacidade atual;
- carrinho SQL do Delivery mantém somente o estado da jornada;
- `application.checkout` continua sendo autoridade de Pedido/Pagamento/Reserva;
- `core.entrega` continua sendo autoridade logística;
- a UoW da Application possui commit/rollback das operações coordenadas.

## Superfície comercial

`core/delivery/ui_streamlit.py` não cria mais `RuntimeDeliveryTeste`, não recebe tenant/unidade por formulário e não usa identidades demo. A tela recebe `SessionLocal` e `CURRENT_IDENTITY` do `app.py` e somente é exposta quando `delivery_v1_enabled()` e `delivery_v1_access_allowed()` permitem.

O cliente é escolhido apenas dentre registros CRM do Active Scope. O endereço é o último endereço seguro validado do cliente e a cotação usa a política de entrega real da unidade. A UI não fabrica cupom/cashback: ela apenas mostra valores já reservados no carrinho e deixa a fronteira F11-D decidir se podem cruzar para o Checkout.

## Confirmação

`application/delivery_operacao_comercial.py` cria a composição transacional da jornada:

1. resolve contexto comercial por identidade + cliente;
2. lê o carrinho SQL escopado;
3. cria o snapshot canônico de `Pedido` com origem/canal `DELIVERY_PROPRIO`;
4. captura a ficha/estoque vigente pelo cutover governado;
5. chama `executar_checkout_delivery_comercial_em_transacao` da F11-D;
6. vincula o mesmo `pedido_id` a uma `Entrega` canônica `PROPRIA`;
7. marca o carrinho como confirmado apenas como estado da jornada;
8. faz um único commit no boundary Application.

Nenhuma chamada comercial usa `ServicoDelivery.confirmar()` histórico.

## Tracking, cancelamento e repetição

O tracking lê o Pedido e a Entrega canônicos, sempre validando tenant, unidade, cliente e origem Delivery Próprio.

O cancelamento é fail-closed. Ele só prossegue quando a entrega ainda está em etapa cancelável e a obrigação financeira não está liquidada. Na mesma UoW:

- cancela a obrigação pendente, quando existir;
- transiciona o Pedido para `CANCELADO` pela máquina normativa;
- libera a reserva de estoque ainda ativa;
- cancela a Entrega após a prova de que o Pedido já foi cancelado.

Pagamento liquidado nunca é estornado automaticamente por esta UI; ele exige o fluxo financeiro autorizado de estorno.

A repetição usa o Pedido canônico apenas como referência dos itens, reabre um novo carrinho e reaplica catálogo, preço, estoque, endereço, taxa e SLA atuais. Benefícios antigos não são copiados.

## RBAC

Acesso à superfície exige, no mínimo:

- `pedido.criar`;
- `pedido.visualizar`;
- `cliente.visualizar`.

Finalização do checkout exige também `pedido.alterar` e `pagamento.registrar`. Cancelamento exige `pedido.cancelar`, `pedido.alterar` e `pagamento.registrar`. Efeitos internos estreitos de logística/estoque não ampliam a alçada do ator humano.

## Gates permanentes

- fitness proíbe `RuntimeDeliveryTeste`, `runtime_teste` e escopos demo no caminho comercial;
- fitness exige `CURRENT_IDENTITY + SessionLocal` no `app.py`;
- fitness exige convergência para Checkout/Estoque/Entrega canônicos;
- Ruff e mypy cobrem a nova fachada e UI;
- testes unitários cobrem mapeamento econômico, endereço seguro e gate de acesso;
- PR16 mantém regressão completa e E2E isolado existente.

## Limites desta etapa

F11-E não declara o Commercial Runtime E2E definitivo, não remove blockers de readiness e não faz deploy. Essas provas pertencem à F11-F/F11-G. O runtime histórico continua permitido apenas em fronteiras explicitamente test-only até sua remoção/reconciliação final.
