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

## Estado do recorte F4-F — fechamento interno da Fase 4

Esta seção separa explicitamente prova interna real de configuração/homologação
do provedor externo. O candidato final do recorte interno é
`523bd3534865290ea8362139f32166e72c2d3bdc`.

| Dependência do Assistente | Prova interna / herdada válida | Pendência remanescente |
|---|---|---|
| WhatsApp Cloud API | contrato de webhook escopado, challenge, HMAC, texto, áudio, download autenticado, outbound, replay idempotente, fail-closed e UI browser-driven aprovados; Gate F4 + Commercial E2E verdes | **EXTERNA**: WABA/número/Meta App reais, challenge real, `wamid`/callback reais e evidência do tenant |
| Gemini / transcrição | homologação prática já registrada no Control Plane + áudio do Assistente convergindo para `CapabilityIA.ATENDIMENTO_TRANSCRICAO`; regressão do candidato verde | nenhuma pendência interna da Fase 4 |
| Google Maps Server | homologação prática já registrada + endereço/área/taxa/ETA do Assistente usando adapter e política tenant/unidade; regressão do candidato verde | nenhuma pendência interna da Fase 4 |
| PagBank PIX | reconciliação, runtime PIX e Order Result Orchestrator aprovados internamente; pagamento nunca é promovido por declaração do cliente | **EXTERNA**: conta/credenciais oficiais, cobrança/QR real, webhook/consulta autenticados |
| Migrations 0034 / 0035 | workflow `Assistente Fase 4 Commercial E2E V1` run 5: PostgreSQL 16 real, aplicação + registro + idempotência + tabelas: **PASS (2 testes)** | nenhuma pendência interna da Fase 4 |
| Commercial Runtime E2E | run 5 (`33463947423`) no SHA candidato: **PASS** | nenhuma pendência interna da Fase 4 |
| Browser físico automatizado | Chromium real via Playwright no run 5: aplicação Streamlit + Assistente V1 + texto/áudio + ausência de fallback legado: **PASS (1 teste)** | nenhuma pendência interna da Fase 4 |

**Mercado Pago:** permanece como pendência externa herdada do Control Plane/Fase 3
por condição do provedor/suporte; não é blocker de código específico do F4-F.

**Classificação atual do Assistente:** `COMMERCIAL_CANDIDATE`, com blockers
internos conhecidos = 0. Não é `COMMERCIAL_HOMOLOGATED` porque PagBank e
Meta/WhatsApp ainda dependem de configuração/homologação externa real.

**Decisão de progressão:** a condição autorizada pelo proprietário foi satisfeita.
As pendências locais que impediam o avanço — PostgreSQL/migrations, Commercial
Runtime E2E e browser — foram fechadas. A **Fase 5 está liberada para execução
sequencial**, enquanto PagBank, Meta/WhatsApp e Mercado Pago permanecem como
`PENDÊNCIA EXTERNA`, sem qualquer declaração falsa de homologação.

A promoção futura para `COMMERCIAL_HOMOLOGATED` exige remover os blockers
externos com evidência real dos provedores. O E2E e o browser internos já estão
registrados no readiness; fixture ou mock não substitui evidência externa.
