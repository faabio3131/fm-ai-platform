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

1. **Fase 2 — FECHADA / COMMERCIAL_HOMOLOGATED** — Auth/RBAC homologado no runtime físico.
2. **Fase 3 — APROVADA INTERNAMENTE / avanço liberado** — Control Plane existente preservado; Mercado Pago/PagBank e demais dependências exclusivamente externas permanecem como homologação externa pendente e não reabrem desenvolvimento interno.
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

## 10.1 Reconciliação forense Work × Drive × GitHub — 30/08/2026

Antes de qualquer novo código da Fase 4, foi reconciliado o patrimônio preservado do Work.

**Fonte preservada**
- pasta Drive: `KORDENA — STAB-01 — EVIDÊNCIAS E INVENTÁRIO — 2026-08-23`;
- HEAD forense original: `2fdb3824c96bfeeef0c1722b6b37609f77074553`;
- snapshot restaurável: 660 entradas = 609 tracked + 51 untracked;
- estado dirty preservado: 25 modified + 51 untracked = 76 arquivos;
- restauração descartável e SHA-256 dos 76 arquivos: PASS.

**Cópia física**
- worktree: `C:\\fm-ai-platform-fase4`;
- branch: `feat/v1-assistente-atendimento`;
- HEAD físico verificado: `2fdb3824c96bfeeef0c1722b6b37609f77074553`;
- portanto a cópia física parte exatamente do mesmo commit-base do snapshot forense STAB-01.

**Comparação exata do conteúdo dirty preservado contra a branch comercial atual**
- branch atual usada no navegador: `fix/v1-auth-streamlit-login-input`;
- SHA atual: `e56a2724d00bd3f27fcf3ae292310632e26045d8`;
- 76 arquivos do snapshot comparados por Git blob SHA;
- **4** permanecem byte-a-byte idênticos;
- **47** existem hoje, mas evoluíram;
- **25** continuam ausentes da branch atual;
- dos 25 ausentes, **11 são código produtivo** e **14 são testes**.

**Regra de recuperação**
- NÃO copiar o worktree físico inteiro sobre o canonical;
- NÃO reaplicar patch/snapshot em bloco;
- para os 47 arquivos evoluídos, a branch atual é a base e qualquer capacidade antiga deve ser portada seletivamente;
- para os 25 ausentes, recuperar somente o que ainda é válido perante Documento Mestre, System Design e interfaces atuais;
- preservar os snapshots Drive/PC como fonte forense e rollback patrimonial.

### 10.1.1 Patrimônio ausente prioritário — Assistente

Ainda ausentes da branch atual:
- `core/assistente_atendimento/atendimento_adapters.py`;
- `core/assistente_atendimento/atendimento_schemas.py`;
- `core/assistente_atendimento/atendimento_servicos.py`;
- `core/assistente_atendimento/cliente_adapters.py`;
- `core/assistente_atendimento/contexto.py`;
- `core/assistente_atendimento/entradas.py`.

Já existem e evoluíram na branch atual:
- `atendimento_modelos.py`;
- `checkout_adapter.py`;
- `erros.py`.

O serviço preservado implementa parsing estrito, resolução exata de catálogo, contexto tenant/unidade, cliente conhecido/novo, fingerprint de carrinho, confirmação explícita, reconfirmação em alteração, idempotência, handoff fail-closed e delegação ao checkout autoritativo.

**Decisão de cutover Fase 4:** recuperar/adaptar essas seis peças sobre as interfaces atuais e substituir a delegação comercial `core.mica/OperacaoMicaFake`; nunca sobrescrever os três arquivos que já evoluíram sem revisão de diff.

### 10.1.2 Patrimônio ausente prioritário — CRM dependência da Fase 4

Ainda ausentes:
- `application/crm_regularizacao_legado.py`;
- `infra/crm/cliente_legado_sqlalchemy.py`;
- `infra/crm/consentimentos_sqlalchemy.py`;
- `infra/crm/contatos_sqlalchemy.py`;
- `infra/legacy_customer_scope.py`.

Schemas/migrations correlatos já existem e evoluíram na branch atual.

O patrimônio preservado implementa ponte explícita legado→ClienteCRM, Contact Store cifrado `contact://`, isolamento tenant/unidade e persistência append-only de consentimentos.

