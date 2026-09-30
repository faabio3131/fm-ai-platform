# KF-06 — Fiscal V1 e integrações de lançamento

Data: 2026-09-30  
Baseline de auditoria: `577babfa977463929d66387c60f75fb68a079494`  
Autoridade: Cronograma Mestre de Finalização V1 Comercial

## Resultado executivo

O escopo de lançamento foi reconciliado contra o CURRENT do repositório, a matriz de homologação externa e a configuração do runtime Railway.

Gate KF-G06:

- `FISCAL_V1_LAUNCH_SCOPE_TRUTHFUL`: **PASS**
- `NO_FAKE_PROVIDER_HOMOLOGATION`: **PASS**
- `ALL_ADVERTISED_INTEGRATIONS_EVIDENCED_OR_DISABLED`: **PASS**

Este PASS certifica **verdade de escopo e governança de lançamento**. Ele não transforma providers pendentes em homologados.

## 1. Fiscal V1

### Decisão de lançamento

A camada fiscal existente contém domínio, documentos, tributação, XML, lifecycle, numeração, assinatura, reconciliação e orquestrações provider-neutral.

Entretanto, o CURRENT examinado não contém evidência de adapter externo real de autoridade fiscal promovido/homologado para produção. Os gateways encontrados em:

- `kordena_fiscal/gateway/fake.py`;
- `kordena_fiscal/operations/fake.py`;

são explicitamente sintéticos, determinísticos e destinados a testes/contratos. Eles **não executam rede externa** e não podem ser usados como prova de SEFAZ, prefeitura ou provider real.

Classificação de lançamento:

```text
Fiscal V1 externo/live: DISABLED_NOT_ADVERTISED
NFCore: DEFERRED_BY_DESIGN
```

Consequências:

- nenhuma UF, município ou provider fiscal é anunciado como homologado sem prova;
- nenhuma emissão real é vendida como disponível;
- nenhum resultado sintético é apresentado como autorização fiscal;
- emissão, contingência, cancelamento, inutilização, carta/correção ou equivalentes só poderão ser promovidos conforme evidência real do escopo específico;
- sandbox/homologação não é confundido com produção.

## 2. Matriz de integrações do lançamento

A classificação abaixo usa exclusivamente os estados autorizados pelo Cronograma Mestre.

| Integração | Classificação V1 | Anunciada como live no lançamento? | Base da decisão |
|---|---|---:|---|
| Gemini | `HOMOLOGATED_LIVE` | SIM, somente no escopo já homologado | Cronograma Mestre declara Gemini já homologado; matriz registra homologação prática e regressão do candidato |
| Google Maps | `HOMOLOGATED_LIVE` | SIM, somente no escopo já homologado | Cronograma Mestre declara Maps já homologado; matriz registra prova prática do Maps Server; credenciais permanecem por tenant/unidade |
| Facebook Pages | `CONFIGURABLE_BY_TENANT` | NÃO como garantia live global | control plane tenant-managed existe; prova externa real por conta/página continua obrigatória |
| Instagram | `CONFIGURABLE_BY_TENANT` | NÃO como garantia live global | control plane tenant-managed existe; conta Business/permissões/publicação real devem ser homologadas por tenant |
| WhatsApp Cloud API | `CONFIGURABLE_BY_TENANT` | NÃO | contrato interno está pronto, porém WABA/número/Meta App, challenge e callbacks reais continuam pendentes |
| PagBank PIX | `CONFIGURABLE_BY_TENANT` | NÃO | runtime/reconciliação internos existem; conta/credenciais/cobrança/webhook reais permanecem pendentes |
| Mercado Pago PIX | `CONFIGURABLE_BY_TENANT` | NÃO | integração preparada e tenant-managed; homologação externa continua pendente |
| iFood | `SANDBOX_ONLY` | NÃO | adapter HTTP/sandbox existem; contrato Merchant e homologação parceira real continuam pendentes |
| 99Food | `DISABLED_NOT_ADVERTISED` | NÃO | contrato técnico/credenciais parceiras verificadas não estão disponíveis |
| Keeta | `DISABLED_NOT_ADVERTISED` | NÃO | endpoints/payloads/credenciais parceiras verificadas não estão disponíveis |
| Fiscal externo | `DISABLED_NOT_ADVERTISED` | NÃO | somente Core fiscal/provider-neutral e fakes de teste foram comprovados |
| NFCore | `DISABLED_NOT_ADVERTISED` | NÃO | fora do escopo desta finalização por decisão arquitetural |

