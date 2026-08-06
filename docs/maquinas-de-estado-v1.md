# Máquinas de estado operacionais — V1

Documento normativo complementar à [arquitetura principal](arquitetura-operacional-v1.md). Transições não listadas são proibidas. `sistema` só atua por regra versionada; `Gerente IA` apenas solicita ações e nunca substitui a confirmação humana crítica.

**Colunas:** origem → destino; ator; pré-condições; evento; efeitos; reversibilidade/auditoria. Toda transição exige tenant da sessão, versão otimista, comando idempotente, horário, ator, motivo quando excepcional e `correlation_id`.

## Pedido

| Origem → destino | Quem | Pré-condições | Evento / efeitos | Reversibilidade e auditoria |
|---|---|---|---|---|
| rascunho → aguardando_confirmacao | canal, atendimento, garçom, caixa | ≥1 item válido; preços calculados | `pedido.aguardando_confirmacao`; congela proposta | volta a rascunho por nova versão; diff |
| aguardando_confirmacao → rascunho | cliente/operador | pedido não enviado | `pedido.reaberto_edicao`; invalida confirmação anterior | reversível; motivo/diff |
| aguardando_confirmacao → confirmado | cliente ou operador autorizado | itens/total/endereço/comanda confirmados; política e estoque avaliados | `pedido.confirmado`; reserva estoque e avalia cozinha | não desfazer; cancelar/alterar por comando |
| confirmado → enviado_producao | sistema, cozinha/gerente em override | `pode_enviar...` permitido; itens roteados | `pedido.enviado_producao`; cria produção/jobs | não voltar; cancelamento compensatório |
| enviado_producao → em_preparo | sistema por primeiro item | produção iniciada | `pedido.em_preparo`; timestamps/SLA | não; histórico automático |
| em_preparo → pronto | sistema por todos itens | todos produzíveis prontos/cancelados autorizados | `pedido.pronto`; alerta expedição/garçom | correção cria nova produção, não volta |
| pronto → em_expedicao | expedição/sistema | canal exige expedição | `pedido.em_expedicao`; checklist | não; auditar operador |
| pronto → servido | garçom | canal mesa; retirada registrada | `pedido.servido`; atualiza comanda | não; correção como ocorrência |
| pronto → entregue | balcão/atendimento | retirada; pagamento/política atendida | `pedido.entregue`; dispara conclusão financeira | não |
| em_expedicao → saiu_entrega | expedição | embalagem e entrega atribuída/coletada | `pedido.saiu_entrega`; notifica cliente | não; reentrada é ocorrência logística |
| em_expedicao → entregue | expedição | retirada/balcão conferido | `pedido.entregue` | não |
| saiu_entrega → entregue | entregador/integração | prova mínima ou confirmação autorizada | `pedido.entregue`; pagamento na entrega/reconciliação | não; contestação separada |
| servido → concluido | sistema/caixa | comanda fechada ou recebimento posterior autorizado | `pedido.concluido`; projeções finais | terminal; ajuste compensatório |
| entregue → concluido | sistema/financeiro | pagamento confirmado ou posterior autorizado; pendências resolvidas | `pedido.concluido`; cria/concilia Venda | terminal |
| pronto/em_expedicao → concluido | gerente/sistema | canal sem serviço/entrega; critério financeiro atendido | `pedido.concluido` | terminal; justificar atalho |
| rascunho/aguardando_confirmacao/confirmado/enviado_producao/em_preparo/pronto/em_expedicao/saiu_entrega → cancelado | cliente dentro da regra; atendimento/caixa/gerente por alçada | política de estágio, autorização, motivo; não concluído | `pedido.cancelado`; saga estoque/produção/entrega/estorno | terminal; novo pedido para refazer; registrar perdas/aprovações |

## Pagamento

| Origem → destino | Quem | Pré-condições | Evento / efeitos | Reversibilidade e auditoria |
|---|---|---|---|---|
| nao_iniciado → pendente | caixa/cliente/sistema | método online e cobrança criada | `pagamento.iniciado`; cria transação | cancelar; refs sem segredo |
| nao_iniciado → aguardando_entrega | sistema/atendimento | dinheiro/cartão na entrega permitido | `pagamento.aguardando_entrega`; registra obrigação | cancelar ou iniciar captura |
| nao_iniciado → aguardando_fechamento | garçom/caixa/sistema | comanda/pagamento na saída | `pagamento.aguardando_fechamento` | cancelar enquanto sem consumo financeiro |
| pendente/aguardando_entrega/aguardando_fechamento → parcialmente_pago | gateway/caixa | confirmação autêntica >0 e < saldo | `pagamento.parcial_confirmado`; atualiza saldo | estorno por transação compensatória |
| pendente/aguardando_entrega/aguardando_fechamento/parcialmente_pago → pago | gateway/caixa/sistema reconciliador | soma confirmada = obrigação; caixa tem permissão | `pagamento.confirmado`; habilita Venda/conclusão | somente estorno |
| pendente → falhou | gateway/sistema | falha final/autenticada ou timeout reconciliado | `pagamento.falhou`; oferece nova tentativa | nova transação pode voltar a pendente; preservar tentativa |
| falhou → pendente | cliente/caixa | nova tentativa idempotente | `pagamento.retentado` | sim; contador/auditoria |
| nao_iniciado/pendente/aguardando_entrega/aguardando_fechamento/falhou → cancelado | sistema/caixa/gerente | obrigação cancelável, sem valor capturado | `pagamento.cancelado`; cancela cobrança | terminal; novo pagamento separado |
| pago → estornado_parcial | financeiro/gerente + provedor | estorno >0 e < pago, motivo/alçada | `pagamento.estornado_parcial`; ajusta Venda | novo estorno ou nova cobrança; dupla confirmação |
| estornado_parcial → estornado | financeiro/provedor | total estornado = pago | `pagamento.estornado`; ajuste financeiro | terminal |
| pago → estornado | financeiro/provedor | estorno integral confirmado | `pagamento.estornado`; ajuste Venda | terminal |
| estornado_parcial → pago | financeiro/provedor | reversão externa comprovada e reconciliada | `pagamento.reversao_estorno_confirmada` | excepcional; auditoria reforçada |

