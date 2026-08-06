# Plano de Pull Requests — expansão operacional V1

Complementa a [arquitetura](arquitetura-operacional-v1.md) e o [plano de migração](plano-migracao-pedidos-v1.md). Cada PR deve ser pequeno, atrás de flag quando executável, sem migração destrutiva, com observabilidade, segurança multiempresa e rollback documentado.

## Ordem revisada

| PR | Escopo e entregável | Dependência / aceite principal |
|---:|---|---|
| 1 | **Contratos de domínio:** IDs/Decimal/tempo, enums, schemas de comandos/eventos, erros, snapshots e `DecisaoCozinha`; nenhuma ORM | Base; unitários/contratos, sem diff funcional |
| 2 | **Fundação de segurança e contexto:** tenant/unidade autenticados, RBAC/alçadas, auditoria e correlation IDs | PR1; testes IDOR/multiempresa e ações críticas |
| 3 | **Infra de eventos:** interfaces outbox/inbox, idempotência, retry/DLQ e observabilidade (ainda adapter in-memory/teste) | PR1–2; duplicatas e replay seguros |
| 4 | **Persistência aditiva do Pedido:** modelos/repositories de Pedido, Item, adicionais, observações e eventos; migration somente mediante autorização específica | PR1–3; upgrade/downgrade em banco efêmero, nenhum dado legado alterado |
| 5 | **Máquinas/política de cozinha:** serviços puros, transições, autorização, matriz por canal e risco | PR2,4; tabela completa e property tests |
| 6 | **Ledger/reserva de estoque:** movimentos idempotentes, concorrência, snapshot de ficha e compensações | PR3–5; corrida simultânea/zero dupla baixa |
| 7 | **Pagamento e consequência Venda:** obrigações/transações, webhook/reconciliação, critérios financeiros e adapter de Venda legada | PR3–6; pagamento não controla universalmente cozinha; relatórios conciliam |
| 8 | **Vertical slice PDV:** escrita sombra, flags, Pedido autoritativo canary, compatibilidade de cashback/dashboard | PR7; E2E PDV e rollback, nenhuma dupla Venda/baixa |
| 9 | **Central de Pedidos:** projeções, filtros, detalhe, comandos permitidos e alertas | PR5–8; RBAC/responsividade/auditoria |
| 10 | **KDS por setor:** filas, aceite/início/pausa/pronto/retirada e SLAs | PR5–6,9; E2E multi-setor/offline degradado |
| 11 | **Mesas e comandas:** mapa, participantes, múltiplos pedidos, transferir/juntar/separar/dividir/pagamento misto/fechar | PR5,7,9; invariantes financeiros e concorrência |
| 12 | **Interface do garçom:** celular/tablet, atualizações, aviso de pronto e alçadas | PR10–11; acessibilidade e E2E por papel |
| 13 | **Expedição e entrega:** checklist, atribuição, tentativas, prova e pagamento na entrega | PR7,10; dados mínimos e transições completas |
| 14 | **Impressão opcional:** spool por setor, deduplicação, reimpressão auditada e contingência | PR10; KDS permanece padrão, falha não bloqueia indevidamente |
| 15 | **Refatoração da Mica:** Conversa/Carrinho/Pedido/Pagamento/Pós-venda, schemas estritos, confirmação e handoff | PR8–10,13; zero fallback inventado/primeiro item/pagamento falso |
| 16 | **Delivery próprio:** catálogo/carrinho/endereço/área/taxa/SLA/cupom/cashback/tracking/cancelamento/repetição | PR7,9,13,15; jornada e concorrência completas |
| 17 | **Framework de adapters e primeiro marketplace:** integração, PedidoExterno, inbox, capacidades, reconciliação e sandbox de um provedor | PR3,9,13; contrato, fora de ordem, retry/DLQ |
| 18 | **Adapters adicionais:** iFood/99Food/Keeta conforme APIs/credenciais disponíveis, um adapter por commit/flag | PR17; testes oficiais/sandbox por plataforma |
| 19 | **CRM e conversão consentida:** cliente marketplace restrito, consentimento/opt-out, funil, cupom/cashback | PR16–18; marketing negado por padrão e revogação imediata |
| 20 | **Gerente IA:** tools somente sobre services, consultas primeiro, preview/confirm para ações, campanha em rascunho | PR2,9–19; prompt injection/RBAC/auditoria; sem voz no caixa |
| 21 | **Hardening transversal:** carga, caos/offline, segurança, privacidade, acessibilidade, migração/restore, SLOs e runbooks | Todos; critérios de aceite da V1 e go/no-go |

## Por que a sugestão inicial mudou

1. **Segurança, tenant e auditoria antecedem modelos operacionais**, evitando retrofit perigoso.
2. **Outbox/inbox antecedem canais**, pois estoque, KDS, pagamento e marketplace precisam da mesma idempotência.
3. **Estoque antecede PDV novo/KDS**, eliminando desde o primeiro vertical slice a dupla baixa.
4. **Pagamento/Venda antecedem integração PDV**, garantindo o princípio de independência no primeiro fluxo real.
5. **PDV vertical vem antes da Central**, oferecendo uma fonte real, pequena e reversível para validar projeções.
6. **Impressão vem após KDS**, preservando KDS como padrão.
7. **Mica vem depois dos serviços operacionais**, para que a IA orquestre contratos e não banco/UI.
8. **Framework de marketplace e um adapter vêm antes dos demais**, reduzindo suposições e isolando capacidades.
9. Hardening não substitui testes em cada PR; é gate final com carga, restore e operação assistida.

## Template obrigatório por PR

* Problema, escopo/não escopo, dependências e ADR afetado.
* Contratos e invariantes; ameaça/PII/tenant; compatibilidade legada.
* Feature flag, plano de rollout/canary, métricas/alertas e rollback.
* Testes unitários, integração, contrato e E2E aplicáveis.
* Para banco: autorização, migration aditiva, locks, backup/restore e downgrade não destrutivo.
* Evidência de idempotência, auditoria e reconciliação.

## Gates de release

* **Gate A (PR 7):** domínio, segurança, eventos, persistência, estados, estoque e financeiro estáveis.
* **Gate B (PR 8):** primeiro fluxo Pedido → Pagamento/Venda executado em canary e reconciliado.
* **Gate C (PR 14):** operação interna PDV/KDS/salão/entrega com contingência.
* **Gate D (PR 19):** canais digitais e consentimento validados.
* **Gate E (PR 21):** restore/rollback, SLOs, segurança, LGPD e critérios da arquitetura aprovados.

Nenhum gate autoriza merge automático, deploy, migration real ou início do PR seguinte; cada etapa aguarda aprovação humana.
