# INVENTÁRIO DO PATRIMÔNIO NOVO V1 — CONSTRUÍDO, REUTILIZÁVEL E AINDA NÃO CORTADO PARA O RUNTIME COMERCIAL

**Projeto:** Kordena / GERENTE AI V1.0  
**Base auditada:** `fix/v1-auth-streamlit-login-input` @ `f3a0a4a31d92b5e5b6cd6e2adc2415337ac48157`  
**Documento de recuperação:** Issue #62  
**Regra:** este inventário não substitui o Documento Mestre. Ele identifica patrimônio técnico que deve ser **implantado/cortado**, não reescrito.

## 1. Critério deste inventário

Um item entra aqui quando:
- existe implementação nova/canônica no repositório;
- a implementação está alinhada às autoridades atuais de domínio (tenant/unidade, RBAC, idempotência, UoW/eventos/auditoria quando aplicável);
- ela é tecnicamente aproveitável e não deve ser descartada;
- porém o `app.py`, a UI comercial, o provider real, a migration do ambiente ou o fluxo físico ainda não fizeram o cutover completo.

**Importante:** “reutilizável/canônico” não significa “100% homologado”. A homologação final continua dependendo do Documento Mestre, Commercial Runtime E2E e teste físico/manual no mesmo SHA.

---

## 2. Resumo executivo

| Patrimônio novo já construído | Qualidade arquitetural atual | Situação comercial | Ação econômica |
|---|---|---|---|
| Pedido V1 autoritativo | ALTA | Não é a autoridade de todos os canais comerciais | Implantar/cortar, não reescrever |
| Checkout canônico | ALTA | Não é a única entrada comercial | Tornar fronteira única |
| Pagamento + VendaFinanceira V1 | ALTA | PDV ainda híbrido/legado | Cortar PDV/canais para este domínio |
| Estoque ledger/reserva V1 | ALTA, com risco de replay já documentado | Aba Estoque e parte do PDV ainda legadas | Integrar e completar hardening necessário |
| Event Bus / Outbox / Auditoria | ALTA | Infra disponível, uso depende do cutover | Reusar transversalmente |
| PDV autoritativo V1 | ALTA no backend | Runtime normal ainda forçado a LEGACY | Fazer cutover governado |
| Central de Pedidos V1 | ALTA | Já aparece no app, mas depende de Pedido real chegando | Alimentar por todos os canais |
| KDS V1 | ALTA | UI comercial existe, fluxo integrado ainda incompleto | Conectar ao Pedido/Estoque/canais |
| Salão/Comandas V1 | ALTA no domínio, composição comercial incompleta | UI ainda usa helpers/contexto de teste | Substituir composição, preservar domínio |
| Garçom V1 | ALTA no serviço | Não está no app comercial e UI usa teste | Criar composition root comercial |
| Impressão por Setor V1 | ALTA no spool/domínio | Sem adapter físico/composição comercial | Ligar KDS + impressora real |
| Expedição/Entrega V1 | ALTA no domínio/repositório | Não está no app; contexto da UI ainda test-only | Compor com identidade/eventos reais |
| Delivery Próprio V1 | BOA no domínio | Runtime/ports concretos ainda de teste | Implementar adapters canônicos, não reescrever regras |
| CRM/Consentimento V1 | ALTA no domínio | UI principal continua CRM/Cliente legado | Cortar UI/transporte/benefícios para CRM canônico |
| Marketplaces V1 | ALTA na arquitetura de inbox/outbox/adapters | Transportes reais/homologação externos pendentes | Compor providers oficiais e Central |
| Gerente IA/Core V1 | ALTA | Runtime/HTTP existem; integração transversal depende dos cutovers | Expor no produto e ligar domínios aprovados |
| AI Model Router / Metering | ALTA | Backend existe; maturidade de providers ainda parcial | Reusar como gateway cognitivo padrão |
| AI FinOps | ALTA | Tela existe; migration 0032 pendente no banco atual | Aplicar migration e validar projeção |
| Notificações internas | ALTA no domínio | Não é ainda fluxo comercial unificado | Integrar Administração/alertas |
| Campanhas governadas | ALTA na governança | Publicação externa real ainda não concluída | Conectar CRM + transporte autorizado |

---

## 3. Patrimônio prioritário para CUTOVER — não reescrever

### 3.1 Pedido V1 autoritativo

