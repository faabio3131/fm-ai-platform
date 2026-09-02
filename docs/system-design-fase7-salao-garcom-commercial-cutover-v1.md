# System Design — Fase 7 — Salão / Garçom — Commercial Cutover V1

**Status:** APROVADO PARA IMPLEMENTAÇÃO CONTROLADA  
**Issue:** #71  
**Base:** `main@0feb5594655f30e0c26fc72754bdaa03c3e88ddd`

## 1. Contexto e objetivo

Salão e Garçom possuem domínio, repositórios, UoWs, RBAC e E2Es históricos,
porém suas UIs ainda atravessam helpers de teste. A Fase 7 é um cutover de
composition root, não uma reimplementação funcional.

Objetivo: permitir a jornada real de mesa/comanda/produção/fechamento no
Kordena comercial usando as autoridades já aprovadas.

## 2. Componentes e fronteiras

### Salão
- `core.salao`: autoridade de Mesa/Comanda e projeção do pagamento confirmado;
- `application.salao_transacoes.AplicacaoSalaoV1`: boundary de escrita/UoW;
- `RepositorioSalaoSQLAlchemy`: persistência, sem ownership de commit;
- `core.salao.ui_streamlit`: apenas apresentação e composition.

### Garçom
- `core.garcom.ServicoGarcom`: alçada e leitura operacional;
- `application.garcom_transacoes.AplicacaoGarcomV1`: writes/UoW;
- KDS: fonte dos avisos de pronto;
- UI Garçom: apresentação mobile/tablet, sem autoridade financeira.

### Autoridades externas ao Salão
- Pedido: `core.pedidos`;
- Pagamento/VendaFinanceira: `core.pagamentos`;
- Produção: `core.kds`;
- Identidade/RBAC: `core.seguranca`;
- schema: migration runner oficial.

## 3. Fonte autoritativa

| Dado/efeito | Autoridade |
|---|---|
| usuário/tenant/unidade | IdentidadeUsuario / Active Execution Scope |
| mesa/comanda | Salão |
| pedido/itens/total | Pedido |
| produção/setor/estado | KDS |
| obrigação/pagamento/confirmação | Pagamentos |
| venda reconhecida | VendaFinanceira |
| permissões | matriz RBAC |
| schema | migration runner |

A UI nunca cria uma segunda verdade.

## 4. Contratos e composition root

### Contexto comercial
Seguir o padrão já adotado pela Central de Pedidos:
1. ler `_fm_ai_authenticated_identity_v1` do session state;
2. exigir `IdentidadeUsuario` ativa;
3. derivar `ContextoExecucao` com correlation id novo;
4. nunca aceitar papel, tenant, unidade ou usuário provenientes de widget/query.

Renderers podem aceitar `contexto: ContextoExecucao | None` apenas para E2E.
Se `contexto is not None` e `FM_AI_TEST_MODE != 1`, falhar fechado.

### Schema
Commercial path não executa `create_all` nem `preparar_schema_teste`.
O app comercial já executa/asserta migrations pelo runner. Injeção E2E isolada
pode preparar schema de teste somente sob TEST_MODE.

## 5. Fluxo Salão

1. identidade autenticada cria contexto;
2. listar mapa no escopo tenant/unidade;
3. operador autorizado abre comanda;
4. Pedido canônico é criado pelo fluxo de Pedido/PDV apropriado;
5. Salão vincula o `pedido_id`, sem copiar Pedido;
6. Pedido alimenta KDS conforme regras existentes;
7. Garçom recebe alerta derivado do KDS quando pronto;
8. conta é solicitada;
9. perfil com alçada financeira cria/confirma Pagamento canônico;
10. Salão valida o PagamentoORM `PAGO`, `comanda_id`, método, valor e saldo;
11. Salão projeta o pagamento de forma idempotente;
12. saldo zero permite fechamento;
13. comanda fecha e mesa é liberada.

## 6. Fluxo Garçom

1. login real;
2. contexto derivado da identidade;
3. `ServicoGarcom.listar_painel` filtra próprias comandas para GARCOM;
4. Garçom pode abrir mesa/comanda e alterar consumo dentro da alçada;
5. pode solicitar conta;
6. não confirma pagamento e não fecha financeiramente;
7. gerente/admin mantêm capacidades elevadas já existentes.

## 7. Pagamento e fechamento

A Fase 7 não cria payment facade paralela.

Usar as funções determinísticas existentes em `core.pagamentos.servicos`:
- `criar_obrigacao_pagamento(..., comanda_id=...)`;
- `confirmar_pagamento` para dinheiro conforme regra existente;
- `confirmar_pagamento_presencial` para crédito/débito com referência auditável;
- webhook/provider para Pix.