## 3. Regra tenant-managed

`CONFIGURABLE_BY_TENANT` significa apenas que a plataforma possui contrato/configuração segura por `tenant_id` e `unidade_id`.

Não significa:

- provider homologado globalmente;
- credencial presente;
- conta aprovada;
- webhook real validado;
- autorização para movimentar dinheiro;
- autorização para publicar conteúdo;
- autorização para anunciar o provider como live.

O estado canônico existente diferencia `desativado`, `bloqueado`, `configurado` e `pronto`; `configurado` não equivale a `pronto`.

## 4. Evidência de runtime

O inventário atual de variáveis do serviço Railway não contém variáveis globais de Meta, WhatsApp, PagBank, Mercado Pago, iFood, Keeta, 99Food, Gemini, Maps, fiscal, SEFAZ ou NFS-e.

Isso é coerente com a arquitetura tenant-managed e também impede usar a simples existência do runtime Railway como prova de homologação desses providers.

Nenhuma credencial foi lida ou registrada nesta certificação.

## 5. Gemini e Maps

O Cronograma Mestre registra explicitamente ambos como já homologados.

A matriz histórica de homologação registra:

- Gemini/transcrição com homologação prática já registrada no Control Plane;
- Google Maps Server com homologação prática registrada, incluindo geocodificação/rota no escopo do Assistente.

O código também preserva healthchecks externos reais dedicados para Gemini e Maps, separados da alteração do estado de homologação.

Esta certificação não amplia o escopo além do já provado e não converte automaticamente novas contas/tenants em homologados.

## 6. Marketplaces

### iFood

O CURRENT possui adapter HTTP, OAuth, polling, acknowledge, consulta, comandos suportados, inbox/outbox, idempotência, retry/DLQ e sandbox.

A documentação de Fase 12 mantém o estado:

```text
EXTERNAL_HOMOLOGATION_PENDING
```

Logo o lançamento não anuncia iFood como live.

### 99Food e Keeta

Permanecem fail-closed até contrato técnico e credenciais verificadas. Não são anunciados no lançamento.

## 7. Pagamentos operacionais

PagBank e Mercado Pago possuem contratos e componentes internos, porém a evidência atual registra homologação externa incompleta.

Nenhuma cobrança real foi executada para esta certificação.

Eles podem permanecer configuráveis por tenant, mas não são vendidos como integração live sem prova específica daquele tenant/provider/ambiente.

## 8. Critério de publicidade comercial

Para o lançamento V1:

1. somente uma integração com evidência real compatível pode ser descrita como live;
2. integração preparada em código não é vendida como live;
3. integração tenant-managed sem homologação real é apresentada apenas como configurável, quando aplicável;
4. sandbox é identificado como sandbox;
5. integração sem contrato/evidência suficiente fica desabilitada e não anunciada;
6. fake, fixture, mock ou teste contratual nunca substitui evidência externa.

## 9. Conclusão do gate

`FISCAL_V1_LAUNCH_SCOPE_TRUTHFUL = PASS` porque o Fiscal externo fica desabilitado/não anunciado.

`NO_FAKE_PROVIDER_HOMOLOGATION = PASS` porque os gateways sintéticos permanecem classificados exclusivamente como teste e nenhuma autoridade externa foi inventada.

`ALL_ADVERTISED_INTEGRATIONS_EVIDENCED_OR_DISABLED = PASS` porque somente Gemini/Maps permanecem live dentro do escopo já homologado; os demais providers ficam sandbox, configuráveis sem promessa live ou desabilitados/não anunciados.

KF-G06 pode ser considerado **PASS de governança de lançamento**, sem remover blockers externos de KF-04/KF-05 e sem autorizar release público.