**Já existe**
- `core/pedidos/*`;
- `core/pedidos/servicos.py`;
- `core/pedidos/adaptador_sqlalchemy.py`;
- models ORM de Pedido/itens/adicionais/observações/eventos;
- idempotência, versão/CAS, tenant/unidade e eventos;
- migration comercial oficial `0004_orders_authoritative_v1`.

**Também existe a entrada canônica**
- `application/checkout.py` declara explicitamente que **PDV, Assistente, Salão, Delivery e marketplaces devem entrar por esta fronteira**.

**Ainda não implantado por completo**
- o PDV comercial não usa Pedido V1 como única autoridade;
- Assistente ainda não usa checkout canônico;
- Delivery próprio ainda usa portas/runtime de teste;
- Marketplaces ainda não convergem de ponta a ponta para Pedido no runtime real;
- Salão ainda não executa toda jornada comercial pelo caminho canônico.

**Decisão:** preservar integralmente e promover a **única porta de criação/checkout de pedido**.

---

### 3.2 Checkout canônico V1

**Já existe**
- `application/checkout.py`;
- cria Pedido;
- cria obrigação de Pagamento;
- reserva Estoque;
- usa uma UoW;
- propaga contexto tenant/unidade;
- cria eventos/outbox/auditoria;
- separa permissões internas por capacidade.

**Ainda não implantado**
- não é a fronteira única chamada pelo `app.py` e por todos os canais.

**Decisão:** este deve ser o centro do cutover comercial. Não criar checkout novo.

---

### 3.3 Pagamentos + VendaFinanceira + finalização autoritativa

**Já existe**
- `core/pagamentos/*`;
- obrigações, transações, confirmação, reconciliação, estorno e VendaFinanceira;
- métodos dinheiro, Pix, crédito, débito, voucher, pagamento na entrega e recebimento posterior;
- valores em `Decimal`;
- idempotência e eventos;
- migration comercial `0005_payments_authoritative_v1`;
- `application/finalizacao_pagamento.py` para concluir efeitos após liquidação eletrônica confiável;
- ligação com Pedido e consumo da reserva de Estoque;
- projeção legada compatível apenas como borda de transição.

**Já existe também**
- fluxo Pix por Control Plane no PDV;
- consulta/recuperação de status e confirmação somente por fonte confiável;
- persistência durável de pendência/finalização no runtime V1.

**Ainda não implantado completamente**
- o PDV normal continua com autoridade econômica híbrida/legada;
- Assistente não inicia pagamento por este domínio;
- Salão ainda possui helper de pagamento de teste;
- Dashboard financeiro ainda lê `Venda` legada.

**Decisão:** cortar todos os canais para Pagamento/VendaFinanceira V1; manter projeção legada somente por compatibilidade até aposentadoria.

---

### 3.4 Estoque V1 — ledger, reserva, consumo, liberação e compensação

**Já existe**
- `core/estoque/*`;
- ledger append-only;
- saldo físico/reservado/disponível;
- reserva por snapshot da ficha;
- consumo/liberação idempotentes;
- perda, devolução, ajuste e compensação governados;
- RBAC, tenant/unidade e auditoria;
- adapter SQL;
- migration comercial `0006_stock_authoritative_v1`;
- `application/checkout.py` já reserva estoque;
- `application/finalizacao_pagamento.py` já consome reserva no fluxo previsto.

**Risco técnico já conhecido**
- documentação registra necessidade de sequência causal monotônica persistida antes de usar replay como fonte definitiva sob concorrência de produção.

**Ainda não implantado**
- aba comercial Estoque/Validades continua em `AplicacaoLegacyEstoqueV1`;
- cadastro/ajuste/inventário continuam sobre tabelas legadas;
- PDV não está integralmente cortado para ledger;
- Ficha Técnica/Produto comercial ainda são legados.

**Decisão:** preservar o ledger; corrigir somente o hardening necessário e ligar UI/PDV/produção. Não criar novo estoque.

---

### 3.5 Event Bus / Outbox / Auditoria

**Já existe**
- persistência do Event Bus;
- inbox/outbox/DLQ e contratos de evento;
- auditoria SQL;
- correlation/idempotency;
- migrations comerciais `0007_event_bus_persistence_v1` e `0008_audit_log_v1`.

