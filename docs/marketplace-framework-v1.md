# Framework de adapters e primeiro marketplace — PR17

## Objetivo

Criar a camada anticorrupção de marketplaces prevista na arquitetura operacional.
O domínio interno continua centrado em `Pedido`; peculiaridades de cada plataforma
ficam encapsuladas em `MarketplaceAdapter` e em `capacidades` declarativas.

O primeiro adapter é **iFood Sandbox**. Ele reproduz o contrato necessário para
homologação e desenvolvimento sem credenciais e sem rede real: polling de eventos,
acknowledgement, consulta de pedido e comandos de ciclo de vida. A implementação de
produção fica para PR18, quando APIs/credenciais de cada plataforma estiverem disponíveis.

## Referência externa usada

A implementação foi alinhada à documentação oficial do iFood consultada em
11/08/2026. O módulo Events documenta polling e webhook, eventos com `id`, `code`,
`fullCode`, `orderId`, `merchantId` e `createdAt`, além de acknowledgement após
processamento. O guia oficial recomenda polling em desenvolvimento e exige reconhecer
os eventos processados; os estados principais incluem `PLACED`, `CONFIRMED`,
`READY_TO_PICKUP`, `DISPATCHED`, `CONCLUDED` e `CANCELLED`.

O sandbox **não envia HTTP** e não contém token, client secret ou credencial real.
Constantes de URL servem apenas como contrato/documentação do adapter.

## Contratos e invariantes

1. `IntegracaoMarketplace` é sempre escopada por tenant + unidade + conta externa.
2. Segredos são apenas referências (`segredo_ref`); token bruto não é aceito no modelo.
3. `PedidoExterno` é único por `(integracao_id, id_externo)` e aponta para um Pedido interno.
4. Evento externo vira um `EnvelopeMensagem` mínimo; payload bruto/PII não entra na inbox.
   Persiste-se somente hash e metadados necessários à reconciliação.
5. A inbox é registrada **antes** do handler. Acknowledgement ao provedor só ocorre após
   sucesso, duplicata segura ou persistência em DLQ.
6. Falha transitória usa backoff exponencial + jitter determinístico e não recebe ack.
7. Erro permanente ou retry esgotado vai para DLQ; como a cópia interna está preservada,
   o evento pode ser reconhecido no provedor para evitar poison loop.
8. Evento fora de ordem nunca regride o PedidoExterno; o serviço consulta o snapshot
   autoritativo do provedor e reconcilia por data/versão.
9. Comandos de saída passam por outbox e chave de idempotência antes do adapter.
10. Capacidades do provedor são declarativas; ausência de capacidade falha fechada.
11. O adapter não decide política de cozinha, pagamento, estoque ou entrega.
12. Cliente de marketplace e marketing ficam fora da PR17; PR19 tratará consentimento.

## iFood Sandbox V1

Capacidades declaradas nesta PR:

- receber pedido/eventos;
- confirmar;
- atualizar status de preparo/pronto/despacho;
- solicitar cancelamento;
- consultar/reconciliar.

`rejeitar` permanece não suportado no adapter V1 em vez de ser improvisado como
cancelamento. PR18 poderá ampliar capacidades somente com contrato oficial validado.

## Fluxo de entrada

```text
iFood sandbox -> polling -> normalização -> inbox
    -> handler -> consultar snapshot -> PedidoExterno -> porta de Pedido interno
    -> sucesso/duplicata -> acknowledgement
    -> transitório -> retry sem ack
    -> permanente/esgotado -> DLQ -> acknowledgement seguro
```

## Fluxo de saída

```text
service -> checa capacidade -> outbox(idempotency_key)
        -> adapter iFood sandbox -> marca publicado
```

Repetir a mesma chave de idempotência não dispara o comando novamente.

## Fora de ordem e reconciliação

Cada `PedidoExterno` guarda `ultima_ocorrencia_em` e `versao_externa`. Se chega evento
mais antigo, o serviço não aplica regressão. Ele consulta o snapshot atual do adapter e
sincroniza somente se o snapshot for tão novo quanto o estado já conhecido.

## Segurança e PII

- tenant/unidade derivam da integração cadastrada;
- `merchantId` divergente vira erro permanente/DLQ;
- payload externo completo não é persistido na inbox;
- nenhum segredo bruto é persistido;
- nenhum dado de marketplace é liberado para marketing nesta PR.

## Rollout

`FM_AI_MARKETPLACE_V1=1` só habilita execução quando `FM_AI_TEST_MODE=1`.

Não há nesta PR:

- conexão real com iFood, 99Food ou Keeta;
- webhook público;
- credenciais reais;
- migration em banco real;
- deploy;
- criação de cliente/consentimento CRM;
- alteração do app interno principal.

## Rollback

Desligar `FM_AI_MARKETPLACE_V1` remove o caminho executável de teste. Como o PR17 não
executa migration nem toca serviços externos reais, o rollback não requer compensação
de produção.

## Gates

`PR17 Marketplace Gates` executa Ruff, mypy, unitários, integração, contrato do adapter,
E2E sandbox sem rede e a suíte Python completa. Workflows das PRs anteriores continuam
como regressão automática. Nenhum gate autoriza merge, deploy ou PR18 automaticamente.