**Decisão:** recuperar apenas as implementações que continuam compatíveis com os schemas/migrations atuais; usar CRM como dependência canônica do Assistente sem antecipar o cutover completo da UI de CRM da Fase 13.

### 10.1.3 Patrimônio PDV/Checkout

Os componentes centrais de cutover PDV e `application/checkout.py` já existem na branch atual e evoluíram em relação ao snapshot.

**Decisão:** não restaurar versões antigas. O snapshot serve apenas para conferir capacidades eventualmente perdidas. O cutover comercial do PDV permanece na Fase 6.

### 10.1.4 Mapa Current → Target do runtime comercial

| Área | Current no `app.py` | Target | Ação |
|---|---|---|---|
| Auth/RBAC | novo/comercial | homologado | preservar |
| Integrações | Control Plane novo | aprovado internamente; externos pendentes | preservar |
| Assistente | UI comercial já usa `RuntimeAssistenteAtendimentoV1`; `core.mica/OperacaoMicaFake` saiu do caminho comercial | serviço novo + Core/IA + CRM + checkout autoritativo + escopo restante da F4 | continuar Fase 4; não homologado ainda |
| Cardápio/Ficha | `AplicacaoLegacyCardapioV1` | fonte canônica/ponte governada | não criar autoridade paralela |
| PDV | `LegacyPDVSQLAlchemyAdapter` no runtime normal | checkout/Pedido/Pagamento/Estoque autoritativos | cutover Fase 6 |
| Estoque | `AplicacaoLegacyEstoqueV1` | `core.estoque` ledger/reserva/consumo | cutover Fase 6 |
| CRM UI | Cliente/cashback legado | ClienteCRM/consentimento/contact store | dependência F4 + cutover UI F13 |
| Financeiro | leitura de `Venda` legada | VendaFinanceira/Pagamentos | F6/F5 conforme Mestre |
| Central Pedidos | código novo atrás de readiness/flags | comercial integrado | provar na fase correspondente |
| KDS | código novo atrás de readiness/flags | comercial integrado | provar F8 |
| Salão | composição ainda contém test helpers | composition root comercial | F7 |
| Garçom | não composto no `app.py` | comercial | F7 |
| Impressão | não composta | spool + adapter físico | F9 |
| Expedição/Entrega | não composta / contexto de teste | comercial | F10 |
| Delivery próprio | runtime teste/demo | adapters canônicos | F11 |
| Marketplaces | framework sem composição real completa | providers oficiais | F12 |
| Gerente IA/Core | backend/composition root existe, experiência final não exposta | cérebro transversal | F14 após cutovers |
| AI FinOps | dashboard existe, migration física pendente | read model aplicado | gate de migration |

## 10.2 Checkpoint Fase 4 — corte inicial do Assistente no runtime comercial — 31/08/2026

**Branch:** `recovery/v1-fase4-assistente-cutover`  
**SHA técnico deste checkpoint:** `0b19b8a2a25e412254022d46a614e3814cc7c604`

**Recuperado e integrado neste checkpoint**
- seis peças do patrimônio STAB-01 do domínio/orquestração do Assistente foram recuperadas seletivamente e adaptadas às interfaces atuais;
- `ClienteCRMORM`, `ContatoCRMORM` e `RepositorioClientesCRMSQLAlchemy` foram recompostos sobre os schemas/migrations atuais;
- Contact Vault SQLAlchemy cifrado `contact://` foi restaurado como boundary de PII;
- foi criado `application/assistente_atendimento_runtime.py` como composition root comercial;
- o AI Model Router recebeu capability `ATENDIMENTO_INTERPRETACAO`, reutilizando o Control Plane homologado em vez de chamada direta a provider;
- a UI comercial do Assistente deixou de importar/chamar `core.mica` e agora recebe `CURRENT_IDENTITY` do `app.py`;
- cliente, catálogo, IA, confirmação, fingerprint, idempotência, handoff e checkout passam pelo novo runtime;
- `core.mica/OperacaoMicaFake` permanece apenas como histórico/teste isolado e não é mais caminho comercial.

**Provas automáticas**
- Commercial Runtime Readiness V1: **PASS**;
- Assistente Fase 4 Gate V1: **PASS**;
- compile dos componentes recuperados/comerciais: **PASS**;
- Ruff do recorte F4: **PASS**;
- testes direcionados do serviço/checkout + fitness de cutover: **PASS**.