**Ainda não implantado por completo**
- módulos legados do `app.py` ainda executam writes diretos fora do modelo canônico.

**Decisão:** usar essa infraestrutura como espinha transversal de todos os cutovers.

---

### 3.6 PDV autoritativo V1

**Já existe**
- `core/pdv/*`;
- repositórios SQL;
- roteamento/modes;
- claim idempotente de finalização;
- finalização pendente/durável;
- reconciliação;
- `application/checkout.py`;
- `application/finalizacao_pagamento.py`;
- migration comercial `0009_pdv_authoritative_runtime_v1`.

**Ainda não implantado**
- `core/pdv/configuracao.py` força `LEGACY` fora de `FM_AI_TEST_MODE=1`;
- `app.py` ainda usa `LegacyPDVSQLAlchemyAdapter`.

**Decisão:** patrimônio prioritário. Fazer canary/cutover comercial seguro; não desenvolver outro PDV.

---

## 4. Operação do restaurante já construída no backend

### 4.1 Central de Pedidos V1

**Já existe**
- `core/central_pedidos/*`;
- UI comercial `core/central_pedidos/ui_streamlit.py`;
- Application/UoW `application/central_pedidos_transacoes.py`;
- leitura somente de Pedido V1;
- contexto vindo da identidade autenticada;
- financeiro baseado em Pagamento/VendaFinanceira;
- comandos delegados ao Pedido autoritativo;
- auditoria/outbox.

**Situação**
- já está renderizada no `app.py`;
- não deve ser reescrita;
- porém ainda recebe pouco valor real enquanto PDV/Assistente/Delivery/Marketplaces não criarem todos os Pedidos canônicos.

**Decisão:** manter e alimentar pelo cutover dos canais.

---

### 4.2 KDS V1

**Já existe**
- setores de produção;
- roteamento idempotente;
- fila por setor;
- máquina de produção;
- SLA;
- CAS;
- RBAC;
- eventos;
- repository SQL;
- `application/kds_runtime.py`;
- `application/kds_transacoes.py`;
- UI comercial `core/kds/ui_comercial.py`;
- migration comercial `0010_kds_authoritative_runtime_v1`.

**Situação**
- já aparece no `app.py`;
- E2E histórico era isolado;
- falta provar e fechar a jornada real PDV/Salão/Delivery → Pedido → KDS → Estoque → Expedição.

**Decisão:** não reescrever KDS; completar integração e Commercial Runtime E2E.

---

### 4.3 Salão / Mesas / Comandas V1

**Já existe**
- `core/salao/*`;
- mesas/comandas/participantes;
- múltiplos pedidos por comanda;
- transferência/junção/separação;
- divisão e pagamento misto;
- versões/CAS;
- RBAC;
- repository SQL;
- `application/salao_transacoes.py`;
- schema incluído na migration comercial `0012_restaurant_operations_runtime_v1`.

**Problema de implantação**
- a UI ainda chama `preparar_schema_teste`;
- ainda cria `contexto_salao_teste`;
- o fechamento contém helper `registrar_pagamento_confirmado_teste_v1`.

**Decisão:** o domínio e persistência são patrimônio. Substituir apenas a composição de teste por identidade, Pagamento e migrations reais.

---

### 4.4 Garçom V1

**Já existe**
- `core/garcom/*`;
- serviço construído sobre **Salão + KDS autoritativos**;
- alçada por responsável;
- RBAC;
- alertas de item pronto;
- operações de comanda;
- `application/garcom_transacoes.py`;
- UI responsiva já construída.

**Problema de implantação**
- não está conectado ao `app.py`;
- UI ainda prepara schema/contexto de teste.

**Decisão:** preservar serviço/UI e trocar composition root; adicionar navegação/perfil e teste físico celular/tablet.

---

### 4.5 Impressão por Setor V1

**Já existe**
- `core/impressao/*`;
- spool persistente;
- deduplicação/idempotência;
- retry;
- reimpressão auditada;
- ticket minimizado sem PII financeira desnecessária;
- repository SQL;
- schema incluído em `0012_restaurant_operations_runtime_v1`.

**Ainda não implantado**
- falta adapter de impressora física/comercial;
- falta ligar eventos KDS ao spool no runtime real;
- não está na experiência comercial;
- `ImpressoraFake` existe apenas como adapter de teste e não pode ser provider comercial.

