# Kordena V1 — Gates independentes de construção interna e homologação externa

**Decisão do proprietário: 06/11/2026.** Primeiro concluir 100% da construção interna com jornadas e evidências; **somente depois** executar configurações, testes reais e homologações oficiais. Não confundir CI verde com produto funcional, nem exigir credenciais de terceiros para validar os próprios módulos.

## Fonte factual e disciplina de status

- Repositório: `faabio3131/fm-ai-platform`.
- Baseline de operação auditado: `production@fe25ecf2fefb23ee4f3fd3fde9bdb6c8c8a28c7a`. A branch `production` alimenta automaticamente a Contabo a cada cinco minutos; **nenhuma PR desta auditoria autoriza merge nessa branch, deploy ou operação financeira/fiscal real**.
- A PR [#237](https://github.com/faabio3131/fm-ai-platform/pull/237) permanece aberta/Draft. Ela tem CI exact-HEAD aprovada, mas **não está em production**: checkout em dinheiro, troco, venda e reserva/baixa no início do KDS só serão considerados presentes na release após promoção autorizada.
- Históricos de Railway/Vercel/staging/main não são estado operacional atual. Referência: `docs/finalization/KORDENA_CURRENT_PRODUCAO_2026-11-01.md`.
- A homologação passada de Gemini e Maps refere-se às capacidades realmente testadas e não certifica automaticamente o consumo do cardápio via Web/Next.js.
- Status permitidos: **IMPLEMENTADO_COM_TESTES_INTERNOS**, **LACUNA_INTERNA**, **REVALIDAR_JORNADA**, **DEPENDE_CONTRATO_EXTERNO_E_COMPLEMENTO_INTERNO**, **EXCLUSIVAMENTE_EXTERNO**, **FORA_ESCOPO_V1**, **NÃO_COMPROVADO**. NÃO usar **PRONTO_100%** sem gate efetivo.

## 1. O que é estritamente responsabilidade de construção/QA internos

| Área e fluxo | Situação factual | Pendência interna exigida antes de 100% |
|---|---|---|
| Autenticação, unidade ativa, Proprietário/step-up, RBAC | Implementado com matrizes de segurança | Revalidar no SHA final frontend↔API, negação de acesso e isolamento entre pelo menos duas unidades/tenants |
| Cadastro manual de cardápio/categorias/ficha técnica | APIs e telas implementadas; persistência testada | E2E editar, recarregar, consultar fichas, refletir preço/disponibilidade no PDV/atendente |
| Importação de cardápio por Gemini (texto/JPG/PNG/PDF) | A rota Web legada usava `gemini_config.generate_content`, que em runtime comercial exige sessão **Streamlit**; o frontend atual é Next.js. Correção candidata nesta branch usa roteamento IA governado, com capability própria | CI exact-HEAD, E2E sem chave real, erro fail-closed sem rota, upload multimodal, limites de arquivo, validação dos produtos extraídos; reavaliar gravação direta sem etapa humana de revisão |
| Criação original de cardápio por IA a partir de briefing, sem material preexistente | **Não comprovada**: a função existente é importação/extração de cardápio | Distinguir oficialmente se faz parte da V1; se fizer, construir gerador de proposta, revisão e gravação, sem inventar preço/custo |
| CMV de pratos extraídos por IA | Hoje a importação aplica CMV **estimado 32% do preço**, não a ficha real de insumos | Não rotular custo estimado como custo real; permitir conciliação/edição da ficha antes de relatórios de margem |
| Estoque manual, upload documental, conferência, baixa | API/UI de estoque e preview sem gravação têm testes; lote confirmado grava | Testar PNG, JPG, WebP, PDF digital e digitalizado, limites, erros, adição única, múltiplas unidades e estoque pós-venda; reconciliar texto da interface com formatos realmente suportados |
| PDV dinheiro, reserva, pagamento, venda e KDS | Correções testadas na PR #237, **ainda fora de production** | Promover somente com autorização de release; depois reproduzir jornada no mesmo SHA, incluindo troco, estoque, cancelamento e replays |
| Pix operacional PagBank/Mercado Pago | Adapters, webhook, reconciliador e persistência existentes; provas internas | E2E offline com provider fake e webhooks assinados: QR, pendência, liquidação confiável, repetição, estorno/cancelamento e reconciliação; nenhuma cobrança real |
| Débito, crédito, voucher, pagamento posterior | Métodos constam no domínio de pagamentos | Provar quais canais aceitam registro manual e quais exigem captura externa. Captura por adquirente/TEF não deve ser declarada pronta sem adapter real |
| Contas/recebimentos e dashboards financeiros | Modelos financeiros, pagamento e dashboards existem | E2E conciliação venda↔receita↔saldo↔estorno↔Command; provar que contas a pagar de compras não viram recebimentos |
| Fiscal V1: núcleo, emissão, recebimento, XML, perfis, assinatura, cancelamento, inutilização | WP-031 A–L e Master Gate possuem certificação interna histórica. `ConfiguredFiscalGatewayAdapter` existe, mas `build_frontend_http_app` recebe `fiscal_operations_gateway_factory` opcional e o default não registra transporte fiscal real | Definir com precisão o escopo fiscal executável da V1; se emissão/consulta/cancelamento live for parte da entrega, implementar composição e transporte concreto do provider escolhido, tratamento de rejeição, contingência, XML/XSD, A1/CSC, idempotência e testes de contrato **antes** da homologação externa. Não emitir nota real |
| iFood pedidos | Adapter HTTP, OAuth, polling, ACK, comandos, Central de Pedidos e sandbox interno existentes | Reproduzir fluxo completo em ambiente controlado: pedido, itens, status, cancelamento, repetição, DLQ, ACK pós-commit, mapeamento à unidade, flags/segredos, reconciliação; catálogo, horário de loja e webhook só podem ser chamados completos se pertencentes ao escopo funcional acordado |
| 99Food pedidos | `Food99PartnerAdapter` existe, mas **não é registrado no runtime Web real** e não consta no catálogo de integrações configuráveis | Implementar auth/transporte, configuração do tenant, vínculo de loja, inbox/outbox, status/pedidos e UI quando contrato oficial suficiente estiver disponível. Não simular endpoints como se fossem oficiais |
| Keeta pedidos | Adapter/Open Delivery e UI listagem existentes | Verificar compatibilidade de endpoints/escopos do parceiro e E2E, manter fail-closed sem autorização |
| Delivery próprio, Salão, Garçom, KDS, expedição | Implementados e historicamente certificados | Reproduzir jornada entre módulos, concorrência, cancelamento, indisponibilidade e não duplicidade no SHA final |
| Atendente IA, upsell/cross-sell, Gerente IA | Implementados/testados; upsell na release de 01/11 | Verificar runtime atual por texto/voz, comandos permitidos, pedido/carrinho, retorno do cliente, tenant e logs sem dados sensíveis |
| WhatsApp Evolution | Código e deploy evidenciados na release 01/11 | E2E interno de inbound/outbound, reenvio, idempotência, revogação e ausência de credenciais em logs; canal real é etapa externa |
| Integrações e cofre de segredos | Painel, credenciais por tenant, control plane e healthcheck existem | Validar que cada botão de configurar/testar/homologar reflete o adapter realmente executável; guardar secrets só no Vault |
| Billing comercial da assinatura Kordena | KCA-00→17 e adapter Mercado Pago Subscriptions existem | Provar sandbox end-to-end signup→trial→plano→webhook→assinatura→entitlement→cancelamento→Command sem cobrança real; perfis PF/PJ segregados |
| E-mail transacional, recuperação de senha, suporte | Runtime SMTP e fluxos previstos | Simular provider, falhas, reenvio e recuperação em teste; configurar contato e procedimento de suporte na UI |
| FM Command / telemetria / custos IA | Integração S2S e controle de uso existentes | Provar sync, health, métricas, fonte e não duplicidade, sem SQL direto entre bancos |
| Impressão térmica | Infra e testes técnicos existem | Validar spool e fallback internos; prova em impressora física pertence à etapa externa |
| Premium, responsividade, botões e rotas | UI Premium existente | Varrer todos os módulos via Playwright, desktop/mobile, sem ações mortas |
| Banco/migrations e resiliência | Infra e gates existentes | Certificar fresh+upgrade PostgreSQL, backup/restore isolado, retries, observabilidade e rollback no SHA exato |

**Nenhuma linha marcada REVALIDAR passa a LACUNA_INTERNA comprovada sem teste ou defeito objetivo; porém também não pode ser classificada PRONTO_100% apenas por existência de código.**

## 2. Dependências exclusivamente externas ou físicas — deixam de bloquear o gate de construção

| Provedor/dependência | O que o proprietário/terceiro fornece ou autoriza | Critério futuro de homologação |
|---|---|---|
| PagBank Pix | Conta, sandbox oficial, API token, domínio de callback, habilitação da conta recebedora | Cobrança/QR, webhook autenticado, estado pago confirmado e reconciliação sem duplicidade |
| Mercado Pago Pix / assinaturas SaaS | Conta recebedora, identidade PF/PJ, aprovação/KYC, Access Token, Webhook Secret, URLs | Cobrança e assinatura em sandbox oficial; liquidação real apenas após autorização específica |
| Fiscal/SEFAZ/prefeitura/provider | Certificado A1 e senha, CSC e ID quando aplicável, parâmetros do emitente/UF/município, credenciamento oficial e ambiente de homologação | XML aceito/rejeitado pelo ambiente oficial, autorização/protocolo, eventos fiscais e arquivamento/reconciliação |
| iFood | Cadastro Professional **CNPJ**, app/sandbox e lojas de teste, Client ID/Secret, aprovação/homologação e autorização das lojas | Teste oficial completo de pedidos e estados pelo portal iFood |
| 99Food | Cadastro de parceiro, app/sandbox, documentação técnica autenticada/versão do contrato, credenciais e autorização dos estabelecimentos | Homologação sandbox/aceitação da plataforma; a falta do contrato ainda bloqueia parte da implementação interna |
| Keeta | Acesso parceiro, contrato/escopos e credenciais verificadas | Teste de integração oficial |
| WhatsApp Meta/Evolution | Instância/conta/número/autorização de canal e credenciais pertinentes | Mensagem real inbound/outbound com consentimento e estados conciliados |
| Gemini/Maps | A autoridade da plataforma já possui homologação registrada; novas contas, permissões ou cotas só se aplicam se a configuração original mudar | Regressão das capacidades efetivamente usadas pela Web, sem exigir nova homologação do provedor como desculpa para bug |
| SMTP/Brevo e domínio | Conta, domínio/sender autorizado, DNS/SPF/DKIM/DMARC quando exigido, credenciais | Mensagem real entregue, bounce e fluxo de recuperação |
| Infra física | Impressora, dispositivo, rede, ambiente/canais reais e operador | Teste físico documentado, não substituído por CI |
| Go-live | Autorização de alteração produtiva, dinheiro real, ativação do signup público | Monitoramento, canary e rollback |

## 3. Escopo que não pode ser camuflado como falha técnica

- **NFCore**: a integração Kordena → NFCore permanece `DEFERRED_BY_DESIGN` no cronograma aprovado. Construir o Fiscal V1 próprio não implica NFCore já conectado. Se a decisão de produto mudar, criar escopo explícito e integração separada; nunca inferir.
- **Campanhas pagas/Meta Ads**: fora do escopo V1 original; marketing orgânico/direto é o escopo registrado.
- **99Food**: antes classificada desabilitada/não anunciada no lançamento V1; a exigência atual de deixá-la configurável altera a meta de prontidão, mas não fornece automaticamente contrato/credenciais oficiais.

## 4. Ordem obrigatória de fechamento da construção

1. Sanar defects internos confirmados: cardápio IA na Web, CVM/estimativa versus ficha, controle de upload/revisão e PR #237 de dinheiro/estoque.
2. Fechar as composições Web/API e simulações completas de pagamento e fiscal. Registrar quando a única barreira remanescente for contrato externo indispensável.
3. Certificar iFood e Keeta com contratos públicos disponíveis. Preparar 99Food até o limite verificável, rastrear contrato externo faltante sem fingir 100%.
4. Certificar assistente, PDV, Salão, Garçom, KDS, Delivery, estoque, financeiro, impressão, fiscal, Gerente IA e Command como jornadas encadeadas; executar permissões e isolamento adversarial.
5. Executar regressão total Python/Node/TypeScript/Playwright/PostgreSQL; zero falhas bloqueantes. Fixar SHA, CI exact-head, evidência de cada botão/rota, migrations fresh/upgrade e rollback.
6. Só classificar `CONSTRUCAO_INTERNA_100 = PASS` com evidência rastreável por requisito, ou reclassificar explicitamente uma dependência de especificação externa que impede construir a integração. Não usar semântica comercial enganosa.
7. **Só depois** iniciar testes de contas, sandbox oficial, certificados e homologações reais; e **só após autorização** promover a `production` na Contabo.

## 5. Gate factual nesta data

```text
CURRENT_PRODUCTION = fe25ecf2fefb23ee4f3fd3fde9bdb6c8c8a28c7a
CHECKOUT_CASH_FIX = PR_237_DRAFT_NOT_DEPLOYED
CARDAPIO_AI_WEB_GOVERNED_ROUTER = FIX_CANDIDATE_NOT_YET_CERTIFIED
FISCAL_EXTERNAL_TRANSPORT = NOT_PROVEN_IN_WEB_PRODUCTION
IFOOD_EXTERNAL_APPROVAL = PENDING
99FOOD_RUNTIME = NOT_COMPOSED
PRODUCTION_DEPLOY_AUTHORIZED = NO
CONSTRUCAO_INTERNA_100 = NOT_YET_PROVEN
EXTERNAL_HOMOLOGATIONS = SEPARATE_FUTURE_GATE
```

**Este documento é inventário de evidências e plano de correção, não certificado de conclusão integral.** Toda revisão deverá substituir status apenas com testes, SHA e resultado verificáveis.
