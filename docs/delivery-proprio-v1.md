# Delivery Próprio V1 — PR16

## Objetivo

Implementar o canal próprio sem acoplar a jornada do cliente ao monólito legado.
O fluxo segue a arquitetura operacional V1: catálogo publicado → carrinho →
endereço/área → taxa e SLA versionados → cupom/cashback → confirmação explícita
→ Pedido/Pagamento/Entrega → tracking, cancelamento ou repetição.

## Escopo entregue

- catálogo somente com produtos ativos da empresa/unidade e disponibilidade explícita;
- carrinho com snapshots de preço, custo estimado e versão do produto;
- concorrência otimista por `versao`/CAS em toda mutação;
- endereço validado e isolado por cliente;
- área de entrega por CEP, com escolha determinística pelo prefixo mais específico;
- taxa e SLA congelados na cotação e revalidados no fechamento;
- cupom com vigência, mínimo, limite total/cliente e reserva idempotente;
- cashback lido de fonte autoritativa, reservado idempotentemente e nunca acima do saldo;
- confirmação com claim CAS **antes** de efeitos externos para impedir pedido/pagamento/entrega duplicados;
- obrigação financeira por porta: Pix/cartão começam `pendente`; pagamento na entrega começa `aguardando_entrega`;
- criação de `Entrega` comum e tracking por eventos autoritativos;
- cancelamento com reconciliação de pagamento, entrega, cupom e cashback;
- cálculo de desperdício usando custo estimado snapshotado dos itens quando produção já começou;
- repetição reconstrói novo carrinho e revalida produto, preço, estoque, endereço, área, taxa e SLA;
- repetição não copia cupom nem cashback silenciosamente;
- isolamento obrigatório por tenant/unidade/cliente;
- feature flag fail-closed: `FM_AI_DELIVERY_V1=1` só funciona junto de `FM_AI_TEST_MODE=1`.

## Invariantes

1. Nenhuma operação aceita recurso de outro tenant/unidade.
2. Tracking e cancelamento também validam o `cliente_ref`; falhas de escopo retornam `recurso_indisponivel`.
3. Duas mutações com a mesma versão não podem vencer.
4. Confirmação reivindica o carrinho via CAS antes de criar Pagamento/Entrega.
5. Retry do mesmo `idempotency_key` retorna o mesmo pedido.
6. Mudança de preço, versão, estoque, taxa ou SLA exige reconfirmação; nada é corrigido silenciosamente.
7. Cupom/cashback são reservas e precisam existir na fonte de promoções no fechamento.
8. Pix ou cartão não são considerados pagos pelo canal; somente a autoridade financeira pode mudar o status.
9. Pagamento na entrega permanece `aguardando_entrega`.
10. Pedido entregue não pode ser cancelado pelo canal.
11. Cancelamento de pedido pago solicita estorno; pedido pendente apenas cancela a obrigação.
12. Repetir pedido nunca inventa substituto para produto indisponível.

## Concorrência e idempotência

O carrinho usa compare-and-swap. Na confirmação, o estado muda primeiro de `aberto`
para `confirmacao_em_andamento`, gravando `pedido_id` determinístico e a chave de
idempotência. Somente depois são chamados os adapters de Entrega e Pagamento,
também idempotentes. Uma segunda confirmação concorrente não cria efeitos externos.

## Cancelamento e desperdício

O canal recebe o estágio operacional autoritativo. Antes da produção o desperdício
estimado é zero. A partir de `em_producao`, o valor usa o custo estimado congelado
dos itens; ele é indicador operacional, não escrituração contábil/fiscal. Se a fonte
financeira já confirmou pagamento, o cancelamento solicita estorno integral do total
do pedido. Se ainda estava pendente, cancela a obrigação sem declarar dinheiro recebido.

## Tracking

O cliente só lê eventos da `Entrega`. O canal não deriva status de texto da UI nem
da IA. O runtime de teste modela a sequência da PR13 e bloqueia transições inválidas.

## Rollout e não escopo

Nesta PR o canal é executável apenas no runtime isolado de testes. Não há:

- deploy público;
- migration em banco real;
- geocoder/mapa real;
- gateway/adquirente real;
- entregador ou roteirização real;
- antifraude;
- cálculo fiscal;
- domínio/SSL/CDN;
- integração com marketplace;
- alteração do app interno principal.

A futura implantação deve fornecer adapters persistentes/externos sem alterar os
contratos do domínio.

## Gates

`PR16 Delivery Gates` executa:

- Ruff em `core/delivery` e testes PR16;
- mypy no módulo Delivery;
- unitários/integração focados;
- suíte Python completa;
- Playwright browser-driven da jornada própria.

Os workflows PR10–PR15 continuam como regressão automática em pull requests para
`main`. Nenhum gate autoriza merge, deploy, migration real ou início da PR17.