**Status**
- `assistente_atendimento = CUTOVER_PENDING`;
- code blockers de dependência comercial de Mica: **0**;
- Commercial Runtime E2E: ainda não executado neste checkpoint;
- teste físico/browser: ainda não executado neste checkpoint;
- portanto este checkpoint **não** é homologação comercial da Fase 4.

**Escopo F4 ainda pendente antes do gate comercial**
- áudio/transcrição pela mesma validação autoritativa do texto;
- endereço/localização + Maps/área/taxa/ETA;
- dinheiro/troco e integração completa dos meios de pagamento; PIX permanece pendente de provider real conforme disponibilidade externa;
- snapshot/reserva de estoque pela ficha técnica autoritativa no checkout;
- handoff com contexto suficiente e retomada segura;
- consentimento/memória/CRM conforme finalidade;
- alteração/cancelamento/acompanhamento/reclamação sobre estados reais;
- integração e prova com KDS/expedição/delivery quando aplicável;
- Commercial Runtime E2E + navegador físico no mesmo SHA candidato.

**Ritual do inventário:** concluído para este checkpoint. Nenhum módulo posterior está liberado; a próxima tarefa permanece dentro da própria Fase 4.

## 10.3 Checkpoint Fase 4 — áudio/transcrição no mesmo runtime autoritativo — 31/08/2026

**SHA técnico validado:** `b1830d1d7dc9cf0a9537b5d2a2d8720de9bee03d`

**Implementado**
- `CapabilityIA.ATENDIMENTO_TRANSCRICAO` adicionada ao AI Model Router;
- `ConteudoAudioIA` provider-neutral com bytes ocultos de `repr`;
- Gemini recebe bytes somente no boundary `GoogleGenAITenantGateway`, via `types.Part.from_bytes`;
- `RuntimeAssistenteAtendimentoV1.interpretar_audio` transcreve pelo Control Plane e entrega a transcrição à mesma `EntradaAtendimento(AUDIO)` e ao mesmo `ServicoAssistenteAtendimento` usados pelo texto;
- UI comercial aceita upload de OGG/MP3/WAV/M4A/WebM e não cria caminho paralelo de pedido/checkout;
- falha de áudio/IA permanece fail-closed.

**Provas**
- Commercial Runtime Readiness V1: **PASS**;
- Assistente Fase 4 Gate V1: **PASS**;
- compile: **PASS**;
- Ruff: **PASS**;
- testes de serviço, checkout, AI Router, gateway Gemini e fitness comercial: **PASS**.

**Readiness**
- status continua `CUTOVER_PENDING`;
- SHA técnico registrado;
- Commercial Runtime E2E e teste físico continuam pendentes;
- áudio deixou de ser pendência de implementação interna, mas ainda precisa de prova física com provider/arquivo real no mesmo SHA candidato.

**Próxima tarefa F4**
- endereço/localização + Google Maps + área/taxa/ETA, reutilizando o Control Plane existente e sem duplicar domínio de Delivery.

## 10.4 Checkpoint Fase 4 — endereço/localização + Google Maps + área/taxa/ETA — 31/08/2026

**SHA técnico validado:** `0827fb21810e727fe76eae0aaf122800737c2f36`

**Implementado**
- o Assistente passou a cotar entrega no runtime comercial por `CotadorEntregaAssistenteGoogleMaps`, sem criar domínio paralelo de Delivery;
- a origem da unidade e as áreas de entrega passaram a ter persistência canônica tenant/unidade scoped em `delivery_origem_unidade_v1` e `delivery_areas_v1`;
- foi adicionada a migration comercial `0033_delivery_policy_v1`, aditiva, sem defaults silenciosos e com falha fechada quando origem/áreas não estiverem configuradas;
- o Google Maps existente passou a expor componentes do endereço geocodificado necessários à entrega: CEP, logradouro, número, bairro, cidade e UF;
- o runtime valida que o CEP informado é confirmado pela geocodificação e rejeita endereço incompleto;
- a política de área/taxa/SLA reutiliza a regra determinística já existente em Delivery, preservando isolamento por tenant/unidade;
- o cálculo de rota retorna distância e ETA pelo adapter Google Maps já governado pelo Control Plane;
- a cotação passa a compor o fingerprint do carrinho, exigindo nova confirmação se a entrega mudar;
- não foram introduzidos Fake/Mock/runtime_teste ou defaults comerciais para Maps/Delivery.

