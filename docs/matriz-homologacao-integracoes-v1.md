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

## Estado do recorte F4-F — 31/08/2026

Esta seção registra somente o que foi provado internamente para o Assistente. Ela
**não substitui** a evidência real exigida na tabela de homologação externa acima.

| Dependência do Assistente | Prova interna no candidato | O que ainda falta para homologação externa/comercial |
|---|---|---|
| WhatsApp Cloud API | webhook escopado por tenant/unidade, challenge, HMAC, texto, áudio, download autenticado de mídia, outbound, replay idempotente e falha fail-closed; Assistente Fase 4 Gate run 209 PASS | WABA/número/Meta App reais do tenant de homologação, challenge real, envio com `wamid` real, callback real de status, evidência datada e teste físico |
| Gemini / transcrição | áudio WhatsApp converge para `CapabilityIA.ATENDIMENTO_TRANSCRICAO` do AI Router e usa o mesmo fluxo de atendimento do texto | execução física com credencial/provider homologado no tenant candidato, latência/quota/correlation sanitizados |
| Google Maps Server | endereço/área/taxa/ETA já passam pelo adapter governado e política tenant/unidade do Assistente | manter/apresentar evidência real do ambiente candidato quando o E2E físico for executado |
| PagBank PIX | reconciliação interna e Order Result Orchestrator estão cobertos por testes; nenhum pagamento é marcado como pago por declaração do cliente | conta/credenciais oficiais, cobrança/QR real, webhook/consulta autenticados e prova real de idempotência |
| Migrations do Assistente | 0034 e 0035 estão registradas no runner/manifest e passam pelo gate automatizado | aplicar 0034/0035 no banco físico de homologação e registrar dry-run/upgrade/healthcheck do mesmo candidato |

**Classificação atual do Assistente:** `COMMERCIAL_CANDIDATE`, não
`COMMERCIAL_HOMOLOGATED`.

A promoção final exige que `docs/commercial_runtime_readiness_v1.json` tenha
evidência real para `commercial_runtime_e2e` e `physical_test`, e que nenhum
blocker externo permaneça. Fixture, mock, sandbox sem conta oficial ou teste
automatizado isolado não pode ser usado para fabricar essa evidência.

