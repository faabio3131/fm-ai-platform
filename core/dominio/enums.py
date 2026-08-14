from enum import StrEnum


def _enum(nome: str, valores: str):
    return StrEnum(nome, {v: v.lower() for v in valores.split()})


PedidoStatus = _enum(
    "PedidoStatus",
    "RASCUNHO AGUARDANDO_CONFIRMACAO CONFIRMADO ENVIADO_PRODUCAO EM_PREPARO PRONTO EM_EXPEDICAO SAIU_ENTREGA SERVIDO ENTREGUE CONCLUIDO CANCELADO",
)
PagamentoStatus = _enum(
    "PagamentoStatus",
    "NAO_INICIADO PENDENTE AGUARDANDO_ENTREGA AGUARDANDO_FECHAMENTO PARCIALMENTE_PAGO PAGO FALHOU CANCELADO ESTORNADO_PARCIAL ESTORNADO",
)
ComandaStatus = _enum(
    "ComandaStatus",
    "ABERTA EM_CONSUMO CONTA_SOLICITADA FECHAMENTO_EM_ANDAMENTO PARCIALMENTE_PAGA FECHADA CANCELADA",
)
ProducaoStatus = _enum(
    "ProducaoStatus", "AGUARDANDO ACEITA EM_PREPARO PAUSADA PRONTA RETIRADA CANCELADA"
)
EntregaStatus = _enum(
    "EntregaStatus",
    "AGUARDANDO_PRODUCAO AGUARDANDO_EXPEDICAO AGUARDANDO_ENTREGADOR ATRIBUIDA COLETADA EM_ROTA ENTREGUE TENTATIVA_FALHOU CANCELADA",
)

# Origem identifica de onde o pedido nasceu. Mantemos valores genéricos legados
# para retrocompatibilidade, mas novos adapters devem preferir a origem específica.
OrigemPedido = _enum(
    "OrigemPedido",
    "BALCAO PDV SALAO MESA RETIRADA DELIVERY_PROPRIO IFOOD FOOD99 KEETA MARKETPLACE WHATSAPP MICA GARCOM TELEFONE ADMINISTRATIVO OUTRO",
)

# Canal identifica a jornada comercial usada pelo cliente/operador. Plataformas
# recebem valores próprios para permitir financeiro e observabilidade por canal.
CanalAtendimento = _enum(
    "CanalAtendimento",
    "PRESENCIAL PDV SALAO WHATSAPP MICA DELIVERY_PROPRIO IFOOD FOOD99 KEETA MARKETPLACE QR_MESA GARCOM TELEFONE ADMINISTRATIVO OUTRO",
)

FormaPagamento = _enum(
    "FormaPagamento",
    "PIX DINHEIRO CARTAO_CREDITO CARTAO_DEBITO CARTAO_ONLINE PAGAMENTO_MISTO CORTESIA OUTRO",
)
MomentoPagamento = _enum(
    "MomentoPagamento",
    "ANTECIPADO NA_ENTREGA NA_RETIRADA NO_FECHAMENTO NA_SAIDA POSTERIOR_AUTORIZADO",
)
RiscoPedido = _enum("RiscoPedido", "BAIXO MEDIO ALTO BLOQUEADO")
PapelUsuario = _enum(
    "PapelUsuario",
    "ADMINISTRADOR GERENTE CAIXA GARCOM COZINHA EXPEDICAO ENTREGADOR ATENDIMENTO FINANCEIRO GERENTE_IA",
)
MotivoCancelamento = _enum(
    "MotivoCancelamento",
    "SOLICITACAO_CLIENTE INDISPONIBILIDADE ERRO_OPERACIONAL FRAUDE OUTRO",
)
TipoEvento = _enum("TipoEvento", "DOMINIO INTEGRACAO")
CodigoDecisaoCozinha = _enum(
    "CodigoDecisaoCozinha",
    "PERMITIDO_PAGAMENTO_POSTERIOR PERMITIDO_PAGAMENTO_CONFIRMADO PERMITIDO_MARKETPLACE_CONFIRMADO BLOQUEADO_PAGAMENTO_PENDENTE BLOQUEADO_RISCO_ALTO BLOQUEADO_ESTOQUE EXIGE_APROVACAO_MANUAL BLOQUEADO_POLITICA_CANAL",
)