`ServicoSalao.registrar_pagamento_confirmado` permanece a projeção final e já
valida o registro financeiro autoritativo.

A implementação deve manter um único UoW proprietário por comando e não
introduzir `commit()` em repository/service.

## 8. Persistência e migrations

Nenhuma migration nova prevista.

`0012_restaurant_operations_runtime_v1` é a migration oficial e já contém
`SalaoBase.metadata.create_all(..., checkfirst=True)`.

`migrations/salao_v1.py` continua test-only; não será importada pelo runtime
comercial.

Se os testes fresh/upgrade revelarem drift, o trabalho para e uma migration
forward posterior a 0037 deverá ser desenhada antes de qualquer alteração.

## 9. Tenant/unidade e RBAC

- tenant/unidade vêm apenas da identidade ativa;
- repositórios filtram ambos;
- Pedido/Pagamento ligado a outra unidade/tenant é recusado;
- GARCOM conserva sua matriz atual;
- GARCOM não recebe `PAGAMENTO_CONFIRMAR` ou `COMANDA_FECHAR`;
- transferência continua restrita a alçadas existentes.

## 10. Concorrência e idempotência

Preservar:
- CAS de Mesa/Comanda;
- unicidade pedido→comanda;
- idempotency keys de eventos Salão;
- idempotência de Pagamentos;
- pagamento projetado uma única vez;
- retries não podem duplicar Pedido, Pagamento, VendaFinanceira nem efeitos.

Evidência obrigatória:
- replay serial;
- duas sessões concorrentes em mutação relevante;
- fechamento repetido retorna estado idempotente ou conflito estável, nunca
  duplicação financeira.

## 11. Falhas, retry e fail-closed

- identidade ausente/inativa: negar tela/ação;
- contexto E2E fora de TEST_MODE: erro;
- schema não current: startup/gate falha;
- pagamento inexistente/não pago: `pagamento_nao_confirmado`;
- pagamento de outra comanda: bloquear;
- método/valor divergente: bloquear;
- KDS indisponível no painel Garçom: leitura degrada com aviso, sem inventar
  estado pronto;
- erro financeiro nunca é transformado em fechamento bem-sucedido.

## 12. Observabilidade e auditoria

Preservar correlation/idempotency do contexto.
Registrar eventos já existentes de Salão e Pagamentos.
Adicionar apenas logs seguros necessários ao composition root; não logar
credenciais, payload de cartão, Pix secreto ou PII desnecessária.

## 13. Desempenho

Não introduzir fila, cache ou tabela nova.
Reutilizar queries existentes e refresh do Garçom.
Evitar N+1 novo; qualquer problema mensurável deve ser tratado no boundary
existente, não com materialização paralela.

## 14. Compatibilidade Current -> Target

Current:
- domínio correto;
- UI Salão/Garçom test-only;
- migration oficial já existe;
- Salão comercial pode ser exposto por flag apesar do harness;
- Garçom não tem superfície comercial.

Target:
- domínio invariável;
- UI commercial-first;
- test harness isolado por injeção explícita;
- Salão e Garçom consumindo identidade real;
- pagamento exclusivamente canônico;
- Garçom exposto de forma governada.

## 15. Rollback

Antes do merge: reverter commits da branch.

Após integração futura:
- desabilitar `FM_AI_SALAO_V1` e `FM_AI_GARCOM_V1` server-side;
- preservar dados de Salão/Pedido/Pagamento;
- não executar downgrade de `0012`;
- rollback de UI/composition não apaga mesas, comandas, pagamentos ou eventos.

## 16. Estratégia de testes

F7-B:
- fitness: nenhum test context/schema no commercial default;
- auth fail-closed;
- contexto injetado só em TEST_MODE;
- schema current sem create_all comercial.

F7-C:
- Pagamento canônico dinheiro/cartão;
- Pix fail-closed/provider conforme disponibilidade;
- projeção Salão;
- fechamento;
- retry/concorrência.

F7-D:
- GARCOM mobile 390x844;
- tablet;
- comanda própria vs outro garçom;
- prova negativa de pagamento/fechamento.

F7-E:
- Pedido → KDS/setor → pronto → aviso Garçom → conta.

F7-F:
- PostgreSQL comercial;
- `app.py` real;
- login real;
- desktop + celular/tablet;
- regressões PR10/11/12 e F6;
- matriz transversal do mesmo SHA.

## 17. STOP / critérios de promoção

F7 não fecha se:
- existir `contexto_*_teste`, `preparar_schema_teste` ou criação de pagamento
  fake no caminho comercial default;
- Garçom puder escolher papel/usuario por UI;
- Garçom ganhar alçada financeira;
- commercial E2E não usar app/entrypoint real;
- schema PostgreSQL não estiver current;
- qualquer gate crítico estiver vermelho.