## Comanda

| Origem → destino | Quem | Pré-condições | Evento / efeitos | Reversibilidade e auditoria |
|---|---|---|---|---|
| aberta → em_consumo | garçom/sistema | primeiro pedido confirmado | `comanda.consumo_iniciado`; ocupa mesa | não voltar; cancelar conforme regra |
| aberta/em_consumo → conta_solicitada | cliente/garçom | comanda ativa | `comanda.conta_solicitada`; bloqueio configurável de novos itens | pode voltar a consumo pelo garçom, auditado |
| conta_solicitada → em_consumo | garçom/gerente | cliente desistiu; sem fechamento capturado | `comanda.conta_reaberta` | sim; motivo |
| conta_solicitada → fechamento_em_andamento | caixa/garçom autorizado | conferência e divisão definidas | `comanda.fechamento_iniciado`; cria obrigações | pode abortar se sem captura; auditar |
| fechamento_em_andamento → parcialmente_paga | caixa/gateway | parte confirmada | `comanda.parcialmente_paga`; atualiza saldos | apenas compensação |
| fechamento_em_andamento/parcialmente_paga → fechada | caixa/sistema | saldo zero ou posterior autorizado; pedidos resolvidos | `comanda.fechada`; libera mesa, cria Vendas | terminal; ajustes separados |
| aberta/em_consumo/conta_solicitada → cancelada | gerente | sem consumo ou itens cancelados/resolvidos | `comanda.cancelada`; libera mesa | terminal; motivo/perdas |

## Produção

| Origem → destino | Quem | Pré-condições | Evento / efeitos | Reversibilidade e auditoria |
|---|---|---|---|---|
| aguardando → aceita | cozinha | item na fila/setor correto | `producao.aceita`; atribui operador | cancelável; SLA/ator |
| aguardando/aceita → em_preparo | cozinha | estoque consumido/resolvido; estação apta | `producao.iniciada`; baixa única, cronômetro | pausar/cancelar, não “desiniciar” |
| em_preparo → pausada | cozinha/gerente | motivo (insumo/equipamento/prioridade) | `producao.pausada`; pausa SLA conforme política | retomar; motivo obrigatório |
| pausada → em_preparo | cozinha | impedimento resolvido | `producao.retomada`; cronômetro | sim, histórico preservado |
| aceita/em_preparo/pausada → pronta | cozinha | quantidade concluída e checklist | `producao.pronta`; alerta/consolida pedido | não voltar; refação é nova tentativa |
| pronta → retirada | expedição/garçom | conferência e posse transferida | `producao.retirada`; encerra SLA | terminal |
| aguardando/aceita/em_preparo/pausada → cancelada | gerente; cozinha antes de início por regra | pedido/item cancelado, motivo | `producao.cancelada`; libera reserva ou registra perda | terminal; refazer cria tentativa; perda auditada |

## Entrega

| Origem → destino | Quem | Pré-condições | Evento / efeitos | Reversibilidade e auditoria |
|---|---|---|---|---|
| aguardando_producao → aguardando_expedicao | sistema | pedido pronto | `entrega.aguardando_expedicao`; checklist | não voltar; ocorrência se refação |
| aguardando_expedicao → aguardando_entregador | expedição | embalagem/conferência completas | `entrega.aguardando_entregador` | pode atribuir; checklist auditado |
| aguardando_producao/aguardando_expedicao/aguardando_entregador → atribuida | expedição/adapter | entregador disponível e aceitou; dados mínimos | `entrega.atribuida`; notifica | reatribuir via evento mantendo estado/versão |
| atribuida → coletada | entregador/expedição | entrega física conferida | `entrega.coletada`; inicia custódia | não voltar |
| coletada → em_rota | entregador/adapter | saída registrada | `entrega.em_rota`; tracking consentido | não voltar |
| em_rota/coletada → entregue | entregador/adapter | prova/confirmação válida; pagamento na entrega resolvido ou exceção | `entrega.concluida`; atualiza pedido/pagamento | terminal; contestação separada |
| em_rota → tentativa_falhou | entregador/atendimento | motivo e tentativa registrados | `entrega.tentativa_falhou`; contato/reprogramação | pode reatribuir/coletar por nova tentativa; histórico |
| tentativa_falhou → atribuida | expedição/atendimento | nova tentativa aprovada/endereço confirmado | `entrega.reatribuida`; incrementa tentativa | sim operacionalmente; auditar mudança |
| aguardando_producao/aguardando_expedicao/aguardando_entregador/atribuida/tentativa_falhou → cancelada | atendimento/gerente | pedido cancelado e custódia resolvida | `entrega.cancelada`; notifica/reconcilia taxa | terminal; motivo/alçada |

## Invariantes entre máquinas

* `Pedido.enviado_producao` depende da decisão, não de `Pagamento.pago` universalmente.
* `Produção.pronta` não conclui Pedido nem Venda.
* `Entrega.entregue` pode confirmar dinheiro/cartão na entrega, mas a confirmação financeira é evento próprio.
* `Comanda.fechada` exige saldo resolvido ou recebimento posterior autorizado.
* Pedido só conclui com serviço/entrega resolvido e critério financeiro atendido.
* Estado terminal não é reaberto; correções usam novos agregados/transações/eventos compensatórios.
