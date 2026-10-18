# KORDENA V1 — PENDÊNCIAS DE INTEGRAÇÃO E CONCLUSÃO DO AI FINOPS E CONTROLE DE FRANQUIAS

**FM Tecnologia | Documento técnico de continuidade e execução**  
**Data:** 18/10/2026  
**Situação:** PENDENTE DE INTEGRAÇÃO, TESTES E CERTIFICAÇÃO — NÃO CONCLUÍDO  
**Prioridade:** P0 para lançamento comercial com franquias de IA  
**Repositório:** `faabio3131/fm-ai-platform` (privado)  
**Base examinada:** `staging/kordena-premium`, commit `d300ab1e2e01b004b45152c1c91d099731a4d6e0`  
**Natureza desta entrega:** documentação e auditoria de leitura. Nenhum código funcional, deploy, migration de produção, preço ou plano comercial foi alterado.

## 1. Decisão e objetivo

**Preservar e concluir o AI FinOps que já existe. Não criar outro FinOps, outro cadastro de planos, outro sistema de cobrança ou uma nova infraestrutura.** O produto usa a estrutura existente do Kordena e a autoridade comercial do FM Command. Este documento consolida as integrações faltantes para que a V1 controle franquias por cliente/unidade, calcule custos de IA, mostre consumo e avisos ao contratante e bloqueie automaticamente novas operações de IA pagas antes de ultrapassar os limites financeiros.

Uma pergunta comum à IA **não depende de aprovação humana** nem de chamada remota síncrona ao FM Command. A política contratual é previamente sincronizada e executada localmente pelo backend. Confirmação humana continua exigível para **novas cobranças** ou ações de negócio críticas, não para fazer perguntas.

**Não aprovar preços ou franquias numéricas a partir deste documento.** Quantidades de créditos, teto financeiro, limites de áudio, mensagens e demais faixas deverão ser definidos após testes reais e simulações de custo.

## 2. Inventário do patrimônio técnico já implementado

| Parte existente | Evidência no repositório | Resultado verificado |
|---|---|---|
| Tela web AI FinOps | `web/src/app/admin/ai-finops/page.tsx`; `web/src/features/backoffice/ai-finops/components/AIFinOpsWorkspace.tsx` | Interface read-only: tentativas, sucesso, fallback, latência, tokens, custos conhecidos por moeda, cobertura de custo e mix de modelos; filtros de período |
| Cliente HTTP web | `web/src/features/backoffice/ai-finops/services/ai-finops-api.ts` | Consulta `GET /v1/ai-finops/resumo` com sessão autenticada |
| API e segurança | `http_api/ai_finops.py` | Exige `admin.acessar` e `financeiro.visualizar`; escopo da sessão por tenant e unidade; não aceita headers como autoridade |
| Contrato de uso | `core/ai_router.py` (`AIUsageEvent`) | Tenant, unidade, request/correlation, capability, provider/model, tokens, latência, outcome, fallback, snapshot e custo opcional |
| Persistência do uso | `infra/ai_metering.py` | Tabela `fm_ai_usage_events_v1`, persistência independente da transação operacional e chave idempotente por evento |
| Pricing Catalog | `core/ai_pricing.py` | Snapshots versionados, vigência e tarifas por componente com validação de ambiguidades |
| Calculadora financeira | `core/ai_cost.py` | Estimativa determinística em `Decimal`; custo observado/estimado/indisponível; moedas preservadas |
| Agregador | `infra/ai_finops_projector.py`; `infra/ai_finops_models.py` | Projeção incremental de eventos em agregados diários, em lotes, com prevenção de duplicidade |
| Consulta dos agregados | `infra/ai_finops_read_model.py`; `application/ai_finops_dashboard.py` | Leitura eficiente e isolada por tenant, unidade e período, sem varrer eventos brutos na tela |
| Tela histórica | `infra/streamlit_app/ai_finops.py` | Outra interface read-only do mesmo domínio; **não criar nova fonte de verdade** |
| Base comercial | `core/comercial/entitlement.py`; `application/commercial_entitlement.py` | Capacidades por plano, `enabled`, `limit_value`, `limit_unit`, `config`, snapshots/versionamento e avaliação local |
| Tela de assinatura | `web/src/app/admin/assinatura/page.tsx`; `web/src/features/commercial/components/CommercialAccountWorkspace.tsx` | Plano, assinatura, período e estado de acesso comercial |
| Migração declarada | `migrations/ai_finops_read_model_v1.py`; `migrations/runner.py` | Migration `0032_ai_finops_read_model_v1` presente em código; aplicação em produção **não certificada por esta leitura** |

