# KORDENA V2 — Proposta de Evolução: Painel Operacional Unificado
**ID:** KORDENA-V2-POU-001  
**Data:** 2026-10-11  
**Status:** RASCUNHO DE DESCOBERTA / CANDIDATO À V2 — NÃO APROVADO PARA IMPLEMENTAÇÃO  
**Origem:** referência visual aprovada conceitualmente pelo proprietário, com três colunas de pedidos e sugestões do Gerente IA.  
**Escopo:** estudo arquitetural, sem alterações funcionais, migrações ou deploy.

## 1. Objetivo
Estudar um dashboard operacional único para restaurante, com visão **Novos / Em preparo / Prontos**, detalhes de cada pedido, alertas de SLA, origem/canal, atualização de estado e recomendações governadas do Gerente IA. A interface deve reaproveitar os domínios existentes e não criar uma segunda fonte de verdade.

## 2. Evidências verificadas no código
Leitura estática do checkout local `fm-ai-platform-visual-fix`, branch `fix/kordena-dashboard-compact-layout`, HEAD `b163163`. **Este snapshot não foi confirmado como a versão mais recente da main nem como produção.**
- `web/src/features/shell/components/DashboardHome.tsx`: dashboard atual centrado em navegação/cartões por módulos; não implementa o Kanban unificado mostrado na referência.
- `web/src/features/shell/module-registry.ts`: módulos Central de Pedidos (`/pedidos`, `pedido.visualizar`), KDS (`/kds`, `producao.visualizar`), PDV, Salão, Delivery, Entrega, Gerente IA e áreas administrativas com permissões específicas.
- `web/src/features/orders/components/OrdersCenterWorkspace.tsx`: listagem, busca/filtros, paginação, detalhes, ações de confirmação/cancelamento, controle de concorrência HTTP 409 e atualização sob demanda. Não foi encontrado polling periódico nesta tela analisada.
- `web/src/features/orders/services/orders-api.ts`: `GET /v1/pedidos` e detalhes; resumo com `pedido_id`, `canal`, `status`, timestamps, quantidade de itens, alertas, versão e financeiro.
- `http_api/central_pedidos.py`: API canônica de listagem, detalhe e transições; contexto operacional; versão/idempotência e respostas de conflito.
- `http_api/kds.py`: estados de produção por item `aceita`, `em_preparo`, `pausada`, `pronta`, `retirada`, `cancelada`; informações de SLA, setor, itens e timestamps.
- `web/src/features/kds/components/KDSWorkspace.tsx`: polling de 5 segundos em implementação examinada; não implica que o dashboard possua atualização em tempo real.
- `web/src/features/gerente-ia/components/GerenteIAWorkspace.tsx` e `services/gerente-ia-api.ts`: perguntas operacionais, `POST /v1/gerente-ia/perguntar`, preview e confirmação governada `POST /v1/gerente-ia/confirmar` com `preview_id`, `fingerprint` e `idempotency_key`. Não foi comprovada uma fila de sugestões proativas com botões Aprovar/Recusar por cartão.

## 3. Lacunas para equivalência com a referência
1. Projeção consolidada dos estados comerciais, de produção e expedição.
2. Endpoint de leitura agregado para três colunas, contadores, SLA, alertas e paginação por coluna.
3. Kanban responsivo com cartões de pedidos reais, acesso ao detalhe e estados vazios/erro.
4. Estratégia de atualização, reconciliação após reconexão, controle de versões e dados obsoletos.
5. Mecanismo de sugestões proativas fundamentadas em sinais reais, com validade, proveniência, deduplicação e autorização.
6. UX de aprovação, recusa, justificativa e auditoria por sugestão; autorização no backend, nunca apenas no botão.
7. Testes ponta a ponta multicanal, multiunidade, concorrência, isolamento e desempenho.

## 4. Semântica proposta das colunas (a validar com os donos dos domínios)
- **Novos:** recebidos e aguardando aceite/confirmação ou encaminhamento para produção.
- **Em preparo:** confirmados com itens de produção ainda pendentes, aceitos, em preparo ou pausados.
- **Prontos:** todos os itens obrigatórios prontos e pedido apto à retirada/expedição, conforme o canal.
- **Exceções:** cancelados, bloqueados, divergentes ou atrasados devem ter sinalização separada, não desaparecer silenciosamente.

