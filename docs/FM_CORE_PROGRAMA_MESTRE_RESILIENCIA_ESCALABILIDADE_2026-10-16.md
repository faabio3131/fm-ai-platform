# Programa Mestre — FM Cognitive Core: Resiliência, Concorrência e Escalabilidade
**Data:** 2026-10-16
**Estado:** PROPOSTA TÉCNICA E ORDEM DE EXECUÇÃO APROVADA PELO PROPRIETÁRIO; IMPLEMENTAÇÃO/RELEASE AINDA NÃO CERTIFICADOS
**Repositório inicial:** `faabio3131/fm-ai-platform`; branch documental isolada `docs/fm-core-capacity-program-20261016`.
**Ordem executiva vinculante:** **1. Kordena → 2. FM Command → 3. Campaia → 4. Ironfit → 5. FM NFCore**. Um produto só é declarado concluído com evidências de testes, segurança, regressão, deploy/cutover autorizado e pós-merge quando aplicável. Os outros continuam no inventário, sem receber correções por suposição.

## 1. Princípio constitucional do Core
Fonte de engenharia: `00-DOCUMENTO-MESTRE-NOVA-FM-TECNOLOGIA.md`, §11, §12 e §27; `02-PADROES-DE-CONSTRUCAO-NOVA-FM.md`, §28–§31, §34, §44–§45 e §54; System Design comercial Kordena §39.
A arquitetura é **Core cognitivo compartilhado + capacidades específicas por vertical + serviços determinísticos autoritativos + interfaces/integrações**. Ser transversal não equivale a uma fila global ou um singleton serial. Compartilham-se contratos, políticas e competências; a **execução é concorrente, distribuível, isolada, multi-tenant e limitada por recurso**.

O Core classifica, planeja, contextualiza e orquestra; **não** substitui transações determinísticas, permissões, step-up, liquidação, estoque, fiscal ou autoridade do domínio. Uma queda de IA não pode tirar do ar PDV, registro de pedidos, KDS ou faturamento.

## 2. Distinção entre tipos de evidência
- **CONFIRMADO por medição independente já executada neste trabalho:** no Kordena, o endpoint autenticado `/v1/gerente-ia/perguntar`, com IA de 3 s simulada e PostgreSQL 16 real efêmero, esgota pool de 20 conexões com 25 chamadas in-flight e gera 503 por `sqlalchemy.exc.TimeoutError`. A vazão de ferramentas sem LLM é distinta. Execução: https://github.com/faabio3131/fm-ai-platform/actions/runs/38917093820. Evidências e limitações em `docs/KORDENA_CORE_AI_CAPACITY_DIAGNOSTIC_2026-10-16.md` na branch `bench/kordena-core-capacity-20261016`.
- **RELATADO nos relatórios de outro agente fornecidos pelo proprietário, ainda a confirmar/reconciliar no respectivo repositório:** medições de catálogo/venda/queda de banco/IA do Kordena e vulnerabilidades de fila/quotas/reprocessamento do Command. Não converter essas informações em certificação ou fatos comprovados em produção.
- **HIPÓTESES por herança tecnológica:** Campaia, Ironfit e NFCore podem conter falhas similares por compartilhamento de origem do Core, mas **nenhuma falha é confirmada apenas pela genealogia**. Comparar código, versões, deploy, configuração, esquema e testes produto por produto.

## 3. Contrato-alvo de execução transversal (System Design a especificar, prototipar e certificar)
```
Entrada (HTTP / eventos / jobs / conectores)
  → AuthN + AuthZ + tenant + unidade + contexto + correlação
  → Admission controller: limites atômicos por tenant / usuário / recurso,
     idempotência, deadline end-to-end, políticas e orçamento por operação
  → Classificador de missões (domínio, risco, latência, custo e prioridades)
  → Scheduler cognitivo: fairness, reserva de capacidade, backpressure
    ├── Lane A: operações determinísticas / PDV / pedidos / KDS (sem LLM obrigatório)
    ├── Lane B: conversas interativas e atendimento (baixa latência)
    ├── Lane C: gerente / consultas operacionais e planejamento
    └── Lane D: relatórios / ingestão / batch / sincronização
  → Workers independentes, escalonáveis horizontalmente e por tenant
  → Capability fabric / ferramentas / roteador multimodelo (OpenAI, Gemini, etc.)
  → Persistência transacional isolada + medição durável + auditoria
  → Resposta correlacionada; eventos longos via jobs/status/sinalização
```
Não transformar **toda** ação em job: trilhas transacionais de baixa latência continuam diretas e isoladas. Não centralizar o executor num único processo/global lock/fila. Evitar starvation; reservar recursos às classes críticas. Usar semáforos distribuídos, cotas governadas e fila durável somente quando seus contratos justificarem.