**Proteções que precisam ser mantidas:** RBAC, step-up administrativo, isolamento de tenant/unidade, trilha de auditoria, idempotência, ausência de prompt/PII em telemetria econômica por padrão, valores monetários não inventados e separação entre o faturamento da FM e o financeiro dos restaurantes.

## 3. Lacunas identificadas e respectivas evidências

| ID | Situação | Evidência/constatação | Prioridade |
|---|---|---|---|
| FIN-01 | **Cálculo monetário não conectado à rota principal examinada** | `core/ai_router.py`, método `_registrar()`, emite `custo_real_calculado=None` e `moeda=None`; `application/ai_router_runtime.py` constrói o roteador sem injetar a calculadora. A calculadora existe separadamente. Verificar quaisquer outras rotas antes da correção. | P0 |
| FIN-02 | **Franquia e saldo comercial não integrados ao ledger de IA** | Entitlements possuem campos de limite, porém `application/commercial_entitlement.py` em `avaliar_local()`/`exigir_capacidade()` comprova habilitação da capability; não consome quantitativo nem reserva orçamento nessa avaliação. | P0 |
| FIN-03 | **Bloqueio de custo antes do provedor não demonstrado** | `AIModelRouter.executar()` chama o executor por rota e registra uso posteriormente; não foi identificado, nesse fluxo, um gate atômico de orçamento antes da chamada paga. | P0 |
| FIN-04 | **Barra de franquia, saldo e alertas ao cliente ausentes da tela examinada** | `AIFinOpsWorkspace.tsx` não exibe percentual de franquia, saldo contratual, ciclo de renovação ou avisos de 70%/90%/100%. | P1 |
| FIN-05 | **Agendamento contínuo do projetor não comprovado** | A classe `AIFinOpsProjector.project_batch()` e seus testes existem, porém não foi comprovada nesta inspeção a ligação com job periódico efetivo no runtime. | P0/P1 |
| FIN-06 | **Preço não conhecido ainda existe como possibilidade operacional** | A rota possui snapshot legado `legacy-unpriced-v1`; o painel distingue custo desconhecido e conhecido. Sem preço confiável não pode haver concessão financeira ilimitada. | P0 |
| FIN-07 | **Separação da apresentação comercial e financeira interna** | A tela atual mostra custos por moeda e mix provider/model. O cliente precisa de créditos/saldo; custo de fornecedor/margem da FM não deve ser exposto. | P1 |
| FIN-08 | **Sincronização do orçamento com o Command e renovação contratual** | Arquitetura comercial do Kordena existe, porém não se demonstrou nesta auditoria um contrato ponta a ponta com alocação/revogação/versionamento de saldo de IA por ciclo. | P0 |
| FIN-09 | **Prova integral em runtime produtivo** | Testes de unidade/API/fitness existentes não substituem teste real integrado com Postgres, múltiplas chamadas simultâneas e cobrança/uso de provedor. | P0 |

**Critério de interpretação:** “não comprovado” não significa “inexistente em todo o projeto”; exige rastreamento do caminho completo antes de criar ou refatorar código. A inspeção foi de código remoto, sem novos testes nem acesso a faturas oficiais de IA.

## 4. Arquitetura-alvo, conservadora e sem duplicação

```text
FM Command (control plane comercial, preços, plano, assinatura, orçamento)
    │ políticas versionadas / revisão / vigência / revogação
    ▼
Kordena — Commercial Entitlement local (PostgreSQL Railway)
    │ tenant + unidade + capability + ciclo + permissão
    ▼
AI Budget Guard / Ledger de franquia (NOVA INTEGRAÇÃO, não novo ERP)
    │ reserva atômica + limites por tarefa e simultaneidade
    ├── negado ──► resposta funcional clara, SEM nova chamada paga
    └── autorizado
           ▼
AI Model Router EXISTENTE → OpenAI/Gemini → AI Usage Metering EXISTENTE
           │                          │
           └──── confirma/corrige saldo e custo por snapshot versionado
                                      ▼
                       AI FinOps Projector / Read Model EXISTENTES
                                      ▼
           AI FinOps EXISTENTE (visão do cliente) + FM Command (visão interna)
```

