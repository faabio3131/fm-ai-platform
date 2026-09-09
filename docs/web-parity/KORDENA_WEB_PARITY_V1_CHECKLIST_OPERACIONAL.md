# Kordena V1 — Checklist Operacional de Migração Web

**Base preservada:** `731f6db17ec46a8173d10dd29897c8c623e52f16`

**Branch da missão:** `feat/web-parity-v1-total-original-migration`

**Regra:** este checklist controla migração, não certificação funcional.

| WP | Nome | Status Mestre | Estado Real Encontrado | Origem | Rota atual | Ação | Commit/Branch | Estado da Migração | Observação |
|---|---|---|---|---|---|---|---|---|---|
| WP-001 | Login / SSO corporativo | MIGRADO | Presente na Web | auth/session | `/login` | Preservar | base preservada | PRESERVADO | Não reconstruir |
| WP-002 | Escopo tenant/unidade + troca | MIGRADO | Presente na Web | auth/operational scope | Shell | Preservar | base preservada | PRESERVADO | Sessão assinada é autoridade |
| WP-003 | Roteamento por perfil/permissão | MIGRADO | Presente na Web | segurança/RBAC | Shell | Preservar | base preservada | PRESERVADO | Registry é fonte única |
| WP-004 | Home / Dashboard / Shell | MIGRADO | Presente na Web | shell/dashboard | `/` | Preservar | base preservada | PRESERVADO | Sem redesign |
| WP-005 | PDV Touch | MIGRADO | Presente na Web | core/pdv + application | `/pdv` | Preservar | base preservada | PRESERVADO | Bug de pagamento fica para pós-migração |
| WP-006 | Salão / Mesas / Comandas | MIGRADO | Presente na Web | core/salão + application | `/salao` | Preservar | base preservada | PRESERVADO | Não recriar |
| WP-007 | KDS / Cozinha | MIGRADO | Presente na Web | core/kds + application | `/kds` | Preservar | base preservada | PRESERVADO | Bug de roteamento fica para pós-migração |
| WP-008 | Atendimento do Garçom | GAP HTTP/WEB | Origem legada localizada | core/garcom + application | — | Migrar depois da retaguarda | missão atual | PENDENTE | Touch-first |
| WP-009 | Central de Pedidos | MIGRADO | Presente na Web | core/central_pedidos + application | `/pedidos` | Preservar | base preservada | PRESERVADO | Não criar outra Central |
| WP-010 | Delivery Próprio | GAP HTTP/WEB no Mestre | Implementação candidata presente | core/delivery + application | `/delivery` | Preservar | PR #117 / base preservada | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Não corrigir nesta fase |
| WP-011 | Expedição / Entrega | GAP HTTP/WEB no Mestre | Implementação candidata presente | core/entrega + application | `/entrega` | Preservar | PR #117 / base preservada | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Não corrigir nesta fase |
| WP-012 | Marketplaces / pedidos externos | GAP HTTP/WEB | Sem superfície Web | core/marketplaces + adapters | — | Migrar sem duplicar WP-009 | missão atual | PENDENTE | Integrar à Central existente |
| WP-013 | Catálogo administrativo básico | PARCIAL | Produtos/categorias presentes | catálogo legado escopado | `/admin/catalogo` | Completar somente a família faltante | missão atual | EM MIGRAÇÃO | Não criar segundo catálogo |
| WP-014 | Engenharia de Cardápio + Ficha | GAP HTTP/WEB no Mestre | Ficha manual e importação Gemini presentes na Web sobre boundary único | legacy_cardapio_transacoes + legacy_cardapio_gemini | `/admin/catalogo` | Preservar; aguardar certificação integrada | `9871814` / PR #118 | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Prompt, parsing e CMV original preservados; regra não duplicada no HTTP |
| WP-015 | Estoque / Almoxarifado / Validades | GAP HTTP/WEB no Mestre | Gestão manual/lote, forecasting/alertas e leitura visual presentes na Web sobre boundaries únicos | core/estoque + legacy_estoque_transacoes + boundaries de forecasting/leitura visual | `/admin/estoque` | Preservar; aguardar certificação integrada | `96e551d`, `c910153` / PR #118 | IMPLEMENTAÇÃO PRESENTE — AGUARDA CERTIFICAÇÃO | Sem lote físico ou FEFO inventado; prompts, thresholds e parsing preservados |
| WP-016 | CRM / Clientes / Cashback | GAP HTTP/WEB | Origem backend indicada no Mestre | core/crm + application | — | Migrar | missão atual | PENDENTE | Preservar consentimento e escopo |
| WP-017 | Marketing / Resgate / Campanhas | GAP HTTP/WEB | Origem backend indicada no Mestre | application/crm_marketing | — | Migrar | missão atual | PENDENTE | Sem nova regra de campanha |
| WP-018 | Dashboard Financeiro / Indicadores | GAP HTTP/WEB | UI legada comprovada | administracao_proprietario | — | Migrar read model | missão atual | PENDENTE | Não duplicar WP-020 |
| WP-019 | AI FinOps | GAP HTTP/WEB | Origem backend indicada no Mestre | ai_finops | — | Migrar | missão atual | PENDENTE | Módulo próprio |
| WP-020 | Área Proprietário / Backoffice | PARCIAL | Contêiner `/admin` presente | administracao_proprietario | `/admin/*` | Completar como contêiner | missão atual | PENDENTE | Não duplicar áreas filhas |
| WP-021 | Step-up administrativo | MIGRADO | Guard presente | auth/admin guard | `/admin` | Reutilizar | base preservada | PRESERVADO | Barreira única |
| WP-022 | Empresa / Unidades | GAP HTTP/WEB | Origem backend indicada no Mestre | core/administracao | — | Migrar | missão atual | PENDENTE | Preservar organização original |
| WP-023 | Usuários / Papéis / Permissões | GAP HTTP/WEB | Origem backend indicada no Mestre | core/seguranca | — | Migrar | missão atual | PENDENTE | Não alterar matriz RBAC |
| WP-024 | Parâmetros Financeiros | GAP HTTP/WEB | Origem backend indicada no Mestre | administração/pagamentos | — | Migrar não secretos | missão atual | PENDENTE | Segredos ficam no WP-026 |
| WP-025 | Impressão Operacional | GAP HTTP/WEB | Origem backend indicada no Mestre | core/impressao + application | — | Migrar | missão atual | PENDENTE | Não alterar PDV/KDS |
| WP-026 | Integrações e Credenciais | GAP HTTP/WEB | Origem backend indicada no Mestre | core/integracoes + application | — | Migrar console | missão atual | PENDENTE | Cofre/healthchecks existentes |
| WP-027 | Assistente de Atendimento | PARCIAL | Web/session faltante | assistente_atendimento | — | Completar superfície | missão atual | PENDENTE | Nome configurável por tenant |
| WP-028 | Gerente IA | PARCIAL | Facade Web/UI faltantes | gerente_ia | — | Completar superfície | missão atual | PENDENTE | Não alterar inteligência |
| WP-029 | Pagamentos / PIX / Provedores | PARCIAL | Operação no PDV; console faltante | pagamentos | `/pdv` | Completar superfícies | missão atual | PENDENTE | Não corrigir pagamentos agora |
| WP-030 | Cardápio Digital público | A VERIFICAR | Não confirmado | fontes oficiais a auditar | — | Auditar antes de decidir | missão atual | NÃO CONFIRMADO | Não implementar por suposição |
| WP-031 | Fiscal / NFC-e / SAT | A VERIFICAR | Não confirmado | fontes oficiais a auditar | — | Auditar antes de decidir | missão atual | NÃO CONFIRMADO | Não prometer |
| WP-032 | Notificações internas | A VERIFICAR | Serviço transversal localizado | notificacoes_internas | — | Auditar necessidade de UI | missão atual | NÃO CONFIRMADO | Não criar central por iniciativa |
| WP-033 | Auditoria / Histórico | GAP HTTP/WEB | Fonte legada indicada no Mestre | repositórios de auditoria | — | Expor consulta existente | missão atual | PENDENTE | Não criar segunda auditoria |