**Provas**
- Commercial Runtime Readiness V1 — run 78: **PASS**;
- Assistente Fase 4 Gate V1 — run 63: **PASS**;
- compile do recorte F4/Maps/Delivery: **PASS**;
- Ruff do recorte F4/Maps/Delivery: **PASS**;
- testes de geocodificação de endereço, política SQLAlchemy, migration 0033, serviço/checkout/AI Router e fitness comercial: **PASS**.

**Readiness**
- `assistente_atendimento` continua `CUTOVER_PENDING`;
- blockers de código conhecidos neste checkpoint: **0**;
- `commercial_runtime_e2e`: ainda não executado no SHA candidato final;
- `physical_test`: ainda não executado no SHA candidato final;
- portanto este checkpoint fecha a dependência interna de endereço/Maps/área/taxa/ETA, mas **não** homologa a Fase 4.

**Próxima tarefa F4**
- dinheiro/troco e integração completa dos meios de pagamento no Assistente, reutilizando Pedido/Pagamento/Checkout autoritativos e mantendo PIX dependente apenas da homologação externa real quando aplicável.

## 10.5 Checkpoint Fase 4 — forma de pagamento + dinheiro/troco governados — 31/08/2026

**SHA técnico validado:** `a3873086cb5a2af2d60459415d8e2cc95335937a`

**Implementado**
- a forma de pagamento passou a ser parte imutável do carrinho do Assistente antes da confirmação final;
- o método escolhido e, quando aplicável, o valor informado para troco entram no fingerprint, impedindo troca silenciosa do meio de pagamento depois da aprovação do cliente;
- o novo estado `AGUARDANDO_FORMA_PAGAMENTO` separa escolha financeira de confirmação definitiva do carrinho;
- dinheiro aceita pedido explícito de troco, valida que o valor recebido pretendido não seja inferior ao total e calcula apenas uma estimativa de troco;
- a solicitação de troco é persistida como `ObservacaoPedido` no Pedido canônico, com ID determinístico, mantendo o pedido como autoridade;
- o Assistente **não** chama `confirmar_pagamento` e não marca dinheiro, PIX ou cartão como pagos por declaração do cliente;
- liquidação manual continua permitida apenas pelo serviço financeiro autoritativo onde já previsto; pagamentos eletrônicos continuam dependentes da fonte financeira oficial;
- a UI exige aplicar a forma de pagamento antes da confirmação final, mostra claramente que a escolha não equivale a liquidação e exige nova confirmação se a forma mudar;
- o checkout continua criando somente a obrigação financeira canônica e preserva idempotência;
- não foi criado domínio paralelo de pagamentos nem integração fake.

**Provas**
- Commercial Runtime Readiness V1 — run 91: **PASS**;
- Assistente Fase 4 Gate V1 — run 76: **PASS**;
- compile do recorte F4: **PASS**;
- Ruff do recorte F4: **PASS**;
- testes direcionados: **51 passed**;
- fitness guard confirma que UI/runtime/serviço/checkout do Assistente não chamam `confirmar_pagamento` diretamente.

**Limite externo preservado**
- PIX real continua dependente de provider homologado por tenant/unidade e dos dados exigidos pelo provider;
- nenhum e-mail, CPF/CNPJ, confirmação de cartão ou retorno de gateway é inventado para contornar essa dependência;
- readiness registra `pix_provider_homologation_incomplete` como blocker externo, não como motivo para criar caminho alternativo inseguro.

**Readiness**
- `assistente_atendimento` continua `CUTOVER_PENDING`;
- blockers de código conhecidos neste checkpoint: **0**;
- `commercial_runtime_e2e`: ainda não executado no SHA candidato final;
- `physical_test`: ainda não executado no SHA candidato final;
- este checkpoint fecha a parte **interna** de forma de pagamento/dinheiro/troco e preserva o PIX real para homologação externa.

**Próxima tarefa F4**
- snapshot/reserva de estoque pela ficha técnica autoritativa no checkout, sem antecipar o cutover comercial completo do PDV/Estoque da Fase 6.

## 10.6 Checkpoint Fase 4 / F4-B — ficha técnica + snapshot + reserva de estoque autoritativa — 31/08/2026