- O **FM Command** governa o contrato e a franquia; não precisa responder a cada pergunta.
- O **Kordena** mantém orçamento local autorizado e impede consumo indevido mesmo se o Command estiver temporariamente indisponível; políticas vencidas/revogadas seguem fail-closed no escopo de IA paga.
- O **PostgreSQL transacional** é a autoridade de saldo, reserva, débito e reversão; contadores em tela e agregados diários são apenas projeções.
- **Não usar somente o dashboard ou o projetor para bloquear**, pois agregação assíncrona tem atraso.
- **Não depender apenas dos limites de fornecedor**: são defesa complementar e podem sofrer atraso de aplicação.
- **Não incluir LLM** no cálculo financeiro; cálculo deve ser determinístico e de custo baixo.

## 5. Contrato funcional obrigatório de franquias

**Escopos:** produto `KORDENA`, `product_account_id`, `tenant_id`, unidade, ciclo contratual, capability, versão do plano, revisão da política e moeda-base de custo. O consumo da unidade deve ser atribuído ao cliente correto; filiais não podem obter saldo de outras unidades. Configuração por plano e eventual saldo compartilhado entre unidades exige política explícita.

**Limites simultâneos:** franquia comercial visível (créditos), teto de custo interno da FM (moeda com câmbio e margem conservadora versionados), limite máximo por solicitação/cadeia de agentes, controles por modalidade (texto, áudio, imagem, automação, WhatsApp) e rate/concurrency limits. Não pressupor que 1 mensagem = 1 unidade financeira.

**Máquina de estados mínima da reserva:** `requested → reserved → committed` ou `released`; quando houver timeout ou uso indeterminado, `pending_reconciliation` até prova do débito. Cada transição com idempotency key, request/correlation, tenant/unidade, cycle ID, valores e audit trail. O estado financeiro não pode ser debitado duas vezes por retry/fallback.

**Cálculo de disponibilidade:** `saldo = orçamento do ciclo + expansões confirmadas - consumo confirmado - reservas pendentes`. Nenhuma operação nova pode exceder o orçamento real, mesmo sob concorrência. Reservar também cada possível fallback/call adicional, com cap global por tarefa. Se custo final exceder a reserva por anomalia, reter bloqueio, registrar diferença e investigar; não desbloquear o cliente por estimativa conveniente.

**Estimativa e conciliação:** adotar snapshot efetivamente vigente do modelo; contabilizar tokens de entrada, saída, cache e modalidade, inclusive raciocínio quando cobrado; utilizar dados oficiais de uso quando disponíveis; registrar custo conhecido ou desconhecido com proveniência; reconciliar periodicamente com o provedor. Preços, câmbio, arredondamento, buffers e validade precisam ser versionados. Na ausência de cálculo seguro, negar nova execução paga ou usar rota comprovadamente coberta pela política, nunca liberar consumo irrestrito.

**Cobranças:** renovação e aquisição de franquia extra só após evento comercial validado, conciliado e autorizado pelo titular. Nunca realizar auto-upgrade ou cobrar excedentes automaticamente sem consentimento contratual. O bloqueio de IA não bloqueia o ERP determinístico: PDV, pedidos, cozinha, salão, estoque e caixa permanecem operacionais conforme demais direitos do contrato.

**Sem latência de aprovação:** toda consulta usa avaliação local e transação curta para reserva, sem ida síncrona ao Command, sem requisição extra de modelo para precificação e sem interação humana para perguntas comuns.

## 6. Evolução da tela AI FinOps existente

### Área visível para proprietário autorizado

- **Plano e ciclo de assinatura**: nome comercial, data de renovação e franquia do período.
- **Consumo da franquia**: créditos contratados, consumidos, reservados/em processamento e disponíveis, com percentual consistente com ledger autoritativo.
- **Alertas persistentes**: primeiro aviso ao atingir 70%; aviso destacado e permanente a partir de 90%; aviso de indisponibilidade da IA paga a 100% ou ao esgotar o teto financeiro interno. Percentuais são **política inicial proposta, configurável**, não valor de preço/plano aprovado.
- **Histórico de consumo**: intervalos, funcionalidades/categorias e eventos; sem dados financeiros internos nem prompts.
- **Transparência**: não usar termos “IA ilimitada” nem misturar créditos do cliente com dólares/tokens do fornecedor. Mostrar o motivo do limite e data de renovação; oferta de expansão somente se houver produto comercial autorizado.
- **Responsividade/acessibilidade**: desktop/mobile, estados de loading, erro, sem dados, quase no limite e esgotado; mensagem compreensível mesmo sem acesso ao painel técnico.

