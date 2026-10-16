# Kordena — investigação dos 70 comandos SQL por checkout PDV
**Data:** 2026-10-16  
**Status:** DIAGNÓSTICO COM MEDIÇÃO REAL EM POSTGRESQL 16 ISOLADO; NENHUMA CORREÇÃO DE DOMÍNIO NESTA PR  
**Base:** `staging/kordena-premium` após merge da PR #223 (`499ebb906a5885fd8dcc8f0dfb6c84ab5b6fee4b`)  
**Código de instrumentação:** `scripts/diagnose_pdv_checkout_sql_attribution_pg.py`  
**Evidência:** GitHub Actions [Kordena PDV SQL 70 Attribution Diagnostic](https://github.com/faabio3131/fm-ai-platform/actions/runs/38969204120); anexo JSON `kordena-pdv-sql-attribution-pg16` (retenção 14 dias).

## 1. Método e limitações
Teste HTTP real do `POST /v1/pdv/checkout` por `TestClient` com cookie de sessão após login, `commercial_access_gate` habilitado, cadastro `INTERNAL_TEST` e PostgreSQL 16 efêmero em localhost. O fluxo realmente grava pedido, obrigação e transação de pagamento **local**; não acessa gateway real, modelos pagos ou dados de clientes. SQLAlchemy `before_cursor_execute` identifica cada comando, tabela, fase de request e call stack; parâmetros e credenciais não entram no relatório. Uma venda de aquecimento, três vendas novas com idempotency keys distintas e um par primeira execução/replay com a mesma chave foram testados.

A captura de stacks aumenta a latência; tempos desse profiler **não podem ser comparados** com o benchmark não instrumentado da PR #223 ou com Railway. Este relatório mede **quantidade e origem dos comandos SQL**, não tempo em produção, p95 ou segurança de alterações futuras.

## 2. Resultados reproduzidos
- Warmup: 70 SQL.
- Vendas novas: **70, 70 e 70 SQL**, todas HTTP 201 e valores financeiros preservados.
- Replay com mesma chave: primeira execução **70 SQL, HTTP 201**; repetição **33 SQL, HTTP 200**, mesmo pedido, marcada idempotente.
- Fase de cada venda nova: middleware comercial **10 SQL**, auth/escopo da rota PDV **8**, catálogo solicitado **2**, checkout transacional **50**.
- Fase do replay: **10 + 8 + 2 + 13 = 33** comandos SQL.

### Atribuição por responsabilidade — venda nova
| Responsabilidade | SQL | Origem comprovada |
|---|---:|---|
| Autenticação: identidade e sessão | 10 | `http_api/auth.py`; `infra/seguranca/adaptador_sqlalchemy.py` |
| Autenticação: introspecção de schema | 4 | `_global_disponivel` → `pg_catalog.pg_class` |
| Autenticação: limpeza de sessões expiradas | 2 **DELETE** | `http_api/auth.py:_limpar_expiradas_db` |
| Gate: licença/entitlement comercial | 2 | `infra/comercial/{repositorio,entitlement}_sqlalchemy.py` |
| Catálogo: tenant/unidade → loja | 1 | `infra/legacy_product_scope.py:resolver_loja_id_legada` |
| Catálogo: produtos solicitados | 1 | `infra/legacy_product_scope.py:listar_produtos_legados` |
| Pedido/agregado/histórico | 24 | `core/pedidos/adaptador_sqlalchemy.py` |
| Obrigação/pagamento/transação | 6 | `core/pagamentos/adaptador_sqlalchemy.py` |
| Outbox de eventos | 8 | `infra/eventos/adaptador_sqlalchemy.py` |
| Auditoria imutável | 6 | `infra/seguranca/auditoria_sqlalchemy.py` |
| Projeção síncrona de eventos do Core cognitivo | 6 | `infra/gerente_ia/persistencia_sqlalchemy.py:ConsumidorEventosCoreSQLAlchemy.consumir` |
| **Total** | **70** | Reconciliado com contagem por fase |

### Evidência de redundância e pontos de cuidado
1. **Identidade duplicada por requisição.** `http_api/frontend_app.py:commercial_access_gate` resolve a identidade e `http_api/pdv.py:_contexto_pdv` executa a resolução novamente. Foram medidos **dois DELETEs de sessões expiradas**, **dois SELECTs de sessão** e buscas duplicadas de identidade/papéis/unidades. São **18 SQL** antes de entrar no catálogo ou checkout (incluindo os 2 SQL legítimos do entitlement). Os **quatro SELECTs** de `pg_catalog.pg_class` decorrem de duas verificações de schema por resolução.
2. **Reidratação recorrente do mesmo agregado Pedido.** A query normalizada para `pedidos_v1` ocorreu **seis vezes**; cada uma das três tabelas `itens_pedido_v1`, `adicionais_item_pedido_v1` e `observacoes_pedido_v1` foi lida **quatro vezes**. Apenas essas assinaturas repetidas totalizam **18 SELECTs**, dentro dos 24 SQL atribuídos à camada de pedidos. O código de `RepositorioPedidosSQLAlchemy.buscar/salvar/_para_dominio` usa relações ORM de modo a acionar leituras adicionais. Não há autorização para eliminar verificação de versão/idempotência simplesmente por ser repetida.
3. **Efeitos da transação canônica.** Há três eventos escritos na `event_outbox_v1` (acompanhados das verificações e de duas leituras de idempotência), três auditorias (SELECT + INSERT cada) e três projeções síncronas em `gerente_ia_eventos_v1` (SELECT + INSERT cada). `infra/transacoes/uow.py:RecursosTransacionaisV1` liga `RepositorioOutboxSQLAlchemy(..., ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir)`: os **6 SQL cognitivos acontecem dentro do checkout**, mesmo sem qualquer chamada de LLM. A projeção é parte do estado transacional atual, portanto movê-la a worker altera o contrato de consistência e exige projeto próprio.
4. **Pagamento mantém barreiras explícitas.** Os 6 SQL de obrigação/pagamento/transação estão ligados à autoridade financeira, versionamento e idempotência. Nenhuma simplificação sem prova concorrente de integridade financeira.
5. **Replay não duplica efeitos.** O replay usa 33 SQL e **não** reinsere auditorias/projeções/novos efeitos de pagamento; mesmos `pedido_id` e estado idempotente comprovados. Contudo, repete o custo pré-checkout de 20 SQL (18 acesso+2 catálogo).

## 3. Ordem recomendada de correção com gates separados
**K-08-A — limpeza fora do hot path (baixo/médio risco).** Migrar `_limpar_expiradas_db` para job periódico governado, com validade da sessão verificada na leitura e revogação/step-up/TTL intactos. Gate: **zero DELETE na venda**, expiração real, sessões revogadas, falha de banco, concorrência e observabilidade; não apagar sessões legítimas.

**K-08-B — identidade única por request + schema discovery (médio risco de segurança).** Reaproveitar a identidade autenticada **somente durante a requisição**, do middleware ao PDV, por estado seguro e tipado; RBAC do PDV continua na rota, sem aceitar headers que substituam o escopo. Eliminar `inspect(...).has_table` repetido no schema estável por mecanismo seguro e invalidável após migration. Gate: tenant/unidade/role, troca de unidade e membership, revogação entre requests, cookies inválidos, 401/403 corretos e medição da redução. **Não reutilizar identidade entre requests**.

**K-08-C — carregar/reutilizar agregado Pedido na UoW (médio/alto risco).** Investigar `RepositorioPedidosSQLAlchemy.buscar/salvar/_para_dominio`; refatorar leituras redundantes da mesma versão e relações (selectinload/joinedload seletivo quando comprovado; cuidado com explosão cartesiana). Gate: idempotência concorrente, isolamento multi-tenant, lock/versionamento, itens/adicionais/observações, evento e rollback. Não tentar eliminar as 18 queries sem antes diferenciar verificação autoritativa de reidratação redundante.

**K-08-D — efeitos Outbox/Auditoria/Projeção (alto risco, fase separada).** Não desligar eventos, auditoria nem projeção para atingir um número artificialmente baixo de SQL. Avaliar restrição única + `ON CONFLICT` governado para evitar leituras de inexistência onde seguro. Avaliar worker durável para projeção cognitiva **somente** com entrega at-least-once, deduplicação, recuperação de crash e read-your-writes formalizados; nenhuma gravação de negócio pode depender de sucesso de IA externa.

**K-08-E — pagamento (alto risco financeiro).** Otimizar apenas após demonstrar redundância na mesma transação e invariantes de cobrança/obrigação/versionamento preservados.

Após cada micro-PR, repetir o MESMO profiler e benchmark sem instrumentação, comparando `SQL/request`, p50/p95, erro/timeout e replay no PostgreSQL controlado. Apenas após matrix integral verde, promover para homologação e verificar o pós-merge. Exigir testes com vários itens e múltiplos tenants, além de ensaio concorrente; **70 é baseline de uma venda de um item, não uma constante universal**.

## 4. Critério de conclusão desta investigação
O diagnóstico será considerado completo quando este documento, o workflow e o JSON forem rastreáveis no GitHub e a execução do profiler estiver verde. **Não equivale a corrigir os 70 SQL**, nem a certificar latência de produção ou carga com múltiplos workers.