**SHA técnico validado:** `fbfd89a223887d68f4775a1c6cb6774d6e3ba347`

**Current → Target**
- Current antes deste bloco: o Assistente construía Pedido/Pagamento pelo checkout canônico, porém enviava `snapshot_estoque=None`; a ficha e o saldo físico continuavam no modelo legado durante o cutover.
- Target aplicado ao caminho do Assistente: a ficha técnica **existente** permanece a única fonte funcional da receita durante o cutover; sua leitura é tenant/unidade scoped, um snapshot imutável e versionado é capturado e a reserva ocorre exclusivamente no ledger canônico de Estoque dentro da mesma Unit of Work do checkout.
- O cutover completo das telas/comandos de Cardápio/Ficha, PDV e Estoque **não** foi antecipado; esses módulos continuam com seus status próprios até as fases previstas no Mestre.

**Implementado**
- criado `application/catalogo_estoque_cutover.py` como ponte governada, sem criar segunda ficha técnica ou segundo saldo;
- cada produto do Pedido é resolvido contra a ficha histórica pelo vínculo explícito tenant/unidade → loja legado;
- produto, ficha e insumo fora do escopo falham fechados;
- `quantidade_utilizada` da ficha existente é convertida para `ItemSnapshotFicha` com quantidade unitária e total por item do Pedido;
- a versão da ficha é um SHA-256 determinístico do conjunto ordenado de definições da receita, permitindo detectar alteração da ficha em replay;
- o insumo legado é ancorado uma única vez no ledger canônico com referência `legacy:insumo:<id>`;
- bootstrap de saldo, captura do snapshot, criação de Pedido/Pagamento e reserva de estoque ocorrem na **mesma UoW**;
- se o ledger já tiver sido inicializado, qualquer divergência entre saldo físico canônico e saldo legado bloqueia o checkout, sem sincronização silenciosa;
- ausência de unidade de medida, saldo inválido, quantidade de ficha inválida, cross-tenant/cross-unit ou saldo insuficiente falham fechados;
- saldo insuficiente reverte bootstrap, Pedido, Pagamento e Reserva na mesma transação;
- o Assistente não faz baixa direta no estoque legado; usa `reservar_estoque` do checkout canônico;
- o resultado do Assistente agora expõe se houve reserva de estoque e incorpora a evidência na auditoria operacional;
- replay idempotente não duplica bootstrap, Pedido, Pagamento nem Reserva;
- mudança de ficha em replay com a mesma idempotency key produz conflito e preserva o snapshot originalmente registrado.

**Provas**
- Commercial Runtime Readiness V1 — run 107: **PASS**;
- Assistente Fase 4 Gate V1 — run 92: **PASS**;
- compile do recorte F4: **PASS**;
- Ruff do recorte F4: **PASS**;
- suíte direcionada ampliada: **67 passed**;
- testes cobrem adapter comercial real do Assistente, snapshot/versionamento, tenant/unidade, bootstrap controlado, reserva, replay idempotente, alteração de ficha, divergência legado↔ledger e rollback por saldo insuficiente;
- fitness guard prova que o caminho comercial do Assistente usa a ponte de ficha → checkout canônico e não chama baixa de estoque legado.

**Readiness**
- `assistente_atendimento` continua `CUTOVER_PENDING`;
- blockers de código conhecidos no Assistente neste checkpoint: **0**;
- blocker externo de PIX real permanece `pix_provider_homologation_incomplete`;
- `commercial_runtime_e2e`: ainda não executado no SHA candidato final;
- `physical_test`: ainda não executado no SHA candidato final;
- `cardapio_ficha_tecnica` e `estoque` não são promovidos por este checkpoint: a UI/comandos completos desses módulos continuam sob autoridade legada até seus cutovers previstos.

**Rollback**
- nenhuma migration nova foi necessária neste bloco; o ledger canônico já pertence ao schema comercial V1;
- antes de merge/deploy, rollback é simplesmente reverter os commits deste bloco na branch;
- após implantação futura, qualquer rollback deve preservar os registros canônicos já gravados e desativar somente o caminho de composição do Assistente; jamais apagar ledger, snapshots ou reservas para “voltar” ao legado.

