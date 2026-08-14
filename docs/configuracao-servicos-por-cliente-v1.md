# Configuração de serviços externos por cliente — V1

## Decisão canônica

Meta (Facebook, Instagram e WhatsApp), Maps, bancos/gateways e demais serviços
externos são configurados por `tenant_id` e `unidade_id`. Não existe credencial
global compartilhada entre clientes. Uma configuração nova nasce desativada e a
presença de campos preenchidos não autoriza tráfego real.

O modelo separa:

- parâmetros públicos, como `page_id`, `phone_number_id`, endereço de origem,
  idioma, moeda e URL de webhook;
- finalidades de credencial, que apontam para o histórico seguro de referências;
- habilitação operacional;
- homologação com referência de evidência;
- versão, ator, correlação e auditoria.

Tokens, senhas, `client_secret`, API keys e chaves privadas são rejeitados nos
parâmetros públicos. O banco de configuração guarda somente a finalidade e a
referência do segredo; o valor é resolvido em memória pelo secret store.

## Estados

| Estado | Significado |
|---|---|
| `desativado` | Configuração existe, mas o cliente ainda não habilitou o uso. |
| `bloqueado` | Foi habilitada, porém faltam parâmetros, referências ou segredos resolvíveis. |
| `configurado` | Campos e credenciais estão presentes, mas falta homologação comprovada. |
| `pronto` | Configuração completa, habilitada e homologada com evidência. |

`configurado` não equivale a integração comercial homologada.

## Maps

O catálogo V1 inclui `servico=mapas` e `provedor=google_maps`. Cada unidade
informa `origin_address`, `country_code`, `language`, `currency` e, opcionalmente,
raio ou regras de entrega. Duas credenciais independentes são obrigatórias:

- `browser_api_key`: somente para renderização no navegador, restringida pelas
  origens/domínios autorizados;
- `server_api_key`: geocodificação, rotas, distância e duração no backend,
  restringida por API e infraestrutura.

A conta de billing, cotas e APIs habilitadas pertencem ao cliente. O healthcheck
de homologação deve provar geocodificação e rota com a origem daquela unidade.
Ausência de permissão, billing, quota ou chave mantém o serviço bloqueado; a V1
não inventa distância nem taxa de entrega.

## Meta

- Facebook: `page_id`, `app_id`, `access_token` e `app_secret` por referência.
- Instagram: `business_account_id`, `facebook_page_id`, `app_id`,
  `access_token` e `app_secret` por referência.
- WhatsApp: `business_account_id`, `phone_number_id`, `app_id`,
  `access_token`, `app_secret` e `webhook_verify_token` por referência.

Permissões da aplicação Meta, assinatura de webhook, número aprovado e opt-in do
destinatário continuam sendo gates próprios; preencher IDs não os substitui.

## Bancos e gateways

PagBank e Mercado Pago estão representados como provedores de `pagamentos.pix`.
Cada unidade mantém sua própria conta externa, URL de notificação, ambiente e
referências de credencial. O ledger financeiro continua sendo a autoridade; um
webhook só confirma pagamento depois de autenticação e reconciliação do provedor.

## Operação administrativa segura

As migrations criam `fm_servicos_externos_config_v1` de forma aditiva. O comando
de credencial recebe apenas o nome de uma variável de ambiente, nunca o segredo
na linha de comando:

```bash
export MAPS_SERVER_KEY='<segredo>'
python -m scripts.configure_external_credential_v1 \
  --admin-email dono@empresa.com \
  --provider google_maps \
  --purpose maps_server_api_key \
  --secret-env MAPS_SERVER_KEY
```

Depois, a configuração pública pode ser registrada e consultada pelo control
plane autenticado:

```bash
python -m scripts.configure_external_service_v1 \
  --admin-email dono@empresa.com configure \
  --config-id maps-loja-centro \
  --service mapas \
  --provider google_maps \
  --external-account billing-cliente \
  --environment homologacao \
  --param origin_address='Rua Exemplo, 100' \
  --param country_code=BR \
  --param language=pt-BR \
  --param currency=BRL \
  --credential browser_api_key=maps_browser_api_key \
  --credential server_api_key=maps_server_api_key \
  --enable
```

O comando autentica o administrador, aplica RBAC, limita o escopo ao tenant e à
unidade do runtime, usa concorrência otimista e grava auditoria. Aplicar migration
em banco real, inserir credencial real ou registrar homologação real continuam
ações operacionais separadas e sujeitas aos gates correspondentes.

## Legado

As colunas `configuracoes_meta.*token` e `gateway_api_key` são legado incompatível
com este contrato e não são a fonte canônica. A migração de valores existentes
deve ocorrer somente com procedimento seguro, sem imprimir o valor e sem apagá-lo
antes de backup e validação. A remoção física dessas colunas é uma etapa destrutiva
posterior, não executada automaticamente.
