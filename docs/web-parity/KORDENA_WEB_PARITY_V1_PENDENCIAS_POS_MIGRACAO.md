# Kordena V1 — Pendências para Certificação e Correção Pós-Migração

Este registro preserva observações conhecidas sem propor nem executar correções durante a missão de migração Web.

| WP | Módulo | Comportamento observado | Evidência | Arquivo provável | Impacto | Classificação preliminar |
|---|---|---|---|---|---|---|
| WP-005 | PDV | Fluxo de pagamento em dinheiro apresenta comportamento inconsistente | Ordem executiva de 09/09/2026 | `web/src/features/pdv`; `http_api/pdv.py`; pagamentos canônicos | Jornada de caixa | BUG / ALTA |
| WP-005 / WP-029 | Financeiro/Pagamentos | Liquidação financeira não está comprovadamente consistente | Ordem executiva de 09/09/2026 | `core/pagamentos`; `application`; `http_api/pdv.py` | Integridade financeira | BUG / BLOQUEADOR |
| WP-007 | KDS | Roteamento e seta de roteamento apresentam comportamento observado como inconsistente | Ordem executiva de 09/09/2026 | `web/src/features/kds`; `http_api/kds.py` | Produção/cozinha | BUG / ALTA |
| WP-009 | Central de Pedidos | Existem mensagens operacionais inconsistentes | Ordem executiva de 09/09/2026 | `web/src/features/orders`; `http_api/central_pedidos.py` | Clareza operacional | BUG / MÉDIA |
| WP-007 / WP-009 | Pedido e Produção | Integração entre pedido e produção requer certificação e correção posterior | Ordem executiva de 09/09/2026 | `core/central_pedidos`; `core/kds`; respectivos adapters HTTP | Fluxo ponta a ponta | BUG / ALTA |
| WP-010 / WP-011 | Delivery/Entrega | Fluxos de Delivery e Entrega aguardam certificação integrada | Ordem executiva de 09/09/2026 e PR #117 Draft | `/delivery`; `/entrega`; routers correspondentes | Operação logística | FUNCIONALIDADE PARCIAL / ALTA |