**Próxima tarefa F4**
- iniciar o **F4-C — Customer Context / CRM do Assistente**: reconciliar histórico/endereço/consentimento/memória por finalidade, handoff com contexto suficiente e retomada segura, sempre reutilizando ClienteCRM + Contact Vault existentes e sem antecipar o cutover completo da UI de CRM da Fase 13.

## 10.7 Checkpoint Fase 4 / F4-C — Customer Context / CRM governado — 31/08/2026

**SHA técnico validado:** `baeae30daf3733ee5653bde6d7ad924d7a95d40f`

**Current → Target**
- Current antes deste bloco: o Assistente já identificava ClienteCRM por canal usando Contact Vault, porém não possuía uma projeção governada única para histórico real de pedidos, consentimentos vigentes, endereço validado reutilizável e contexto seguro de handoff.
- Target aplicado: Customer Context passa a ser uma **projeção minimizada de leitura**, finalidade `atendimento`, composta exclusivamente a partir das autoridades já existentes — ClienteCRM, Contact Vault, histórico canônico de Pedido, histórico append-only de consentimentos e vault cifrado de endereços autorizados.
- O bloco **não** cria um segundo CRM, não transforma memória livre em verdade operacional e não antecipa o cutover completo da UI de CRM/Cashback previsto para fase posterior.

**Implementado**
- criado `ContextoClienteAutorizado` como contrato minimizado do Assistente, contendo somente referência canônica do cliente, histórico operacional autorizado, consentimentos atuais derivados do histórico, referência opaca do último endereço e finalidade fixa `atendimento`;
- `ContextoAtendimento` passa a carregar opcionalmente essa projeção e rejeita contexto pertencente a outro cliente;
- `ContextoClienteAtendimentoSQLAlchemy` exige `CLIENTE_VISUALIZAR`, confirma o ClienteCRM no mesmo tenant/unidade e lê somente pedidos canônicos do próprio cliente em estados operacionais reais;
- pedidos `rascunho`, `aguardando_confirmacao` e `cancelado` não alimentam memória de repetição;
- consentimentos são lidos da autoridade append-only `crm_consentimentos_v1`; a projeção escolhe somente o registro vigente por canal/finalidade e não promove `crm_consentimentos_atuais_v1` a autoridade;
- criada migration aditiva `0034_crm_customer_context_v1` para `crm_enderecos_seguros_v1`, com FK composta para ClienteCRM, escopo tenant/unidade/cliente/finalidade e unicidade por HMAC;
- endereço validado por Google Maps passa a ser armazenado cifrado com Fernet; no domínio e no contexto circula apenas referência `address://...`;
- o valor de endereço é HMAC-scoped por tenant/unidade/cliente/finalidade e não aparece em texto puro na tabela do vault;
- reutilização de endereço antigo exige ação explícita na UI, resolve a referência somente no mesmo tenant/unidade/cliente e passa novamente por Google Maps + área + taxa + ETA; endereço salvo nunca é aceito como cotação atual por confiança histórica;
- a expressão `o de sempre` e variantes usa o último Pedido canônico real, mas resolve cada produto pelo ID histórico contra o **catálogo atual**; nome/preço/disponibilidade atuais continuam sendo revalidados e modalidade/endereço/pagamento precisam ser novamente confirmados;
- produto histórico indisponível não é substituído ou inventado: o serviço determinístico falha fechado e faz handoff;
- a leitura de Customer Context no runtime comercial passa a gerar auditoria minimizada com finalidade, quantidade de históricos/consentimentos, existência de endereço salvo e último pedido, sem telefone/endereço bruto;
- handoff humano passou a carregar somente metadata allowlisted: referência canônica do cliente, tipo, contagens, último pedido, modalidade e quantidade de itens resolvidos/pendentes;
- o adapter de handoff remove campos fora da allowlist, reutiliza a trilha append-only de auditoria e permite recuperar o último contexto pela conversa **somente** no mesmo tenant/unidade;
- não foram introduzidos Fake/Mock/runtime_teste no caminho comercial do Assistente.

**Provas**
- Commercial Runtime Readiness V1 — run 136: **PASS**;
- Assistente Fase 4 Gate V1 — run 121: **PASS**;
- compile do recorte F4-C: **PASS**;
- Ruff do recorte F4-C: **PASS**;
- suíte direcionada ampliada: **73 passed**;
- migration manifest da 0034 validado pelo mesmo mecanismo de fingerprint imutável das migrations comerciais;
- testes cobrem: migration/vault, criptografia em repouso, isolamento tenant/unidade/cliente, último consentimento append-only, histórico canônico, `o de sempre`, catálogo atual, endereço salvo, escopo de resolução e handoff persistido PII-minimized.

