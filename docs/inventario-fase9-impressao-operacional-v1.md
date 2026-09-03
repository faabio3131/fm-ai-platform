# INVENTÁRIO FASE 9 — IMPRESSÃO OPERACIONAL — CUTOVER COMERCIAL V1

**Projeto:** Kordena / GERENTE AI V1.0  
**Autoridade:** Documento Mestre + RECOVERY Issue #62  
**Issue da fase:** #75  
**Branch:** `recovery/v1-fase9-impressao-operacional-cutover`  
**Base auditada:** `main` @ `591c08bace3467b0cedbc827b12396fc8d49bcae`  
**Status:** F9-A CONCLUÍDA — Current → Target antes de código

## 1. Objetivo

Promover o patrimônio já existente de impressão por setor para o runtime comercial
sem reescrever o domínio/spool que já funciona.

Impressão continua sendo um efeito operacional auxiliar. KDS permanece a fonte
autoritativa da Produção e falha de impressora nunca pode bloquear ou alterar
Pedido, Produção, Estoque, Pagamento ou Entrega.

## 2. Current — patrimônio preservado

Já existe em `core/impressao`:
- `JobImpressao`, `DestinoImpressao` e estados pendente/falhou/impresso/contingência;
- renderer de ticket minimizado, sem PII financeira;
- deduplicação/idempotência por tenant/unidade/setor/chave/template;
- retry limitado e contingência;
- CAS/optimistic locking por versão;
- reimpressão idempotente com motivo e auditoria;
- `RepositorioSpoolSQLAlchemy`, sem `commit()` escondido;
- porta `PortaImpressora`;
- `ImpressoraFake` restrita ao universo de testes;
- feature readiness exigindo adapters `orders` e `print`.

Também já existe:
- RBAC `impressao.reimprimir`;
- migration comercial oficial `0012_restaurant_operations_runtime_v1`, que cria
  `ImpressaoBase`;
- migration histórica `migrations/impressao_v1.py` test-only, que não deve ser
  usada como migration comercial;
- testes unitários/integrados de dedup, CAS, falha/contingência, isolamento e auditoria;
- workflow histórico `PR14 Impressao Gates`.

## 3. Current — gaps objetivos

### B9-01 — Composition/Application comercial ausente
Não existe `application/impressao_transacoes.py` nem composition root comercial
que abra UoW, componha repositório/auditoria/adapter e assuma ownership explícito
de commit/rollback.

### B9-02 — KDS → spool não composto no runtime
O serviço aceita um `ProducaoItem`, mas hoje não há consumidor/application
integrado ao evento/resultado canônico de roteamento KDS para criar o job
automaticamente.

### B9-03 — Adapter físico/comercial ausente
A única implementação concreta de `PortaImpressora` é `ImpressoraFake`.
Nenhum arquivo comercial pode instanciá-la ou depender dela.

### B9-04 — Destinos não possuem configuração comercial durável
`DestinoImpressao` é atualmente fornecido por tupla ao construtor do serviço.
Não existe fonte comercial governada por tenant/unidade/setor para resolver
`impressora_id`, ativação e `max_tentativas`.

### B9-05 — Superfície comercial ausente
`app.py` não referencia impressão. Não há visão operacional de spool,
contingência ou reimpressão no runtime comercial.

### B9-06 — Evidência comercial/física ausente
Os testes históricos provam domínio e persistência isolada, mas não provam:
PostgreSQL + migration oficial + identidade real + KDS real + spool comercial +
adapter real/contingência + navegador e impressora física no mesmo SHA.

## 4. Target

Ao final da Fase 9:
1. KDS gera, por integração canônica e idempotente, intenção/job de impressão;
2. Application/UoW é proprietária da transação do spool;
3. falha de impressão permanece separada da transação/estado KDS;
4. destinos são resolvidos por tenant/unidade/setor a partir de configuração
   comercial governada;
5. provider real implementa `PortaImpressora` sem expor segredos/PII;
6. ausência de provider/configuração falha de forma explícita e segura;
7. UI comercial permite observar spool/contingência e reimprimir apenas com RBAC;
8. `ImpressoraFake`, runtime/test helpers e migrations test-only ficam fora do
   caminho comercial;
9. nenhuma migration nova é criada sem drift objetivo;
10. Commercial Runtime E2E e prova física fecham a fase.

## 5. Current → Target

| Área | Current | Target |
|---|---|---|
| Domínio/spool | Canônico | Preservado |
| Persistência | SQLAlchemy existente | Reutilizada via UoW |
| Migration | `0012` já oficial | Reutilizar; sem nova migration por padrão |
| KDS | Sem ligação comercial com spool | Evento/integração idempotente |
| Commit | Repository não commita, mas sem Application dedicada | Application/UoW dona do commit |
| Destinos | Tupla em memória | Configuração comercial tenant/unidade/setor |
| Driver | `ImpressoraFake` | Adapter comercial real + fail-closed |
| UI | Ausente | Spool/contingência/reimpressão governados |
| Evidência | Testes isolados | PostgreSQL + app real + browser + hardware |

## 6. Sequência de execução

### F9-B — Commercial Boundary / Composition
- criar Application/UoW de impressão;
- composição comercial;
- fitness proibindo `ImpressoraFake`/test-runtime em caminhos comerciais;
- provar migration oficial e ownership transacional.

### F9-C — KDS → Spool
- integrar criação de job a partir da cadeia canônica de KDS;
- idempotência/replay;
- provar que falha do spool não altera KDS;
- outbox/auditoria quando aplicável.

### F9-D — Adapter e configuração operacional
- definir/resolver configuração real por tenant/unidade/setor;
- implementar adapter comercial aprovado;
- timeout/erro normalizado/retry/contingência;
- UI de observabilidade/reimpressão com RBAC.

### F9-E — Commercial Runtime E2E / físico
- PostgreSQL 16;
- migrations oficiais;
- `app.py` real sem `FM_AI_TEST_MODE`;
- login/identidade real;
- Pedido → KDS → spool;
- sucesso e contingência;
- reimpressão autorizada;
- prova física/manual com impressora real quando disponível.

## 7. Readiness inicial

`impressao_operacional = CUTOVER_PENDING`

Code blockers:
- `print_commercial_composition_missing`;
- `kds_to_print_spool_not_composed`;
- `print_real_adapter_not_composed`;
- `print_destinations_not_commercially_configured`;
- `print_surface_not_exposed_in_app`.

External blocker:
- `physical_printer_hardware_gate_pending`.

## 8. STOP

F9-A não autoriza merge nem deploy. Cada bloco deve passar seus gates,
reconciliar inventário/readiness e registrar evidência antes do bloco seguinte.
