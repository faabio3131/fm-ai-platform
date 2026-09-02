# System Design — Fase 8 — KDS — Commercial Cutover V1

**Status:** APROVADO PARA IMPLEMENTAÇÃO CONTROLADA  
**Issue:** #73  
**Base:** `f883f898e27c27f01af8930303a13e7f548d7397`

## 1. Princípio arquitetural

O KDS V1 já é um domínio canônico. A Fase 8 é um **cutover de evidência e
composition**, não uma reconstrução.

A arquitetura deve continuar separando:
- Pedido = estado macro autoritativo;
- KDS = estado detalhado da produção;
- Estoque = ledger/reserva autoritativos;
- Expedição = retirada/posse;
- UI = apresentação, nunca fonte de verdade.

## 2. Fontes autoritativas

| Dado/Efeito | Autoridade |
|---|---|
| usuário/tenant/unidade | IdentidadeUsuario / Active Execution Scope |
| pedido/itens/status macro | core.pedidos |
| item/setor/status produção | core.kds |
| saldo/reserva/consumo | core.estoque |
| permissões | core.seguranca |
| eventos | outbox/event bus canônico |
| auditoria | repositório de auditoria canônico |
| schema KDS | migration 0010 |
| UI | nenhuma autoridade |

## 3. Componentes

### Commercial composition
- `app.py`;
- `core.kds.flags.kds_v1_enabled`;
- `core.kds.ui_comercial.render_kds`;
- `core.kds.ui_roteamento`;
- `core.kds.ui_runtime`.

### Application
- `application.kds_roteamento`;
- `application.kds_transacoes`;
- `application.kds_runtime_core.ServicoKDSCanonico`.

### Domínio/persistência
- `core.kds.ServicoKDS`;
- `RepositorioKDSSQLAlchemy`;
- `KDSBase`.

### Dependências canônicas
- Pedido;
- Estoque;
- Event Bus/Outbox;
- Auditoria;
- Segurança/RBAC.

## 4. Composition root e identidade

No runtime comercial:
1. `app.py` autentica a identidade;
2. KDS recebe `session_factory` real;
3. renderer obtém `IdentidadeUsuario` ativa;
4. `ContextoExecucao` deriva tenant/unidade/papeis/permissões;
5. widgets/query params nunca definem identidade, tenant, unidade ou papel.

Contexto injetado só é válido com `FM_AI_TEST_MODE=1`.
Schema E2E só pode ser preparado nesse mesmo boundary isolado.

O Commercial Runtime E2E da Fase 8 deve remover/ignorar todas as variáveis de
TEST_MODE e usar migrations oficiais.

## 5. Fluxo de roteamento

1. Pedido canônico está `CONFIRMADO`;
2. `listar_itens_pendentes` consulta itens ainda não roteados no mesmo escopo;
3. operador com `PRODUCAO_ATUALIZAR` seleciona setor;
4. UI fecha sessão de leitura;
5. `rotear_item_kds_v1` abre `UnitOfWorkV1`;
6. `ServicoKDSCanonico.rotear_item` valida Pedido/setor/escopo;
7. Pedido passa a `ENVIADO_PRODUCAO`;
8. Produção nasce `aguardando`;
9. evento/outbox e auditoria são persistidos;
10. commit é feito apenas pela Application/UoW.

Replay da mesma idempotency key deve retornar o efeito existente, nunca duplicar
produção nem evento econômico.

## 6. Fluxo de produção

### aguardando -> aceita
Permissão: `PRODUCAO_ACEITAR`.  
Precondição: setor correto.

### aceita -> em_preparo
Permissão: `PRODUCAO_ATUALIZAR`.  
Precondições: estoque resolvido + estação apta.

Efeito macro:
- Pedido `ENVIADO_PRODUCAO -> EM_PREPARO`;
- reserva de Estoque é consumida no início real da produção;
- replay não duplica consumo.

### em_preparo -> pausada
Permissão: `PRODUCAO_ATUALIZAR`.  
Motivo obrigatório.

### pausada -> em_preparo
Permissão: `PRODUCAO_ATUALIZAR`.  
Precondição: impedimento resolvido.

### em_preparo -> pronta
Permissão: `PRODUCAO_ATUALIZAR`.  
Precondições: quantidade concluída + checklist concluído.

Quando todos os itens do Pedido estão `pronta` ou `retirada`:
- Pedido macro -> `PRONTO`.

### pronta -> retirada
Permissão exclusiva: `EXPEDICAO_OPERAR`.  
Precondições: conferência realizada + posse transferida.

COZINHA não recebe essa permissão.

## 7. Concorrência e idempotência

Preservar:
- version/CAS em cada Produção;
- fingerprint da operação;
- idempotency key;
- unicidade lógica de roteamento;
- eventos/outbox idempotentes;
- consumo de reserva exatamente uma vez.

Gates:
- replay serial;
- duas sessões concorrentes na mesma produção;
- stale version;
- mesma idempotency key com payload diferente;
- tentativa de rotear item já roteado.