**Privacidade e governança**
- Contact Vault continua sendo a autoridade de telefone/e-mail; o novo Address Vault é separado por responsabilidade de domínio e usa a mesma disciplina criptográfica, sem misturar contatos com endereços;
- Customer Context não entrega telefone bruto, endereço bruto ou prova de consentimento para o modelo de IA;
- consentimento de marketing não é inferido a partir de atendimento, compra, endereço ou histórico;
- memória do Assistente neste checkpoint é derivada de fatos operacionais autoritativos e finalidade explícita; não existe memória livre/promocional silenciosa;
- cross-tenant, cross-unit e cross-client falham fechados.

**Readiness**
- `assistente_atendimento` continua `CUTOVER_PENDING`;
- blockers de código conhecidos neste checkpoint: **0**;
- blockers externos/de implantação: `pix_provider_homologation_incomplete` e aplicação física da migration `0034_crm_customer_context_v1` no banco de homologação;
- `commercial_runtime_e2e`: ainda não executado no SHA candidato final;
- `physical_test`: ainda não executado no SHA candidato final;
- `crm_cashback` não é promovido por este checkpoint; seu cutover de UI/operação permanece na fase própria.

**Rollback**
- antes de merge/deploy, rollback é reverter os commits F4-C na branch;
- depois de uma implantação futura, registros de `crm_enderecos_seguros_v1`, auditoria e referências `address://` já emitidas devem ser preservados; rollback deve desativar a composição do Customer Context, não apagar histórico/PII cifrada;
- nenhuma migration histórica anterior foi alterada; a 0034 foi anexada após a 0033 e o teste antigo da 0033 foi corrigido para ser append-safe.

**Próxima tarefa F4**
- iniciar o **F4-D — Order Result Orchestrator**: extrair/usar uma orquestração pós-resultado independente do canal para Pedido → resultado financeiro real → confirmação → efeitos autorizados, preservando estoque/KDS/entrega/financeiro e evitando que o Assistente replique lógica do PDV.

## 10.8 Checkpoint Fase 4 / F4-D — Order Result Orchestrator independente do canal — 31/08/2026

**SHA técnico validado:** `1f3277d699e8f000e9d1922d519d7745b8b49560`

**Current → Target**
- Current antes deste bloco: a finalização após pagamento confiável existia, porém sua semântica principal permanecia concentrada no fluxo do PDV, incluindo confirmação do Pedido, reconhecimento financeiro, consumo de estoque e projeções legadas.
- Target aplicado: a regra geral passa a ser **independente do canal** e executa somente sobre autoridades canônicas: Pagamento real → Pedido canônico → confirmação autorizada → VendaFinanceira. PDV/legado tornam-se compatibilidade posterior e não pré-requisito.
- O consumo de reserva foi retirado do simples marco de liquidação financeira e associado ao **início real da produção no KDS**, em conformidade com o Documento Mestre.

