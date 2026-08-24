---
name: kordena-system-design-guardian
description: Governa decisões arquiteturais do Kordena/GERENTE AI. Use ao criar, alterar, integrar, refatorar ou revisar domínios, boundaries, bancos, migrations, multi-tenant/unidade, RBAC, eventos, integrações, IA, runtime ou qualquer mudança estrutural.
metadata:
  version: "1.0.1"
  project: "kordena-gerente-ai"
---

# Kordena System Design Guardian

## Objetivo

Impedir evolução estrutural sem autoridade, impacto e rollback compreendidos. Favoreça mudanças mínimas, sistêmicas e comprováveis.

## Antes de implementar

1. Releia `AGENTS.md` e siga integralmente sua hierarquia de autoridade.
2. Registre a instrução/gate atual e as autoridades documentais consultadas; não trate documento anterior como substituto de decisão mais recente explicitamente aprovada pelo proprietário.
3. Se uma autoridade externa necessária não estiver acessível, **não adivinhe**; reporte a ausência.
4. Registre um mapa de impacto curto:
   - domínio/source of truth;
   - callers/consumidores;
   - persistência/schema;
   - tenant/unidade;
   - RBAC;
   - auditoria/idempotência;
   - transação/UoW;
   - integrações externas;
   - migrations/fresh/upgrade/rollback;
   - testes/fitness afetados.
5. Confirme se a mudança realmente precisa existir. Preserve código correto e evite rewrite por estética.

## Regras de arquitetura

- Arquitetura alvo: **Monólito Modular Governado**.
- Cada capacidade operacional deve ter autoridade explícita e contratos estreitos.
- UI, adapter e IA não podem criar fonte de verdade paralela.
- Active Execution Scope é a autoridade de tenant/unidade durante execução.
- Nenhum fallback silencioso para primeira loja, default global, sessão antiga ou valor de formulário.
- Escopo legado (`loja_id` etc.) é partição técnica quando o System Design assim definir; não crie nova autoridade por simetria.
- Cross-tenant/cross-store, ambiguidade de mapping ou ausência de autorização devem falhar fechado.
- RBAC usa menor privilégio; efeitos internos recebem apenas capacidades necessárias.
- Preserve actor, tenant, unidade, correlation/idempotency key e trilha de auditoria através de boundaries.
- Ownership transacional deve ser explícito. Evite commits parciais entre Pedido/Pagamento/Estoque/Eventos quando o caso de uso exigir atomicidade.
- Outbox/inbox/eventos devem permanecer idempotentes e não criar segunda autoridade operacional.
- IA é assistiva/orquestradora, nunca autoridade implícita para operação crítica.
- Segredos pertencem ao Vault/Secret Store; nunca persistir ou logar segredo em claro.

## Migrations

- Trate a história de migrations como patrimônio imutável, salvo decisão corretiva explicitamente aprovada pelo proprietário e registrada com impacto, compatibilidade e rollback.
- Prefira migration forward/additiva a reescrever migrations históricas.
- Fresh install e upgrade legado devem convergir para o mesmo estado relevante.
- Backfill deve ser determinístico; ambiguidade relevante deve abortar fail-closed.
- Não duplique registros automaticamente para “resolver” ambiguidade de ownership/saldo/custo.
- Manifest/fingerprint precisa corresponder legitimamente ao código.
- Preservar história estrutural de schema **não equivale** a aprovar comercialmente a feature associada.

## Estratégia de correção

Quando encontrar um defeito:

1. Determine se é bug local, dívida preexistente ou bloqueador estrutural.
2. Corrija a causa sistêmica mínima, não o sintoma visível.
3. Não amplie escopo para “aproveitar” a tarefa.
4. Se surgir nova decisão arquitetural não coberta pelo gate, **STOP** e devolva proposta/evidência.

## Saída esperada antes do código

Produza uma decisão curta contendo:

- autoridade consultada;
- problema/causa raiz;
- solução mínima;
- arquivos/domínios afetados;
- riscos e rollback;
- fitness/regressão necessários;
- STOP esperado.

Só então implemente.
