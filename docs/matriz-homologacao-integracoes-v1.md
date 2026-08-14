# Matriz de homologação externa — GERENTE AI V1

Segredos são cadastrados por referência (`env:...` ou secret store), nunca em
Git, documentação, banco em texto aberto, log ou conversa.

| Integração | Conta/ambiente | Credenciais e secrets por tenant/unidade | Teste externo | Resultado esperado | Evidência de aprovação |
|---|---|---|---|---|---|
| Facebook Pages | Meta App de desenvolvimento e Página vinculada | `access_token`, `app_secret`; `page_id`, `app_id` | validar permissões e publicar/remover post de homologação | ID real e leitura posterior coerente | execução datada, IDs mascarados, escopos e remoção |
| Instagram | Conta Business vinculada à Página | `access_token`, `app_secret`; `business_account_id`, `facebook_page_id`, `app_id` | criar container, publicar mídia e consultar estado | container e media ID reais, sem duplicata | IDs mascarados e registro da mídia de teste |
| WhatsApp Cloud API | WABA, número de teste/aprovado e Meta App | `access_token`, `app_secret`, `webhook_verify_token`; IDs públicos | challenge, HMAC, envio permitido e webhook de status | challenge aceito, `wamid` e estado reconciliado | correlation ID, `wamid` mascarado e eventos sanitizados |
| Google Maps Web | Google Cloud com billing e Maps JavaScript API | `browser_api_key` restrita por domínio | abrir em origem autorizada e negar outra origem | mapa abre somente no domínio autorizado | restrições, domínio e healthcheck datado |
| Google Maps Server | Geocoding API e Routes API | `server_api_key` restrita por API/IP; endereço da unidade | geocodificar e calcular rota, distância e ETA | coordenadas, metros, duração e polyline válidos | payload sanitizado, quota/billing e rota conhecida |
| PagBank PIX | conta Sandbox | `api_token`; `notification_url` HTTPS | criar ordem, consultar, receber assinatura e reconciliar | `ORDE_...`, QR, webhook confiável e confirmação única | IDs mascarados, assinatura e prova de idempotência |
| Mercado Pago PIX | credenciais de teste da aplicação | `access_token`, `webhook_secret`; `notification_url` HTTPS | criar PIX idempotente, validar `x-signature` e consultar | payment ID, dados PIX, HMAC e replay idempotente | IDs mascarados, manifesto HMAC e reconciliação |
| Gemini | projeto Google AI com quota | `api_key`; modelo e região | validar modelo e gerar resposta mínima | resposta válida e erros normalizados | modelo, latência, quota e correlation ID sanitizados |
| iFood | contrato Merchant e sandbox oficial | `client_id`, `client_secret`, merchant IDs | autenticar, polling, acknowledge, consulta e comandos suportados | pedidos reais de sandbox, replay e reconciliação | capabilities, IDs mascarados e inbox/outbox |
| 99Food | contrato e documentação oficial | conforme contrato, por referência | suíte do transporte parceiro verificado | sem endpoint/capacidade inventada | versão do contrato, ambiente e limitações |
| Keeta | contrato e documentação oficial | conforme contrato, por referência | suíte do transporte parceiro verificado | sem endpoint/capacidade inventada | versão do contrato, ambiente e limitações |

## Testes internos sem credenciais

- catálogo, campos obrigatórios e rejeição de segredo em parâmetro público;
- isolamento tenant/unidade, RBAC e concorrência otimista;
- rotação e resolução de referências de credencial;
- bloqueio antes de configuração e homologação;
- timeout, retry limitado e erros sanitizados;
- webhooks Meta e Mercado Pago por fixtures criptográficas;
- PIX com chave de idempotência estável;
- Maps web/server separados, geocodificação, Routes, distância e ETA;
- migration `0011`: upgrade, idempotência, downgrade, rollback e reaplicação;
- 99Food/Keeta bloqueados até transporte com contrato verificado.

## Critério para homologar

`configurado` não significa `pronto`. O estado muda para `pronto` somente depois
de todas as referências existirem e uma evidência real do provedor ser registrada.
Mudar conta, ambiente, parâmetro ou finalidade revoga a homologação anterior.
