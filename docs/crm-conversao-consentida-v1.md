# CRM e conversão consentida V1 — PR19

## Problema

O CRM legado conhece WhatsApp, inatividade, cashback e campanhas, mas não possui
consentimento de marketing modelado. A arquitetura V1 também exige que identidades
vindas de marketplaces permaneçam restritas: receber um pedido de iFood/99Food/Keeta
não cria autorização para usar os dados do cliente em marketing próprio.

A PR19 fecha o Gate D com **marketing negado por padrão**, prova append-only de
opt-in/opt-out, conversão explícita de cliente marketplace e revalidação do
consentimento imediatamente antes de cada envio.

## Dependências

- PR2: tenant/unidade, auditoria e menor privilégio;
- PR3: outbox/idempotência;
- PR16: delivery próprio, cupom/cashback;
- PR17–18: `IntegracaoMarketplace`, `PedidoExterno` e plataformas.

Nenhuma autoridade de Pedido, Pagamento, Entrega ou Marketplace é movida para o CRM.

## Escopo entregue

### Cliente próprio

`ClienteCRM` guarda apenas IDs operacionais e **referências de contato** (`contact://`
ou `vault://`). Telefone/e-mail em claro não entram no domínio PR19. Cliente existente
sem evento de consentimento é inelegível para marketing.

### Cliente marketplace restrito

`ClienteMarketplaceRestrito` guarda:

- tenant/unidade e integração;
- plataforma;
- HMAC do identificador externo;
- apelido opcional minimizado;
- TTL explícito;
- vínculo com cliente próprio somente depois de conversão.

O identificador externo em claro é usado apenas para calcular HMAC e não é persistido.
O runtime de teste usa chave HMAC marcada como test-only; produção deverá resolver a
chave em cofre/secret manager.

### Consentimento

`ConsentimentoMarketing` é append-only por:

- cliente;
- canal (`whatsapp`, `email`, `sms`);
- finalidade (`promocoes`, `fidelidade`);
- versão do texto;
- origem;
- base legal `consentimento`;
- hash da prova;
- timestamps de concessão/revogação;
- idempotência e correlation ID.

A prova bruta nunca é persistida. O repositório de consentimento grava o evento e a
mensagem de outbox no mesmo limite transacional da porta. Em produção, essa porta deve
ser implementada como transação local do banco + outbox.

### Opt-out imediato

O estado atual considera o evento mais novo por timestamp; em empate, revogação vence.
Assim, evento antigo fora de ordem não reabilita marketing. `despachar_marketing()`
reconsulta o consentimento no momento do envio, portanto uma audiência preparada antes
do opt-out não é suficiente para autorizar mensagem depois da revogação.

Um opt-out é aceito mesmo quando não existe opt-in anterior. Nesse caso o estado atual
fica explicitamente revogado.

### Eventos

A PR19 emite mensagens minimizadas:

- `cliente.consentiu_marketing`;
- `cliente.cancelou_marketing`.

O payload contém somente IDs operacionais, canal, finalidade, versão do texto e status.
Contato e prova não entram na outbox.

### Conversão marketplace

A identidade restrita só vira `ClienteCRM` quando existe uma ação explícita fora do
marketplace que fornece:

1. referência segura de contato próprio;
2. canal/finalidade;
3. versão do texto;
4. prova de opt-in;
5. idempotency/correlation IDs.

Conversão parcial falha de forma segura: se um passo posterior falhar, a existência de
um cliente próprio sem consentimento **não** libera marketing.

### Cupom e cashback

`PortaBeneficiosCRM` permite incentivo de conversão idempotente (`cupom` ou `cashback`)
somente para cliente convertido de marketplace que ainda esteja consentido no
canal/finalidade exigidos. Benefício já emitido não é removido por opt-out; a revogação
bloqueia novos disparos e novos incentivos dependentes daquele consentimento.

A PR19 não altera o ledger/saldo real de cashback nem o motor de cupom da PR16. Produção
deverá implementar essa porta delegando aos serviços autoritativos existentes.

### Funil

Eventos de funil minimizados registram:

- marketplace restrito;
- consentimento concedido;
- convertido;
- benefício emitido;
- opt-out.

O resumo usa IDs/referências operacionais e não precisa de contato em claro.

## Invariantes de segurança e privacidade

1. Marketing é `False` quando não há consentimento atual explícito.
2. Consentimento é específico por canal e finalidade; um não implica o outro.
3. Revogação tem efeito imediato para novas tentativas de envio.
4. Evento antigo/out-of-order não supera revogação mais nova.
5. Re-opt-in posterior exige nova prova explícita.
6. Identidade marketplace restrita nunca é elegível para marketing por si só.
7. ID externo de marketplace é armazenado somente como HMAC.
8. Contato de cliente próprio é somente referência segura; PII bruta fica fora deste domínio.
9. Prova de consentimento é armazenada somente como SHA-256.
10. Outbox e auditoria não contêm contato/prova brutos.
11. Toda leitura/escrita é escopada por tenant/unidade; escopo errado é fail-closed.
12. Idempotency key repetida com semântica diferente gera conflito explícito.
13. Cliente legado permanece sem opt-in até regularização explícita.
14. Nenhum adapter de marketplace pode transformar pedido recebido em consentimento.

## Auditoria

Opt-in, opt-out, conversão e benefício geram `EventoAuditoria` minimizado. `papel_efetivo`
é `None` para ação de autoatendimento e o ator é uma referência interna de cliente.
Metadata contém apenas canal/finalidade/plataforma/tipo de benefício.

## Feature flag

`FM_AI_CRM_V1=1` só habilita o módulo quando `FM_AI_TEST_MODE=1`.

Nesta PR a flag não conecta a UI principal nem transportes reais.

## Rollout, observabilidade e rollback

Fase atual: contratos e runtime in-memory de teste. Para homologação futura:

1. implementar persistência append-only + outbox transacional;
2. resolver HMAC/contatos em cofre;
3. conectar cupom/cashback aos serviços autoritativos;
4. observar taxa de opt-in, opt-out, bloqueios de envio, conflitos de idempotência e expurgo TTL;
5. canary por tenant/unidade;
6. validar política de retenção com jurídico/DPO.

Rollback desta etapa: desabilitar `FM_AI_CRM_V1`; nenhum dado real foi migrado.

## Não escopo

- migration em banco real;
- importação automática do CRM legado;
- envio real de WhatsApp/e-mail/SMS;
- campanha automática;
- compra de mídia ou remarketing marketplace;
- enriquecimento de identidade marketplace;
- venda/compartilhamento de dados;
- definição jurídica final de retenção/base legal;
- início da PR20.

## Gates PR19

- Ruff em `core/crm` e testes PR19;
- mypy em `core/crm`;
- unitários e integração focados;
- suíte Python completa;
- regressões PR10–PR18 continuam executando por pull request.

Nenhum gate autoriza merge, deploy, migration real ou início da PR20.
