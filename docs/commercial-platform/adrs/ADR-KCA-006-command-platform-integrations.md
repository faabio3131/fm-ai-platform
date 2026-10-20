# ADR-KCA-006 — Command como autoridade de integrações de plataforma

Status: ADOTADO

## Contexto

Kordena possui dois grupos de integrações com autoridades diferentes:

1. serviços que fazem parte da própria infraestrutura comercial do SaaS e são
   pagos/operados pela FM Tecnologia;
2. integrações que representam contas, credenciais e contratos do estabelecimento.

Misturar esses grupos no mesmo painel do tenant fazia o cliente enxergar e poder
tentar administrar credenciais que pertencem à plataforma.

## Decisão

O painel central oficial da FM Tecnologia chama-se **Command**.

O namespace técnico histórico `FMCC` permanece temporariamente em rotas e nomes
internos para compatibilidade, mas a autoridade de negócio é o Command.

O catálogo de integrações passa a declarar explicitamente:

- `platform_managed`: autoridade FM/Command;
- `tenant_managed`: autoridade do estabelecimento.

Na V1, são `platform_managed`:

- OpenAI / GPT-5.6 Luna como rota primária de IA textual;
- Google Gemini como fallback textual e rota temporária de transcrição de áudio;
- Google Maps / Geocoding / Routes / browser map key.

A escolha de provider/modelo é responsabilidade da FM/Command, não do tenant. O
roteamento preserva metering por tenant/unidade e permite substituir o modelo sem
expor chaves ou configuração de infraestrutura ao cliente.

As demais integrações do catálogo permanecem `tenant_managed`, incluindo Meta,
WhatsApp, marketplaces, pagamentos operacionais do estabelecimento e fiscal.

### Billing SaaS da FM

A partir do fechamento comercial KF-04, fica explicitamente separado um terceiro
caso que não deve ser confundido com os gateways do estabelecimento:

- pagamentos operacionais do restaurante continuam `tenant_managed`;
- recebimentos de licença/assinatura dos produtos da FM Tecnologia são
  `platform_managed` pelo Command.

Cada produto da FM possui um Billing Profile isolado por `product_code`.
Kordena, IRON, CampaIA e produtos futuros podem usar o mesmo provider físico ou
a mesma conta bancária, mas não compartilham identidade financeira, roteamento,
ledger, receivables ou reconciliação lógica.

O produto incorpora a experiência de contratação, status da assinatura,
paywall/entitlement e retorno de checkout. O Command é a autoridade de gestão
da conta recebedora da FM, credenciais, provider accounts, healthcheck,
homologação, roteamento, fallback, receivables, settlement e monitoramento.

O vínculo mínimo de cada recebimento SaaS é:

```text
product_code
fm_customer_id
product_account_id
tenant_id
subscription_id
receivable_id        # quando o Receivables Ledger estiver materializado
billing_transaction_id
provider_account_id
external_transaction_ref
```

Nenhum evento externo pode reatribuir uma transação já ligada a outro
cliente/produto/assinatura. Pagamento sem binding canônico permanece fora do
ledger financeiro até reconciliação governada.

## Superfície do tenant

A API e a UI de `/v1/admin/integracoes` não listam integrações
`platform_managed`.

Chamadas diretas de escrita, healthcheck ou homologação do tenant contra uma
integração `platform_managed` devem falhar fechado.

## Superfície do Command

O Kordena expõe uma fronteira server-to-server autenticada em:

`/v1/control-plane/fmcc/integrations`

A fronteira usa o mesmo token de control plane já governado pelo FMCC/Command,
exige step-up fresco para mutações e grava as configurações canônicas em:

- tenant técnico: `nova-fm-control-plane`;
- unidade técnica: `fm-control-center`.

O Command não cria uma segunda fonte de verdade: ele delega writes para
`AplicacaoIntegracoesAdminV1`, o mesmo serviço transacional usado pela autoridade
canônica de integrações.

## Runtime

OpenAI, Gemini e Maps resolvem primeiro a configuração canônica do Command.

Durante a migração existe uma ponte de compatibilidade:

- se o Command ainda não tiver configuração, o runtime pode usar a configuração
  homologada do tenant solicitante;
- se o tenant solicitante não tiver configuração, o runtime pode usar uma única
  configuração legada homologada encontrada no banco;
- se houver mais de uma candidata legada homologada, o runtime falha fechado com
  `configuracao_plataforma_legada_ambigua`.

Assim que uma configuração canônica existir no Command, o fallback legado deixa
de participar da decisão.

## Segurança

- segredos continuam cifrados no vault;
- nenhuma credencial é retornada pela API;
- o runtime resolve o segredo no escopo da configuração que foi selecionada;
- tenant comum não pode editar integrações de plataforma;
- mutações do Command exigem token server-to-server e step-up recente;
- a ponte legada nunca escolhe arbitrariamente entre múltiplas candidatas.

## Evolução

O próximo passo é o frontend privado do Command consumir esta fronteira e
centralizar healthcheck, homologação, rotação, uso, FinOps, alertas e auditoria
das APIs compartilhadas entre Kordena e os demais SaaS da FM Tecnologia.
