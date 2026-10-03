# ADR-KCA-011 — Command Product Billing Control Plane

Status: ADOTADO

## Contexto

A FM Tecnologia comercializa múltiplos SaaS. Cada produto precisa incorporar
contratação, assinatura, paywall e estado financeiro sem duplicar a gestão da
conta recebedora da FM nem misturar receita entre produtos.

O mesmo provider físico pode, por decisão operacional, liquidar receitas de mais
de um produto. Isso não autoriza compartilhar identidade comercial, routing,
receivables, ledger ou reconciliação entre eles.

Também existe uma classe totalmente diferente de pagamentos: os recebimentos
operacionais dos clientes dos estabelecimentos. Esses pagamentos pertencem ao
tenant e nunca fazem parte do billing SaaS da FM.

## Decisão

O Command é o control plane oficial de billing SaaS da FM Tecnologia.

Cada SaaS possui um **Product Billing Profile** identificado por
`product_code`. Exemplos:

- `KORDENA`;
- `IRON`;
- `CAMPAIA`;
- produtos futuros.

O Product Billing Profile governa, no mínimo:

- provider accounts permitidas;
- ambiente sandbox/production;
- routing primário e fallback por forma de pagamento;
- capacidade de recorrência;
- webhooks;
- referência segura de credencial;
- healthcheck/homologação;
- receivables;
- reconciliação;
- settlement;
- métricas financeiras e alertas.

A configuração é administrada pelo Command por fronteiras server-to-server
governadas. O Command não grava diretamente nas tabelas internas do produto e
não participa do hot path obrigatório de cada transação.

## Incorporação em cada produto

Cada produto deve incorporar:

1. catálogo/plano/preço canônico;
2. checkout de licença;
3. assinatura;
4. entitlement/paywall;
5. receivable/fatura;
6. billing transaction ledger;
7. webhook inbox;
8. reconciliação;
9. projeção read-only para o Command.

O usuário final do SaaS enxerga somente sua própria assinatura e meios de
pagamento. Ele nunca enxerga credenciais, saldo ou conta recebedora da FM.

## Identidade financeira

Todo recebimento SaaS novo precisa resolver a seguinte cadeia antes de entrar no
ledger:

```text
product_code
→ fm_customer_id
→ product_account_id
→ tenant_id
→ subscription_id
→ receivable_id
→ billing_transaction_id
→ provider_account_id
→ external_transaction_ref
```

Enquanto `receivable_id` ainda não estiver materializado no schema, a
combinação de produto + cliente + product account + assinatura é obrigatória e
o recebimento órfão permanece fora do ledger.

Uma transação externa já ligada a essa cadeia não pode ser rebindeada para
outro cliente, produto ou assinatura.

## Segregação por produto

A política de routing é sempre selecionada por `product_code`, forma de
pagamento e ambiente.

Mesmo quando dois produtos usam a mesma conta externa no provider:

- o checkout carrega referência do produto/assinatura;
- o ledger materializa `product_code`;
- receivables são produto-específicos;
- batches preservam identidade item a item;
- relatórios do Command agrupam primeiro por produto e depois por cliente;
- reconciliação nunca usa nome, e-mail ou valor como chave de identidade.

## Batches

Batch é unidade operacional, não identidade financeira.

Cada item de batch mantém seu próprio envelope canônico. Um batch pode agregar
milhares de recebimentos, mas nenhum item perde o vínculo com cliente,
produto, assinatura, fatura e transação.

## Pagamentos operacionais do tenant

O gateway que um restaurante configura para receber seus próprios consumidores
permanece `tenant_managed`.

O gateway usado pela FM para receber licenças de uso permanece
`platform_managed`.

As duas classes não compartilham tela, credencial, provider account lógico,
routing policy, ledger ou reconciliação.

## Configuração da conta recebedora

Nenhuma conta da FM é hardcoded.

O Command deve permitir criar e editar provider accounts em estado inicial não
ativo, deixando dados externos para configuração posterior. A configuração
mínima inclui:

- provider;
- ambiente;
- tipo do titular: `individual` (Pessoa Física) ou `company` (Pessoa Jurídica);
- referência segura ao perfil do titular;
- métodos de pagamento;
- recorrência;
- webhooks;
- prioridade;
- credencial armazenada pelo fluxo de Vault;
- teste de conexão;
- ativação governada.

Uma conta de produção não pode ser promovida a `ACTIVE` sem tipo de titular e
referência de titular configurados e sem connection test válido.

`legal_entity_ref` é uma referência opaca. CPF, CNPJ, número de conta,
credenciais, tokens e dados bancários sensíveis não devem ser gravados em texto
aberto na tabela de billing. Dados exigidos por um provider devem permanecer no
provider ou em armazenamento cifrado apropriado.

A UI brasileira do Command deve apresentar os rótulos **Pessoa Física (PF)** e
**Pessoa Jurídica (PJ)**, mantendo o contrato interno provider-neutral
`individual/company`.

## Segurança

- segredos ficam em Vault e nunca retornam pela API/UI;
- mutações administrativas exigem autorização de control plane e step-up;
- webhooks são verificados antes de produzir efeitos financeiros;
- status/valor financeiro devem ser reconciliados contra API autenticada do
  provider quando aplicável;
- idempotência é obrigatória;
- replays conflitantes falham fechado;
- recebimento sem identidade canônica não libera entitlement;
- Command consome projeções e emite comandos governados, sem virar segunda
  fonte de verdade.

## Observabilidade no Command

O centro de contas do Command deve expor por produto:

- receita esperada;
- receita recebida;
- MRR/ARR;
- faturas em aberto;
- vencidas;
- inadimplência;
- pagamentos confirmados/falhos;
- settlement pendente;
- reconciliações divergentes;
- provider health;
- webhook health;
- última sincronização;
- alertas financeiros.

Também deve oferecer visão consolidada da FM, sempre derivada da soma dos
Product Billing Profiles e nunca de uma mistura de ledgers sem `product_code`.

## Evolução

O próximo componente estrutural é o Receivables Ledger, que materializa
`receivable_id`, competência, vencimento, valor esperado, status e vínculo com
pagamentos. Depois, o Command deve receber a superfície privada
**Configurações → Produtos → <produto> → Billing & Recebimentos**.