### Invariantes
1. Tenant/unidade/role não transitam livremente; autorização é revalidada no momento da execução e após espera/retry; step-up e revogações prevalecem.
2. Antes de chamar rede/IA longa, liberar recursos transacionais do negócio; após resposta, abrir nova UoW, revalidar autoridade e estado, aplicar optimistic concurrency e idempotência. Nunca liberar conexão no meio de transação incompleta.
3. Exatamente um **efeito de negócio** por chave de idempotência, mesmo sob retries, timeout após commit, crash e reentrega. Execução de IA é potencialmente `at-least-once`; a cobrança, lançamento e auditabilidade têm chaves de tentativa/correlação e reconciliação. Não prometer `exactly-once` universal.
4. Registro de uso/custo de IA governado pelo Command e segregado por produto, tenant, sessão/solicitação e tentativa, com trilha durável, deduplicação, conciliação e sem segredos nos logs.
5. Falhas de DB/serviços externos → 503/429 apropriados, JSON e correlation-id, timeouts explícitos, Retry-After quando justificável; não traduzir falha técnica em 403/400.
6. Health de vida do processo separado de readiness/capacidade/DB/IA; um pico não deve induzir reinicialização em cascata.
7. Segredos e provedores configuráveis centralmente, sem alterar código por tenant. Nunca executar testes pagos sem teto de custo e autorização para chamadas reais.
8. Observabilidade por classe/tenant/produto: fila mais antiga, tempo de espera, runtime de worker, throughput, p50/p95/p99, erros, ocupação pool, rate limit, tentativa/fallback, uso e custo, correlação.
9. Sem acoplamento fiscal prematuro: Kordena→NFCore cutover continua expressamente `DEFERRED_BY_DESIGN` no Cronograma Mestre comercial.

## 4. Ordem de correção em cada produto

### Frente 1 — KORDENA: prioritário, P0 de capacidade de IA
K-01: Baseline e contratos de regressão: medir throughput real de catálogo, pedidos, auth, IA/health; perfis com 1/5/10/25/50/100/250/500 in-flight, erro 5xx, tenant-isolation, ledger idempotente. Capturar hashes, máquinas, pool, runtime e dados de teste. `200 OK` só é aprovação quando latência/erros/efeitos confirmam critério.

K-02: **AI UoW**: separar preparação/autorização/read do modelo externo; remover conexão/transaction checkout durante espera; retomar com nova sessão, revalidar tenant/role/contexto/capability/estado; teste injetando perda de permissão, failover, cancelamento e corrida.

K-03: **Provider e metering**: execução não bloqueante ou isolada, timeout total, budgets, fallback limitado e circuit breaker; medição durável não pode esgotar pool de negócio. Preservar reconciliação de custo no Command.

K-04: **HTTP/auth/middleware/saúde**: tratar pool timeout e DB down com HTTP 503 JSON, correlação e logs; resolver identidade uma vez por request; remover DELETE de sessões expiradas do caminho quente para job governado; health live/readiness separados; verificar proteção de brute force.

K-05: **catálogo e vendas**: reduzir reflection em `infra/legacy_product_scope.py`, com cache de esquema/metadata seguro por engine/versão, invalidação após migrations, isolamento de conexão e teste de falha DB; comprovar melhora de contagem de SQL sem suprimir validação de escopo. Reduzir N+1 e novas consultas excessivas. Verificar controles anti-duplicidade inclusive retry com chave nova.

K-06: **isolamento de classes e scheduler**: operações PDV/KDS/pedidos independentes de IA; classificar atendimento/gerente/batch; limites por tenant e classe, quotas atômicas, fast-fail/backpressure, fairness e telemetria; só então escalar réplicas/workers.

K-07: **certificação e promoção governada**: baseline Python/lint/types/build/testes integração PostgreSQL, race, falha de banco, degradação/fallback, múltiplos tenants, soak e limites de custo. Primeira barreira operacional: 50 perguntas concorrentes com latência IA 3 s simulada e **0 erros** em teste comparável; ampliar para 100/250 conforme gates. Health deve sobreviver. Ensaios com provedor REAL separados e governados. Merge/pós-merge somente com evidência e rollback. Nenhuma carga agressiva na produção.

