# FASE 11 — INVENTÁRIO CURRENT → TARGET — DELIVERY PRÓPRIO V1

**Autoridade:** Documento Mestre + Issue #62 (RECOVERY) + Issue #84  
**Base auditada:** `main` @ `9079a2e2e3b60a5f16de19e6849f6af6ef0c057e`  
**Regra:** preservar domínio correto; implementar somente o cutover comercial necessário. Não criar novo Pedido, Pagamento, CRM ou Entrega paralelo.

## 1. Current — patrimônio reutilizável

O domínio do canal próprio já existe e deve ser preservado:

- `core/delivery/servicos.py` — regras determinísticas de carrinho, endereço, área/taxa/SLA, benefícios, confirmação, tracking, cancelamento e repetição;
- `core/delivery/modelos.py` e `core/delivery/adapters.py` — modelos e portas do Delivery Próprio;
- `core/delivery/modelos_orm.py` + `infra/delivery/politica_sqlalchemy.py` — política canônica de origem/área por tenant e unidade;
- `application/checkout.py` — fronteira canônica já definida para criação de Pedido/Pagamento/Reserva;
- `application/assistente_delivery_convergence.py` — precedente arquitetural: Pedido/Checkout + Entrega canônica no mesmo `pedido_id` e UoW;
- `core/entrega/*` + `application/entrega_transacoes.py` — agregado logístico canônico já promovido na Fase 10;
- infraestrutura canônica já existente para autenticação/RBAC, Pedido, Pagamento, Estoque, CRM/endereços, Maps e eventos.

## 2. Current — o que impede o cutover

`docs/commercial_runtime_readiness_v1.json` classifica `delivery_proprio` como `TEST_RUNTIME` com dois blockers de código:

1. `delivery_runtime_teste`;
2. `delivery_demo_scope`.

A causa concreta está no caminho de UI atual:

- `core/delivery/ui_streamlit.py` importa diretamente `RuntimeDeliveryTeste`;
- `_runtime()` instancia o runtime in-memory e o guarda em `st.session_state`;
- `_carrinho_atual()` cria e consulta carrinho com `tenant-demo`, `unidade-demo`, `cliente-demo`;
- operações de catálogo, endereço, cupom, cashback, confirmação, tracking, cancelamento e repetição continuam delegadas aos adapters de memória do `runtime_teste.py`;
- `tests/e2e-delivery/app_delivery.py` é mini-app isolado e não constitui Commercial Runtime E2E do `app.py`.

Portanto, o domínio é reutilizável, mas o composition root/UI ainda não é comercial.

## 3. Decisões anti-retrabalho

### D11-01 — Não reescrever `ServicoDelivery`

As regras determinísticas do domínio serão preservadas. Mudanças só são aceitas quando necessárias para receber/adaptar autoridades canônicas, sem criar um segundo domínio econômico.

### D11-02 — Pedido/Pagamento/Entrega canônicos são autoridade

O caminho comercial não poderá persistir `PedidoDelivery`, `PagamentoDeliveryRef` ou uma entrega in-memory como autoridade final. A confirmação do canal deve convergir para:

- Pedido/Checkout V1;
- Pagamento/VendaFinanceira V1;
- Reserva/Estoque V1;
- `core.entrega` para logística.

Objetos históricos do `core.delivery` podem continuar como modelo de jornada/compatibilidade interna, mas não como nova fonte autoritativa comercial.

### D11-03 — Identidade e escopo reais

Tenant, unidade e cliente serão resolvidos pelo contexto autenticado/canônico. É proibido introduzir IDs demo, query params livres ou contexto test-only no caminho comercial.

### D11-04 — UoW pertence à Application

Validação, reserva/checkout e criação logística que precisem atomicidade devem compartilhar a UoW apropriada. Repositórios/adapters não podem esconder `commit()`.

### D11-05 — Sem migration por conveniência

A Fase 11 só criará migration se a inspeção provar drift estrutural real. Schemas já oficiais devem ser reutilizados.

## 4. Target comercial

