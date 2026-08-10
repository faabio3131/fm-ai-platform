# KDS por setor — V1

Implementa a **PR10** do plano operacional. O KDS projeta e comanda a máquina normativa de `Produção`; não substitui `Pedido`, `Estoque`, `Pagamento` nem `Expedição`.

## Escopo

- cadastro aditivo de `SetorProducao` por tenant/unidade;
- roteamento idempotente de `PedidoItem` para `ProducaoItem` e setor;
- filas determinísticas por setor, prioridade e ordem de criação;
- transições `aguardando → aceita → em_preparo ↔ pausada → pronta → retirada`, além de cancelamento permitido pela máquina normativa;
- optimistic locking e evento append-only por comando;
- RBAC específico: cozinha aceita/atualiza; expedição registra retirada; configuração exige alçada de configuração;
- SLA por setor com limiar de atenção e política explícita de suspensão durante pausa;
- último snapshot de fila em cache para degradação **somente leitura** quando a persistência estiver indisponível;
- métricas in-memory mínimas para leitura, roteamento, transições e modo degradado;
- migration aditiva restrita a SQLite explicitamente efêmero/de teste nesta PR.

## Não escopo

- ativação em produção ou migration no banco real;
- impressão por setor (PR14);
- interface móvel do garçom (PR12);
- mesas/comandas (PR11);
- expedição/entrega completa (PR13);
- sincronização offline com escrita local. Offline na PR10 é deliberadamente **read-only** para impedir transições conflitantes ou dupla execução.

## Invariantes

1. `Pedido` permanece a fonte operacional; KDS referencia `pedido_id`/`pedido_item_id` e não cria pedido.
2. Um item/setor/tentativa é único no escopo tenant/unidade.
3. Roteamento e transições têm chaves de idempotência; reutilização com payload divergente retorna `conflito_idempotencia`.
4. Transições usam a máquina `producao` de `core.estados` e CAS por `versao` na persistência.
5. `pronta` não conclui Pedido nem Venda. `retirada` encerra o SLA do item de produção.
6. Pausa exige motivo. Início exige estoque resolvido e estação apta. Pronto exige quantidade/checklist. Retirada exige conferência e posse transferida.
7. Tenant/unidade são derivados de `ContextoExecucao`; IDs externos não ampliam o escopo.
8. Em falha de persistência, a fila pode mostrar o último snapshot conhecido, identificado como degradado e somente leitura; nenhum comando é confirmado offline.

## SLA

O relógio inicia no roteamento do item. Por padrão, tempo em pausa é descontado do SLA. O limiar de atenção padrão é 80% do SLA do setor. A política é injetável por `ConfiguracaoSLAKDS`; setores sem SLA retornam `sem_sla`.

## Persistência

Tabelas novas:

- `setores_producao_v1`;
- `producao_itens_v1`;
- `eventos_producao_v1`.

`migrations/kds_v1.py` recusa banco não-SQLite, `banco_erp_local.db` e arquivo SQLite sem marcador `test` no nome. Nenhuma migration real é executada automaticamente.

## Rollback

- manter `FM_AI_KDS_V1=0` remove a superfície executável desta PR;
- tabelas são aditivas e não substituem dados legados;
- em ambiente de teste autorizado, `downgrade(engine)` remove apenas as tabelas KDS V1;
- rollback funcional não reverte eventos ou estados de produção já confirmados: correções operacionais seguem a máquina normativa/compensação.

## Gates PR10

- unitários de SLA/contratos;
- integração multi-setor, idempotência, RBAC, concorrência e migration;
- E2E KDS com ao menos dois setores e ciclo de produção;
- E2E de degradação offline somente leitura;
- suíte Python completa, mypy/ruff e E2E padrão permanecem verdes;
- banco real permanece intocado;
- merge somente após aprovação humana.