**Implementado**
- criado `application/order_result_orchestrator.py` como orquestrador canônico de resultado, sem dependência de `core.pdv`, `app.py`, Streamlit ou projeção legada;
- Pagamento diferente de `PAGO` não confirma Pedido, não cria VendaFinanceira e não consome reserva;
- Pagamento `PAGO` só opera quando existe Pedido canônico compatível no mesmo tenant/unidade; ausência ou divergência falham fechadas;
- Pedido em `aguardando_confirmacao` é promovido para `confirmado` pela máquina normativa existente, com idempotência e auditoria/outbox;
- estados posteriores já válidos são aceitos em replay sem regredir Pedido;
- reconhecimento de VendaFinanceira usa `avaliar_criterio_financeiro` + `reconhecer_venda` existentes; não foi criado segundo domínio financeiro;
- replay do mesmo resultado não duplica Pedido, transição, critério ou VendaFinanceira;
- o snapshot de resultado observa reserva e produção sem transformar KDS em pré-requisito da liquidação; quando a tabela de produção ainda não existe em um runtime parcial, a observação retorna vazia sem abrir nova conexão nem reverter a UoW financeira;
- `application/finalizacao_pagamento.py` foi reduzido a compatibilidade do PDV: primeiro executa a regra genérica e somente depois materializa projeções/reconciliação legadas quando existir pendência própria do PDV;
- `application/pdv_legacy_projection.py` passou a permitir explicitamente postergar a projeção de estoque; pagamento não reduz mais estoque físico legado;
- o executor canônico do PDV síncrono também passou a usar o mesmo Order Result Orchestrator, removendo a duplicação da sequência Pedido/Pagamento/VendaFinanceira;
- reconciliação PDV reconhece `canonico_reservado_aguardando_producao` como estado válido e não exige baixa de estoque no pagamento;
- criado `application/legacy_stock_projection.py` somente como compatibilidade transitória: ele replica para `insumos` legados um **consumo canônico já ocorrido**, nunca decide consumo e nunca se torna autoridade;
- `ServicoKDSCanonico` consome a reserva quando a produção entra efetivamente em `em_preparo`; se a reserva já foi consumida, o replay é idempotente; se foi liberada, falha fechado;
- a baixa canônica e a projeção transitória do saldo legado acontecem na mesma transação do marco real de produção;
- o caminho de produção que chega a pronto sem etapa explícita de início primeiro promove o Pedido para `em_preparo` e aplica o mesmo marco de consumo;
- a reconciliação PagBank por consulta autenticada passou a exigir Pedido canônico real antes da finalização; um Pagamento isolado não é suficiente para produzir efeitos de negócio;
- nenhum Fake/Mock foi introduzido em runtime comercial. O adapter fake de PagBank permanece restrito aos testes de contrato e não é evidência de homologação real.

**Provas**
- Assistente Fase 4 Gate V1 — run 155: **PASS**;
- Commercial Runtime Readiness V1 — run 170: **PASS**;
- compile do recorte F4-D: **PASS**;
- Ruff do recorte F4-D: **PASS**;
- suíte ampliada com regressão completa do PDV: **104 passed**;
- a suíte cobre pagamento pendente, liquidação real, Pedido canônico, VendaFinanceira, replay idempotente, PagBank por consulta simulada, PDV síncrono/assíncrono, corrida concorrente, rollback, divergência de cutover, KDS e marco de consumo de reserva;
- fitness guard comprova que o Order Result Orchestrator não importa PDV/legado, não chama `consumir_reserva` e reutiliza serviços canônicos de Pedido e VendaFinanceira.

**Limite externo PagBank / PIX**
- a conta real do PagBank **ainda não foi criada pelo proprietário**;
- portanto nenhuma credencial real, cobrança real, webhook real ou consulta real ao PagBank foi homologada neste checkpoint;
- o código interno de reconciliação e o contrato de consulta autenticada foram testados sem fingir homologação externa;
- permanece o blocker `pix_provider_homologation_incomplete`; a ausência da conta real é tratada como pendência externa, não como justificativa para sandbox/fake no caminho comercial.

**Readiness**
- `assistente_atendimento` continua `CUTOVER_PENDING`;
- blockers de código conhecidos no recorte F4-D: **0**;
- blockers externos/de implantação preservados: `pix_provider_homologation_incomplete` e aplicação física da migration `0034_crm_customer_context_v1` no banco de homologação;
- `commercial_runtime_e2e`: ainda não executado no SHA candidato final;
- `physical_test`: ainda não executado no SHA candidato final;
- `pdv_pagamentos`, `estoque` e `kds` **não** são promovidos por este trabalho transversal: seus cutovers/gates próprios permanecem nas fases previstas.

**Rollback**
- nenhuma migration nova foi criada no F4-D;
- antes de merge/deploy, rollback é reverter os commits deste bloco;
- após implantação futura, rollback deve preservar Pedido, Pagamento, VendaFinanceira, reservas, movimentos e auditoria já persistidos;
- a compatibilidade legada pode ser desativada/revertida sem restaurar o PDV legado como pré-requisito da regra geral e sem apagar registros canônicos.

**Próxima tarefa F4**
- iniciar o **F4-E — Convergência mínima do Delivery**: fazer somente o caminho necessário ao Assistente convergir para Pedido/Checkout/Order Result canônicos, preservando capacidades específicas de Delivery e mantendo sua homologação completa para a Fase 11.

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
