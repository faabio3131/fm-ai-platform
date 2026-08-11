# Adapters adicionais de marketplace — PR18

## Objetivo

Evoluir o framework da PR17 sem misturar contratos de provedores. Cada plataforma
possui adapter e feature flag próprios. Nenhuma integração real é ativada nesta PR.

## iFood

A documentação pública atual fornece contrato suficiente para preparar um adapter
HTTP verificável sem usar credenciais reais:

- OAuth 2.0 Bearer por `client_credentials`;
- polling em `GET /order/v1.0/orders:polling`;
- acknowledgement em `POST /order/v1.0/orders:acknowledgment`;
- detalhe em `GET /order/v1.0/orders/{id}`;
- comandos `confirm`, `startPreparation`, `readyToPickup`, `dispatch` e
  `requestCancellation`;
- cancelamento é assíncrono: HTTP 202 não significa pedido cancelado; o resultado
  autoritativo chega por evento posterior.

`IfoodHttpAdapter` usa portas injetáveis de HTTP e segredos. Os testes usam fakes e
não fazem rede. O token é mantido somente em memória e o repositório guarda apenas
`segredo_ref`; client secret e access token nunca são persistidos.

## 99Food

A 99Food mantém uma Open Platform oficial e o material oficial para restaurantes
lista API como uma das formas de operação. Entretanto, o contrato técnico detalhado
é entregue no portal/aplicação JavaScript/parceria e não está disponível no
repositório nem há credencial parceira configurada.

Por isso `Food99PartnerAdapter` é deliberadamente fail-closed. Ele só aceita um
`TransporteParceiroNormalizado` com `contrato_verificado=True`. Até a documentação
parceira ser fornecida, as únicas capacidades publicadas são leitura/recepção e
reconciliação; confirmar, rejeitar, atualizar status ou cancelar não são
improvisados a partir de suposições.

## Keeta

O site oficial da Keeta confirma APIs padronizadas para parceiros, incluindo gestão
de pedidos, sincronização de cardápio e serviços centrais. Os endpoints/payloads
detalhados, porém, não estão públicos no material acessível e não há credencial de
parceiro configurada.

`KeetaPartnerAdapter` segue a mesma política fail-closed da 99Food: contrato técnico
verificado primeiro; implementação de mutações depois. Nenhum endpoint ou schema
foi inventado.

## Flags

Todas continuam dependentes de `FM_AI_TEST_MODE=1` e `FM_AI_MARKETPLACE_V1=1`:

- `FM_AI_IFOOD_ADAPTER_V1=1`
- `FM_AI_99FOOD_ADAPTER_V1=1`
- `FM_AI_KEETA_ADAPTER_V1=1`

Nesta etapa elas são apenas gates de runtime de teste. Produção continua desativada.

## Invariantes

1. Um adapter nunca aceita integração de outra plataforma.
2. Segredos continuam sendo referências externas; nada sensível entra no Git.
3. HTTP 202 do iFood não altera sozinho estado interno final.
4. Eventos só são reconhecidos depois que o serviço da PR17 os processa com segurança.
5. Retry/DLQ/inbox/outbox continuam centralizados na PR17.
6. 99Food e Keeta não recebem contrato presumido: sem documentação/credencial de parceiro,
   mutações ficam bloqueadas.
7. O adapter não decide estoque, cozinha, pagamento, entrega ou consentimento de marketing.
8. Não há acesso de rede nos testes PR18.

## Rollout / não escopo

Não há nesta PR:

- deploy público;
- migration real;
- armazenamento de client secret/token;
- chamada real ao iFood;
- login real no portal 99Food;
- chamada real à API Keeta;
- sincronização de cardápio;
- abertura/fechamento real de loja;
- início da PR19.

A ativação real de qualquer provedor exige credencial/parceria, homologação oficial,
adapter de transporte concreto, observabilidade e autorização humana separada.