### Frente 2 — FM COMMAND: somente após gate inicial do Kordena
C-01: Limites de pessoa e empresa com contagem+enqueue atômicos; impedir ultrapassagem em paralelo.
C-02: Identidade por tarefa/tentativa, idempotência de efeitos/cobrança/auditoria e retries `at-least-once`.
C-03: Revalidar permissões no despacho e na execução (revogação).
C-04: Fila com TTL/reaper/retention, DLQ, limite por tenant, idade da mais antiga, alertas, admin operacional.
C-05: Planejador seletivo/hybrid retrieval de métricas; comparar precisão com catálogo integral, tokens/latência/custo.
C-06: Síntese E2E com dados sintéticos **governados**, mantendo `dados indisponíveis` em falta de dados reais.
C-07: Investigar travamento de 8 minutos na ponte multiprocesso e calibrar limite de 32 com Node **24**.
C-08: Medições reais com provider autorizado, teto de custo, confiabilidade do atalho Haiku, BD/auth em carga e limiter distribuído entre instâncias.
A ausência de IA real e de métricas governadas não pode ser ocultada como sucesso cognitivo. Não ligar o atalho rápido com confiança incorreta.

### Frente 3 — CAMPAIA; Frente 4 — IRONFIT; Frente 5 — FM NFCORE
Para **cada produto individualmente**, iniciar com inventário verificável do repositório, dependências, versão/reuso efetivo do Core, engine/provider, conexão DB, branch e ambiente. Construir matriz de aderência dos invariantes 1–9; exercitar os mesmos tipos de falha e cargas **adaptadas ao domínio**, sem declarar defeitos inexistentes ou alterar lógica fiscal/financeira:
- Campaia: campanhas, automações/eventos, envios, billing; deduplicação, rate limits e fila por tenant.
- Ironfit: matrículas, check-in, pagamentos/assinaturas, integrações, atendimento; isolamento e idempotência.
- FM NFCore: emissão/transmissão/consulta fiscal, jobs, autorização externa, certificado/segredos, reconciliação, reprocessamento; nenhuma homologação oficial sem prova externa; sem migração/cutover automático.
Adoção de componentes horizontais deve ser versionada, com Contract Pack, feature flags, homologação e rollback por produto, não via copiar alteração indiscriminadamente.

## 5. Gates objetivos
- **G0 inventário:** branch/HEAD/SHA, CI, ambiente, topologia, pools, schema, paths críticos, métricas de latência/erros/custo e limitações do benchmark;
- **G1 integridade:** zero vazamento cross-tenant, sem dupla cobrança/pagamento/pedido, RBAC/step-up, auditoria e prova de concorrência;
- **G2 desempenho:** baseline vs depois em ambiente equivalente; p50/p95/p99, rps, throughput útil e taxa 429/503 por classe; não comparar hardware diferente como se fosse A/B;
- **G3 resiliência:** DB down, pool exhaustion, falha/retry/cancelamento de modelo, timeout de cliente após commit, reentrega, circuit break, health e recuperação sem perda;
- **G4 release:** testes unitários/contratos/integrados, estáticos e CI todos verdes, PR review/checks, migrations/deploy aprovados conforme risco e política, rollback documentado e monitoramento pós-merge.
- **Não liberar** produção/alto fluxo comercial caso a IA cause 5xx em operação crítica, tenant leakage, perda financeira, dupla execução ou indisponibilidade de health por saturação.

## 6. Cronograma operacional sem datas fictícias
Estado inicial:
1. **Kordena — EM EXECUÇÃO (diagnóstico de IA certificado como reprovado, correções pendentes)**;
2. **FM Command — EM FILA (relatório de terceiro recebido, verificação própria e correções pendentes)**;
3. **Campaia — INVENTÁRIO PENDENTE**;
4. **Ironfit — INVENTÁRIO PENDENTE**;
5. **FM NFCore — INVENTÁRIO PENDENTE**.

Execução autorizada pelo proprietário por bloco governado: *executar → corrigir → testar → certificar → mergear → pós-merge → próximo item*, sem pedir confirmação repetitiva para cada PR. Escalar autorizações especiais quando houver segredos reais, migração destrutiva, risco financeiro/fiscal, cutover ou deploy de produção. Nunca declarar conclusão sem SHA, resultados e evidência verificável.