**Decisão:** manter spool/domínio; implementar somente o adapter físico e composição/eventos.

---

### 4.6 Expedição / Entrega V1

**Já existe**
- `core/entrega/*`;
- repository SQL;
- checklist;
- atribuição/re-atribuição;
- coleta;
- saída em rota;
- tentativa falha;
- prova mínima;
- conclusão logística sem inventar pagamento;
- RBAC expedição/entregador;
- idempotência/CAS;
- `application/entrega_transacoes.py`;
- schema incluído em `0012_restaurant_operations_runtime_v1`.

**Ainda não implantado**
- UI usa `contexto_entrega_teste`;
- não está no `app.py` comercial;
- falta ligação definitiva de eventos KDS/Pedido/Pagamento/Delivery.

**Decisão:** preservar domínio/repo/Application; criar composition root autenticado e conectar eventos.

---

### 4.7 Delivery Próprio V1

**Já existe**
- `core/delivery/servicos.py`;
- carrinho;
- catálogo;
- endereço;
- área por CEP;
- taxa/SLA;
- cupom;
- cashback;
- revalidação no fechamento;
- confirmação CAS/idempotente;
- pagamento;
- entrega;
- tracking;
- cancelamento;
- repetição de pedido;
- isolamento tenant/unidade/cliente.

**Ainda não implantado**
- `core/delivery/ui_streamlit.py` é test-only;
- `RuntimeDeliveryTeste` usa memória;
- usa `tenant-demo/unidade-demo/cliente-demo`;
- não há composition root comercial persistente;
- ainda não está conectado ao app, Google Maps real, CRM canônico, checkout canônico e Entrega real.

**Decisão:** preservar toda regra determinística do Delivery; escrever apenas adapters/composition/persistência necessários para delegar ao Pedido/Pagamento/CRM/Maps/Entrega canônicos.

---

## 5. Cliente, CRM e marketing já construídos

### 5.1 CRM / Consentimento / Conversão V1

**Já existe**
- `core/crm/*`;
- marketing negado por padrão;
- opt-in/opt-out append-only;
- cliente marketplace restrito;
- conversão consentida;
- HMAC/refs de contato;
- funil;
- benefícios por porta;
- idempotência;
- auditoria;
- migrations comerciais:
  - `0022_crm_clientes_persistencia_v1`;
  - `0023_crm_contact_vault_v1`;
  - `0024_crm_cliente_legado_mapping_v1`;
  - `0025_crm_contact_ownership_v1`;
  - `0026_crm_consentimentos_historico_v1`.

**Ainda não implantado**
- aba CRM do `app.py` consulta `Cliente` legado;
- cashback ainda é alterado com update/commit direto na UI;
- `core/crm/runtime_teste.py` ainda tem `EnvioMarketingFake`;
- falta composition root comercial e transporte real governado.

**Decisão:** preservar CRM canônico e migrations; substituir UI/transporte/benefícios legados.

---

### 5.2 Campanhas governadas

**Já existe**
- `application/campanhas_governadas.py`;
- `infra/gerente_ia/campanhas_governadas_sqlalchemy.py`;
- aprovação/publicação governadas;
- UoW;
- auditoria;
- confirmação humana;
- o método de publicação torna campanha publicável, **não inventa envio externo**.

**Ainda não implantado**
- falta transporte de campanha real conectado ao CRM/consentimento/canal homologado;
- falta UI/jornada comercial final.

**Decisão:** usar esta governança; não criar fluxo paralelo de campanha.

---

## 6. Marketplaces e omnicanal já construídos

### 6.1 Framework de Marketplaces

**Já existe**
- `core/marketplaces/*`;
- `ServicoMarketplaces`;
- integração/pedido externo;
- inbox/outbox/DLQ;
- retry/reconciliação;
- idempotência;
- atualização de status;
- adapters por plataforma;
- iFood HTTP com contrato estruturado;
- 99Food/Keeta fail-closed até contrato verificado.

**Ainda não implantado**
- iFood não possui transport/secret composition de rede real homologada no runtime comercial;
- 99Food/Keeta dependem de documentação/parceria oficial;
- não há cutover completo para Central/KDS/Estoque/Entrega;
- não está exposto como operação omnicanal no `app.py`.

**Decisão:** preservar framework; implementar transportes oficiais e composição real por provider.

---

## 7. Core / IA já construídos e não totalmente implantados