Ao final da Fase 11, o canal Delivery Próprio deve operar no `app.py` real com:

1. autenticação real;
2. tenant/unidade derivados da identidade/tenant ativo;
3. cliente/endereço canônicos;
4. catálogo/ficha/estoque autoritativos;
5. política de entrega persistente por tenant/unidade e integração Maps quando configurada;
6. carrinho persistente e isolado por escopo;
7. cupom/cashback delegados à autoridade canônica aplicável, sem saldo paralelo;
8. checkout único gerando Pedido/Pagamento/Reserva canônicos;
9. Entrega canônica no mesmo `pedido_id`;
10. tracking lido da autoridade logística real;
11. cancelamento/repetição seguros e idempotentes;
12. Commercial Runtime E2E em PostgreSQL, migrations oficiais, `FM_AI_TEST_MODE` ausente e evidência durável pós-browser.

## 5. Sequência de execução

### F11-A — Inventário e fronteira arquitetural

Este documento. Define Current → Target, blockers e autoridades. Nenhum status de homologação é antecipado.

### F11-B — Composition root e persistência comercial do canal

Criar a composição Application/SQLAlchemy necessária para carrinho/estado de jornada, isolada por tenant/unidade/cliente e sem dependência de `runtime_teste`.

**Gate:** integração SQL + concorrência/idempotência + fitness anti-demo/anti-runtime-teste.

### F11-C — Contexto comercial, catálogo, cliente/endereço e política de entrega

Conectar identidade autenticada, cliente/endereço CRM, catálogo/estoque e política/Maps canônicos.

**Gate:** escopo tenant/unidade, endereço autorizado e política real; nenhuma fonte demo.

### F11-D — Checkout/benefícios/entrega canônicos

Convergir a confirmação para Pedido/Pagamento/Reserva/Entrega já existentes. Não criar `commit()` escondido nem pagamento aprovado artificialmente.

**Gate:** integração transacional, replay idempotente e falhas compensadas/atômicas conforme autoridade existente.

### F11-E — UI comercial

Converter `core/delivery/ui_streamlit.py` para composition root real, mantendo qualquer runtime histórico somente sob fronteira explicitamente test-only. Ligar a superfície comercial ao `app.py` com autorização adequada.

**Gate:** RBAC/identidade/tenant real + nenhuma referência demo/test-runtime no caminho comercial.

### F11-F — Commercial Runtime E2E

Executar jornada real em PostgreSQL 16, migrations oficiais e `app.py`, com `FM_AI_TEST_MODE` ausente:

- autenticação;
- carrinho;
- endereço/taxa/SLA;
- benefício permitido;
- confirmação;
- Pedido/Pagamento/Reserva/Entrega persistidos;
- tracking/cancelamento ou conclusão conforme cenário;
- RBAC/isolamento negativo;
- evidência durável diretamente no PostgreSQL após o browser.

### F11-G — Reconciliação e fechamento

Atualizar readiness somente com evidência do mesmo SHA. Remover `delivery_runtime_teste` e `delivery_demo_scope` apenas quando o código comercial efetivamente não depender deles.

## 6. Definition of Done Fase 11

A Fase 11 não fecha se qualquer item abaixo permanecer verdadeiro:

- `RuntimeDeliveryTeste`, `core.delivery.runtime_teste` ou IDs demo participam da chamada comercial;
- Pedido/Pagamento/Entrega paralelos são fonte operacional final;
- UI escolhe tenant/unidade/cliente por entrada livre;
- há commit escondido em repositório/adapter;
- Commercial Runtime E2E usa mini-app em vez de `app.py`;
- `FM_AI_TEST_MODE=1` é necessário para a jornada;
- migrations/read models reais estão pendentes sem registro;
- readiness diverge do runtime observado.

## 7. Estado após F11-A

`delivery_proprio` permanece corretamente `TEST_RUNTIME` e os blockers `delivery_runtime_teste` e `delivery_demo_scope` permanecem ativos. F11-A apenas congela a fronteira correta e libera F11-B; não declara cutover nem homologação.
