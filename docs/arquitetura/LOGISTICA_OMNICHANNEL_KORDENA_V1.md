# Kordena — Logística Omnichannel V1

**Status:** arquitetura implementada em candidata isolada; sem merge/deploy
**Data:** 2026-10-03
**Objetivo:** fazer Expedição e Entrega serem uma única superfície operacional para Delivery Próprio e marketplaces, preservando a autoridade real de cada parceiro.

## 1. Fundamento

A Expedição do Kordena pertence à operação do restaurante, não a um canal específico.

Todo pedido que exige entrega deve convergir para a mesma fila operacional do Kordena, independentemente da origem:

- Delivery Próprio;
- iFood;
- Keeta;
- 99Food, quando houver contrato/homologação real;
- demais canais futuros.

Origem comercial do pedido e responsabilidade logística são dimensões distintas.

Exemplos válidos:

- origem = iFood / responsável atual = iFood;
- origem = iFood / responsável atual = loja;
- origem = Delivery Próprio / responsável atual = loja.

## 2. Autoridade externa

Para iFood, a fonte autoritativa por pedido é o detalhe oficial do pedido.

Contrato público consultado:

- GET /order/v1.0/orders/{id}
- orderType
- delivery.mode
- delivery.deliveredBy
- delivery.pickupCode
- delivery.deliveryDateTime

Valores documentados de `delivery.deliveredBy`:

- `IFOOD` — logística iFood;
- `MERCHANT` — entrega do estabelecimento.

Documentação oficial:
- https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/details
- https://developer.ifood.com.br/en-US/docs/food/guides/modules/order/endpoints
- https://developer.ifood.com.br/en-US/docs/food/guides/modules/shipping/endpoints

## 3. Regra de segurança

O Kordena nunca presume que uma entrega externa é própria da loja.

Se a origem não fornecer responsabilidade logística confiável, o estado canônico é:

- modalidade = `indefinida`;
- status após checklist = `aguardando_definicao_logistica`;
- atribuição de entregador próprio bloqueada.

Isso evita dupla logística e double-dispatch.

## 4. Estados logísticos

### Entrega própria

`aguardando_producao -> aguardando_expedicao -> aguardando_entregador -> atribuida -> coletada -> em_rota -> entregue`

### Entrega por marketplace

`aguardando_producao -> aguardando_expedicao -> aguardando_coleta_parceiro`

Eventos externos do parceiro devem evoluir a jornada sem criar entregador local falso.

### Responsabilidade desconhecida

`aguardando_producao -> aguardando_expedicao -> aguardando_definicao_logistica`

Nenhuma atribuição local é liberada até resolução confiável.

## 5. Flexibilidade e mudança de responsabilidade

A responsabilidade logística pode mudar durante a jornada.

O Kordena preserva:

- responsável original;
- responsável atual;
- autoridade que confirmou a decisão;
- evidência externa;
- histórico de alteração.

Quando um novo snapshot confiável do marketplace mudar `deliveredBy`, o Kordena atualiza a mesma Entrega canônica, sem criar uma segunda entrega.

Exemplo:

`IFOOD -> MERCHANT`

mantém:

- mesmo pedido Kordena;
- mesma entrega Kordena;
- histórico de origem;
- evento `entrega.responsavel_logistico_atualizado`.

## 6. Ação “Alterar forma de entrega”

A UI possui a superfície “Alterar forma de entrega”, mas a mutação só pode ser habilitada quando o adapter do provider declarar uma capacidade oficialmente suportada e homologada.

Regra:

1. operador solicita alteração no Kordena;
2. Kordena chama o contrato oficial do provider;
3. resposta assíncrona/evento é reconciliado;
4. somente após confirmação externa o responsável atual é promovido;
5. falha externa mantém o responsável anterior.

Não é permitido alterar apenas o banco local.

### iFood — capacidades públicas confirmadas

A Shipping API pública documenta:

- GET /shipping/v1.0/orders/{orderId}/deliveryAvailabilities;
- POST /shipping/v1.0/orders/{orderId}/requestDriver;
- POST /shipping/v1.0/orders/{orderId}/cancelRequestDriver.

Ela também documenta os eventos:

- REQUEST_DRIVER;
- REQUEST_DRIVER_SUCCESS;
- REQUEST_DRIVER_FAILED.

Isso suporta a jornada loja -> logística iFood quando elegível.

### iFood -> entrega própria

A documentação pública revisada não apresenta um endpoint genérico e explícito para converter todo pedido originalmente `deliveredBy=IFOOD` em `MERCHANT`.

Portanto, esse comando permanece fail-closed até capacidade/contrato oficial homologado para a aplicação Kordena.

Se a alteração ocorrer no parceiro e o novo snapshot chegar com `MERCHANT`, a reconciliação interna já está preparada para refletir a mudança automaticamente.

## 7. Implementação V1 desta candidata

Implementado:

- leitura de `orderType`, `delivery.mode`, `delivery.deliveredBy`, `pickupCode` e `deliveryDateTime` no adapter iFood;
- normalização `IFOOD | MERCHANT | UNKNOWN`;
- criação automática de Entrega V1 para todo snapshot `DELIVERY` de marketplace;
- `IFOOD -> modalidade parceiro`;
- `MERCHANT -> modalidade própria`;
- ausência de autoridade -> modalidade indefinida;
- convergência na mesma tela Expedição e Entrega;
- identificação visual de origem e responsável atual;
- bloqueio de atribuição de entregador próprio quando a logística pertence ao parceiro;
- estados separados para coleta de parceiro e definição logística;
- reconciliação da responsabilidade na mesma Entrega quando o provider mudar `deliveredBy`;
- UI de “Alterar forma de entrega” capability-gated;
- testes de contrato e integração.

Não implementado como mutação externa nesta candidata:

- troca iFood -> MERCHANT sem endpoint/contrato oficial homologado;
- Shipping API transacional loja -> iFood;
- tracking iFood em tempo real;
- adapters logísticos reais de Keeta/99Food.

Esses itens são evoluções da mesma arquitetura e não exigem reescrever a Expedição.

## 8. Critérios de aceite

A candidata só pode ser promovida quando:

1. lint, typecheck, testes Python e Web estiverem verdes;
2. pedido iFood `DELIVERY + deliveredBy=IFOOD` aparecer na Expedição como entrega marketplace;
3. pedido iFood `DELIVERY + deliveredBy=MERCHANT` aparecer como entrega da loja;
4. operador não conseguir atribuir entregador local a entrega de marketplace;
5. deliveredBy desconhecido permanecer fail-closed;
6. resync que mude IFOOD para MERCHANT atualizar a mesma Entrega;
7. nenhum segredo ou payload sensível de marketplace for exposto na UI;
8. nenhuma integração não homologada for declarada operacional.

## 9. Princípio congelado

> Uma tela logística, múltiplos canais, uma Entrega canônica por pedido e nenhuma mudança de responsabilidade sem autoridade externa verificável.