### 7.1 Gerente IA / Core V1

**Já existe**
- `core/gerente_ia/*`;
- tools tipadas;
- consultas e ações governadas;
- preview + fingerprint;
- confirmação humana;
- RBAC;
- tenant/unidade;
- auditoria;
- idempotência;
- campanhas governadas;
- `application/gerente_ia_runtime.py` como composition root de produção;
- `application/gerente_ia_transacoes.py`;
- endpoints HTTP em `http_api/app.py`;
- schema comercial `0013_core_runtime_v1`.

**Ainda não implantado**
- o `app.py` não oferece ainda a experiência final do Gerente IA;
- Assistente de Atendimento não usa este Core para jornada comercial;
- o Core só poderá atingir visão transversal plena quando os módulos operacionais estiverem cortados para fontes autoritativas.

**Decisão:** preservar integralmente; expor e conectar depois dos cutovers das fases correspondentes.

---

### 7.2 AI Model Router provider-neutral

**Já existe**
- `core/ai_router.py`;
- `application/ai_router_runtime.py`;
- rotas por provider/model/capability;
- fallback controlado;
- time/custo/uso;
- Control Plane de provider;
- medição de uso durável;
- desacoplamento de Gemini/fornecedor.

**Situação**
- já é usado pelo runtime do Gerente IA;
- ainda precisa evoluir catálogo de capacidades/providers conforme a V1;
- não deve ser substituído por chamadas diretas de SDK nas novas funcionalidades.

**Decisão:** gateway cognitivo padrão.

---

### 7.3 AI Usage Metering + AI FinOps

**Já existe**
- `infra/ai_metering.py`;
- persistência independente de sucesso/falha da transação de negócio;
- migration `0031_ai_usage_metering_v1`;
- read model/projetor FinOps;
- dashboard;
- migration `0032_ai_finops_read_model_v1`.

**Ainda não implantado no ambiente físico atual**
- o painel mostrou que `0032` ainda não está disponível nesse banco.

**Decisão:** aplicar migrations pelo runner canônico, projetar dados e testar no navegador; não reescrever FinOps.

---

## 8. Infraestrutura transversal já construída

### 8.1 Runtime comercial de migrations

**Já existe**
- `migrations/runner.py`;
- trilha comercial separada das migrations E2E históricas;
- migrations oficiais 0001–0032;
- história/fingerprint;
- migração aditiva;
- suporte a PostgreSQL comercial.

**Observação importante**
- vários arquivos históricos `migrations/*_v1.py` continuam deliberadamente test-only;
- isso não significa que o schema canônico não tenha migration comercial: o runner 0004–0013 cria os metadados autoritativos diretamente.
- novos agentes não devem confundir “migration histórica de E2E” com “runner comercial atual”.

**Decisão:** usar somente `scripts/migrate_v1.py` / runner oficial em ambiente comercial/homologação.

---

### 8.2 Notificações internas

**Já existe**
- `core/notificacoes_internas/*`;
- `application/notificacoes_internas.py`;
- diretório tenant-safe;
- preferências;
- idempotência de alertas;
- auditoria;
- migration `0029_internal_notification_recipients_v1`.

**Ainda não implantado**
- não há experiência unificada no app para configurar/operar todos os alertas internos;
- integração com alertas reais dos módulos ainda deve ser consolidada.

**Decisão:** reaproveitar no Painel Proprietário/Core/Estoque.

---

## 9. Itens que JÁ estão no runtime comercial e não devem ser tratados como “não implantados”

### Autenticação / RBAC / Administração
- login real;
- identidade por tenant/unidade;
- PIN administrativo;
- proteção de áreas sensíveis;
- session guard;
- diagnóstico temporário removido;
- watchdog de inatividade corrigido para renovar o grant somente com atividade real do usuário;
- gate automatizado atual no SHA `e56a2724d00bd3f27fcf3ae292310632e26045d8`;
- workflows `Auth RBAC Commercial Gate V1` de push e pull request: **success** no mesmo SHA;
- teste físico no navegador: **PASS** — após 3 minutos sem atividade real, a área administrativa sensível bloqueou automaticamente e voltou a exigir autenticação sensível;
- gate físico negativo de RBAC: **PASS** — usuário `caixa` autenticado no mesmo tenant/unidade recebeu acesso negado em `/Integracoes_e_Credenciais` por URL direta, sem exposição do conteúdo administrativo;
- jornada comercial do runtime real `app.py`: **PASS** para login → PIN → área sensível → timeout/relock → logout → login caixa → URL administrativa negada;
- nenhum blocker de código ou gate físico conhecido permanece para Auth/RBAC neste checkpoint;
- status de readiness: **COMMERCIAL_HOMOLOGATED** no SHA acima.