### Área administrativa FM Command / plataforma

- Custo por cliente e unidade, provider/model, moeda, tokens, reservas, gastos, custo desconhecido, divergência de conciliação, margem estimada e alertas de risco; visões globais sujeitas a autorização de plataforma, nunca a RBAC de um restaurante.
- Custos de infraestrutura alocados por metodologia explícita não devem ser apresentados como reais se não houver fonte comprovada.

**A tela FinOps existente deve ser estendida, não substituída.** Preservar indicadores atuais de sucesso, fallback, latência e mix em contexto adequado; manter a tela de “Plano e Assinatura” como superfície do contrato e usar FinOps como superfície do consumo.

## 7. Plano de execução — pendências rastreáveis

- [ ] **P0-01 — Auditoria de rotas:** inventariar todas as chamadas pagas OpenAI/Gemini (gerente, assistente, áudio, documentos, jobs, fallback, automações), identificar qualquer caminho que bypassa o router/medidor; reconciliar código com execução real.
- [ ] **P0-02 — AI Pricing + Metering:** ligar calculadora ao evento real, resolver snapshot válido e moedas; tratar custo desconhecido, cache e modalidades; demonstrar uso em provedor real e reconciliação.
- [ ] **P0-03 — Ledger + Budget Guard:** implementar migration aditiva, orçamento e reservas atômicas por tenant/unidade/ciclo e por tarefa; proteção contra concorrência, idempotência, retries e timeout; rollback seguro.
- [ ] **P0-04 — Entitlements e Command:** aproveitar limites/versionamento existentes; definir payload assinado/autenticado de orçamento e política, renovação, expiração, revogação, downgrade/upgrade e comprovação de pagamento sem gerar direitos duplicados.
- [ ] **P0-05 — Cobertura de todas as entradas:** aplicar o guard antes de toda chamada com custo, inclusive fallback e agentes internos; rate limit, max tokens, max steps e cap financeiro por tarefa.
- [ ] **P0-06 — Atualização do projetor:** comprovar ou configurar job leve e durável; medir atraso, retry e idempotência; nunca usar agregado diário como contador de bloqueio.
- [ ] **P1-07 — Evolução visual da FinOps:** reutilizar a página existente, criar resumo comercial/saldo e avisos 70/90/100, sem remover KPIs e sem expor custo privado da FM.
- [ ] **P1-08 — Notificações:** avisos de limiar idempotentes por ciclo e canal; não gerar spam; incluir banner persistente e histórico de aviso.
- [ ] **P1-09 — Planos e franquias:** medir custo real por tipo de operação e volume, definir números para os quatro códigos comerciais versionados, validar margem por plano; submeter preços à aprovação do proprietário.
- [ ] **P0-10 — Certificação e release:** cumprir gates, documentação, PR, reconciliação de SHA, Postgres real, teste de carga/concurrency e provider real; deploy produtivo apenas após autorização específica e Visual Premium/release gates aplicáveis.

## 8. Matriz mínima de testes obrigatórios

| Prova | Resultado exigido |
|---|---|
| Concorrência de 20+ solicitações e saldo para apenas algumas | Apenas reservas que cabem no saldo são aceitas; jamais saldo negativo |
| Duplicação de evento/idempotency key | Um único débito e uma única transição efetiva |
| Fallback após timeout | Nova rota só começa com reserva própria; reconciliar custo desconhecido da primeira |
| Falha do Command | Consultas comuns seguem com orçamento local válido; políticas sem validade segura não liberam IA paga |
| Falha do ledger/banco ou snapshot de preço | Não iniciar chamada paga não coberta; ERP permanece funcionando |
| Cliente muda de unidade / tenta spoofing de tenant | Sem saldo ou histórico cruzado; identidade sempre da sessão |
| 70%, 90%, 100% e renovação | Banner correto, aviso sem duplicidade, reabertura apenas com novo ciclo confirmado |
| Upgrade, downgrade, cancelamento e reembolso | Regras de saldo explícitas, versionadas, auditáveis e sem cobrança surpresa |
| Moedas diferentes e reajuste do fornecedor | Custos segregados e reconciliação por snapshot; ausência de mistura USD/BRL |
| Fluxo real por modelo/modalidade | Tokens, custo, reservas, saldo e fatura reconciliam com evidência |
| Carga/pico de pedidos sem IA | ERP operacional não sofre bloqueio causado pela franquia de IA |
| Interface do proprietário e FM | RBAC/step-up, informação adequada, nenhum custo interno indevido exposto |