Nenhum retry deve duplicar:
- Produção;
- transição;
- consumo de Estoque;
- evento;
- auditoria.

## 8. Tenant/unidade

Todas as consultas e writes devem conter tenant+unidade do contexto.

Provas negativas:
- Pedido de outra unidade não aparece para roteamento;
- Produção de outro tenant não aparece na fila;
- id conhecido de outro escopo retorna indisponível/fail-closed;
- eventos e estoque nunca cruzam escopo.

## 9. RBAC

### COZINHA
`PRODUCAO_VISUALIZAR`, `PRODUCAO_ACEITAR`, `PRODUCAO_ATUALIZAR`.

### EXPEDICAO
`PRODUCAO_VISUALIZAR`, `EXPEDICAO_OPERAR`.

### GERENTE/ADMIN
Alçada elevada existente.

Composition deve evitar expor ações impossíveis ao perfil, mas **a segurança
final continua no domínio/Application**. UI invisível não substitui autorização.

## 10. Degradação e fail-closed

Leitura:
- falha SQL pode retornar último snapshot conhecido;
- snapshot é marcado `degradado=True` e `somente_leitura=True`;
- sem snapshot, retornar fila vazia/degradada, nunca estado inventado.

Write:
- falha de persistência -> `kds_offline_somente_leitura`;
- nenhum fallback in-memory;
- nenhum commit parcial;
- nenhuma transição otimista apenas na UI.

A checkbox “Simular KDS offline” permanece exclusiva do E2E isolado e nunca
deve aparecer no commercial default.

## 11. Eventos, auditoria e downstream

Cada roteamento/transição canônica mantém:
- correlation id;
- idempotency key;
- evento/outbox;
- auditoria.

Downstream pode reagir a `pronta`, mas não se torna autoridade do estado KDS.
Falha de notificação best-effort não reverte a transação KDS já confirmada.

## 12. Persistência/migrations

Migration oficial:
`0010_kds_authoritative_runtime_v1`.

F8 não cria migration por conveniência. Antes de qualquer migration:
1. PostgreSQL fresh;
2. upgrade;
3. comparação ORM/schema;
4. drift reproduzível;
5. migration forward;
6. rollback lógico/documentado sem destruição automática.

## 13. Desempenho

Não introduzir nova fila/cache/tabela.
Preservar:
- filtro por setor;
- ordenação por prioridade;
- cache apenas para degradação;
- queries tenant/unidade.

Se carga revelar gargalo, medir antes de materializar nova projeção.

## 14. Commercial Runtime E2E

O gate F8-E deverá:
1. subir PostgreSQL 16;
2. aplicar runner oficial;
3. criar identidades comerciais reais, sem TEST_MODE;
4. criar Pedido/itens/reserva por APIs/serviços canônicos de seed de staging;
5. iniciar `app.py`;
6. autenticar COZINHA;
7. abrir aba KDS;
8. rotear item confirmado para setor;
9. aceitar;
10. iniciar;
11. opcionalmente pausar/retomar como prova de estado;
12. marcar pronto;
13. validar Pedido macro `PRONTO`;
14. validar consumo de Estoque/eventos/auditoria no PostgreSQL;
15. provar que COZINHA não vê/usa “Registrar retirada”;
16. autenticar EXPEDICAO para provar retirada, se necessário ao gate;
17. executar prova negativa de perfil sem acesso;
18. rodar matriz transversal no mesmo SHA.

O histórico `tests/e2e-kds/app_kds.py` continua como regressão de domínio e não
substitui este gate.

## 15. Rollback

Antes de merge:
- reverter commits da branch F8.

Após integração futura:
- desabilitar `FM_AI_KDS_V1` server-side;
- preservar Pedido, Produção, Estoque, Eventos e Auditoria;
- não executar downgrade destrutivo da migration 0010;
- rollback de UI/composition não apaga histórico operacional.

## 16. Estratégia por bloco

### F8-B
- fitness commercial boundary;
- RBAC/visibilidade;
- nenhum test harness no default.

### F8-C
- roteamento e transições;
- Pedido macro;
- Estoque;
- eventos/auditoria.

### F8-D
- multi-setor;
- concorrência/idempotência;
- isolamento;
- degradação/fail-closed.

### F8-E
- PostgreSQL;
- login real;
- browser;
- evidência pós-browser;
- matriz transversal;
- readiness/inventário/checkpoint.

## 17. Critérios de promoção

F8 só fecha tecnicamente quando:
- Commercial Runtime E2E específico estiver verde;
- browser usar `app.py` e identidade real;
- migration 0010 estiver current em PostgreSQL;
- RBAC positivo/negativo estiver provado;
- Pedido/Estoque/Eventos permanecerem consistentes;
- nenhuma autoridade paralela existir;
- matriz crítica/transversal estiver verde no mesmo SHA;
- readiness e inventário refletirem a evidência.

Nenhum merge/deploy é autorizado por este System Design.