### Control Plane de Integrações e Credenciais
- UI comercial;
- vault cifrado;
- referências de segredo;
- healthchecks reais quando implementados;
- status/homologação;
- UoW/auditoria.
- ainda existem provedores externamente pendentes, mas a **plataforma de configuração** já está no caminho correto.

---

## 10. Ordem de implantação sem retrabalho

A ordem deve continuar sendo a do Documento Mestre. O inventário determina **o que reutilizar** em cada fase:

1. **Fechar Fase 2** — Auth/RBAC.
2. **Fase 3** — consolidar/homologar Control Plane existente.
3. **Fase 4** — cortar Assistente para Core + Checkout + Pedido + Pagamento + Estoque + CRM + Maps/Delivery; eliminar `OperacaoMicaFake`.
4. **Fase 5** — Painel Proprietário, reutilizando RBAC, Integrações, Notificações e configurações existentes.
5. **Fase 6** — cortar PDV para Checkout/Pedido/Pagamento/Estoque autoritativos; migrar dashboard financeiro.
6. **Fase 7** — Salão/Garçom: preservar domínio, substituir runtime_teste por composição comercial.
7. **Fase 8** — KDS: preservar; provar jornada integrada.
8. **Fase 9** — Impressão: preservar spool, adicionar adapter físico e eventos.
9. **Fase 10** — Expedição/Entrega: preservar domínio, substituir contexto de teste e integrar.
10. **Fase 11** — Delivery Próprio: preservar regras; criar adapters reais para os domínios canônicos.
11. **Fase 12** — Marketplaces: preservar framework; ligar transports oficiais.
12. **Fase 13** — CRM: preservar domínio/migrations; cortar UI/cashback/transporte.
13. **Fase 14+** — Gerente IA/Core e inteligência transversal sobre módulos já homologados.

---

## 11. Regra de preservação

Durante a recuperação:

- **NÃO reescrever** Pedido, Pagamento, Estoque, KDS, Salão, Garçom, Entrega, Delivery, CRM, Marketplaces, Core ou AI Router por estética.
- Reescrita só é permitida se a auditoria demonstrar erro estrutural incompatível com o Documento Mestre.
- Priorizar composition roots, adapters reais, migrations, integração, UI comercial, cutover e testes físicos.
- Legado pode sobreviver temporariamente apenas como compatibilidade/projeção, nunca como segunda autoridade depois do cutover.
- Fake/Mock/runtime_teste permanecem somente em testes.
- Todo cutover deve registrar **Current → Target → evidência → rollback**.

## 11.1 Ritual obrigatório após CADA etapa

Antes de iniciar a etapa seguinte, sem exceção:
1. confrontar o código/runtime recém-validado com este inventário;
2. atualizar `docs/commercial_runtime_readiness_v1.json`;
3. remover somente blockers que tenham evidência objetiva;
4. registrar SHA, teste automatizado, Commercial Runtime E2E e teste físico quando aplicáveis;
5. verificar se a etapa revelou patrimônio novo já existente que evite reescrita;
6. verificar se algum Fake/Mock/runtime_teste/Legacy voltou ao caminho comercial;
7. registrar o checkpoint na Issue de recuperação;
8. somente então liberar a próxima etapa do Documento Mestre.

Se inventário, código e evidência divergirem, a execução deve **STOP** até reconciliação. Nenhum agente pode avançar usando apenas memória de conversa.

## 12. Conclusão

O patrimônio novo é substancial. A maior parte do custo de domínio e arquitetura **já foi investida**. O problema central é que vários desses blocos ficaram em estado **BACKEND/TEST RUNTIME READY** sem chegar a **COMMERCIAL CUTOVER**.

A estratégia de menor custo e menor prazo é: **implantar o que já existe, fechar os adapters/composition roots faltantes e eliminar a autoridade legada/fake do caminho comercial**, módulo por módulo, na ordem do Documento Mestre.