## 9. Gates de conclusão — definição inequívoca de “100%”

Uma entrega parcial de interface, testes unitários ou o simples registro de tokens **não fecha** esta pendência. O status só muda para **CONCLUÍDO/CERTIFICADO** quando:

1. Todas as chamadas de IA pagas, inclusive fallback/automação, passarem pelo bloqueio preventivo governado; nenhuma rota de bypass conhecida.
2. O custo real/estimado e as reservas forem persistentes e reconciliáveis por cliente, unidade e ciclo, com política de valores desconhecidos.
3. A franquia exibida na FinOps coincidir com o ledger financeiro autoritativo; alertas e bloqueios funcionarem sem interromper o ERP.
4. O Command administrar políticas/assinaturas sem estar no caminho crítico de cada consulta de IA; renovações e ampliações dependam de eventos comerciais comprovados.
5. Migrations fresh/upgrade e rollback, testes de concorrência e regressão, segurança multi-tenant, navegador/mobile e integração com provedor real estiverem verdes e com evidências.
6. Documento Mestre, System Design/ADR, `AGENTS.md`, inventário, tracker e PR estiverem reconciliados com o SHA canônico; CI pós-merge 100% verde; deploy tiver aprovação própria.
7. Valores de franquia e mensalidade tiverem sido **explicitamente aprovados**, com custos medidos e margem alvo demonstrada.

**Não declarar esta etapa “100% concluída” antes desses sete critérios.** Reaproveitar os artefatos existentes; jamais reescrever partes certificadas por conveniência.

## 10. Evidências e referências técnicas

- [AI FinOps web](../../web/src/features/backoffice/ai-finops/components/AIFinOpsWorkspace.tsx) e [API](../../http_api/ai_finops.py).
- [Router e AIUsageEvent](../../core/ai_router.py), [composition root](../../application/ai_router_runtime.py), [metering](../../infra/ai_metering.py).
- [Catálogo de preços](../../core/ai_pricing.py), [calculadora](../../core/ai_cost.py), [projetor](../../infra/ai_finops_projector.py), [read model](../../infra/ai_finops_read_model.py).
- [Entitlement comercial](../../application/commercial_entitlement.py), [ADR de planos](./adrs/ADR-KCA-004-four-plans-versioned-catalog.md), [ADR Command Billing](./adrs/ADR-KCA-011-command-product-billing-control-plane.md).
- [Testes de certificação WP-019](../../tests/api/test_wp019_ai_finops_certification.py), [teste de metering durável](../../tests/unit/ai_router/test_ai_usage_durable_metering.py), [teste de custo](../../tests/unit/ai_router/test_cost_calculator.py), [teste de projeção](../../tests/fitness/test_af23_ai_finops_projection.py).
- [Documento de certificação histórica WP-019](../web-parity/WP019_AI_FINOPS_CERTIFICACAO.md) — representa evidência histórica, não aprovação comercial desta pendência.

## 11. Registro de governança

**STATUS ABERTO — PENDENTE DE INTEGRAÇÃO E CONCLUSÃO.** Este documento registra o escopo para um executor, não autoriza publicação em produção, contratação de serviços, mudança de valores, emissão de cobrança, migration com dados reais ou conclusão fictícia de testes.

Branch documental separada, PR em rascunho para `staging/kordena-premium`, sem merge. O próximo executor deverá ler `AGENTS.md`, Documento Mestre e System Design, confirmar HEAD e pendências atuais, executar em camadas testadas e atualizar este mesmo documento à medida que surgirem evidências. Manter a distinção entre **implementado no código**, **integrado**, **testado**, **homologado** e **publicado**.