**Regra crítica:** um pedido com múltiplos itens/setores não pode ser marcado pronto porque apenas um item ficou pronto. Distinguir *produção pronta*, *pedido expedido*, *pedido entregue* e *pedido finalizado*. Formalizar tabela de transições, precedências, eventos fora de ordem e tratamento de pedidos sem KDS. A UI nunca deve gravar diretamente estado de produção por mera movimentação visual de cartão.

## 5. Arquitetura candidata
Fontes canônicas (Central de Pedidos, KDS, PDV, Salão, Delivery, Entrega, Estoque) → **Operational Board Read Model / Projection** → API autenticada de supervisão → dashboard. Gerente IA consome dados autorizados e produz sugestões governadas em fluxo separado.

- Preferir projeção de leitura/CQRS seletivo apenas se necessário; evitar duplicar estado transacional.
- Iniciar com polling controlado e medições de latência/custo; estudar SSE/WebSocket depois, se justificável.
- Usar escopo da sessão assinada (tenant e unidade), RBAC e minimização de dados; impedir spoofing por cabeçalhos.
- Manter versionamento otimista, idempotência, auditoria, correlation IDs, limites de consulta, observabilidade e recuperação de falhas.
- Nenhuma recomendação de IA executa automaticamente ação sensível sem política e autorização humana apropriada.

## 6. Entregas candidatas e gates
| Etapa | Entrega | Gate |
|---|---|---|
| V2-POU-A | Contrato canônico de estados e cenários multicanal | Matriz de estados aprovada e testes de agregação |
| V2-POU-B | Read model e API agregada | Isolamento por tenant/unidade, paginação, consistência e carga |
| V2-POU-C | Dashboard Kanban premium | Responsividade, acessibilidade, dados reais e navegação funcional |
| V2-POU-D | Atualização e resiliência | SLA medido, reconexão, concorrência, erros e recuperação |
| V2-POU-E | Gerente IA proativo | Proveniência, aprovação/recusa, autorização e auditoria |
| V2-POU-F | Certificação integral | Testes de integração, segurança, regressão e aceite visual |

O Kanban pode ser entregue antes da IA proativa. Cada etapa deve ser funcional, testada e aprovada antes da próxima.

## 7. Critérios mínimos de aceite
- Pedidos de diferentes canais classificados corretamente, inclusive múltiplos itens/setores e cancelamentos.
- Dados reais; sem cartões fictícios em produção; timestamps e origem rastreáveis.
- Mudanças no KDS refletidas dentro de SLA mensurado e sem dupla transição.
- Usuários só visualizam dados e ações permitidos; financeiro restrito conforme RBAC.
- Operações críticas exigem confirmação e permanecem auditáveis.
- Sem regressão no PDV, Salão, Delivery, KDS, Central de Pedidos ou step-up do Proprietário.
- UX desktop/tablet/mobile validada contra referência visual e por testes funcionais.

## 8. Pendências de descoberta e decisões
- Comparar este snapshot com a branch principal, PRs abertas e deploy efetivo.
- Inventariar estados reais de pedido, KDS, expedição, delivery e cancelamento e respectivos testes.
- Confirmar contrato de agregação por pedido/itens e canais sem produção KDS.
- Determinar SLA de atualização, limites de volume e estratégia de paginação.
- Definir quais alertas e sugestões serão permitidos por perfil.
- Aprovar layout final, ordem de execução, estimativa e encaixe no cronograma oficial da V2.

## 9. Governança e decisão
**Registro de proposta apenas.** Este documento não altera o Plano Mestre, não autoriza desenvolvimento, merge, deploy ou promoção de V2, nem afirma homologação de recursos. A inclusão no cronograma oficial depende de revisão arquitetural, análise de dependências, aprovação humana e gates definidos. Nenhuma credencial, dado de cliente ou segredo deve ser registrado neste documento.
