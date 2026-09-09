from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.decisoes import DecisaoCozinha
from core.dominio.enums import CodigoDecisaoCozinha, PagamentoStatus, RiscoPedido
from core.pagamentos.modelos_orm import PagamentoORM

_STATUS_RECEBIMENTO_POSTERIOR_AUTORIZADO = frozenset(
    {
        PagamentoStatus.PENDENTE.value,
        PagamentoStatus.AGUARDANDO_ENTREGA.value,
        PagamentoStatus.AGUARDANDO_FECHAMENTO.value,
    }
)


def _valor(valor: object) -> Decimal:
    return Decimal(str(valor or 0))


def _quitado(pagamento: PagamentoORM) -> bool:
    return (
        pagamento.status == PagamentoStatus.PAGO.value
        and _valor(pagamento.valor_pago) - _valor(pagamento.valor_estornado)
        >= _valor(pagamento.valor_previsto)
    )


def _recebimento_posterior_autorizado(pagamento: PagamentoORM) -> bool:
    return _quitado(pagamento) or (
        bool(pagamento.recebimento_posterior)
        and pagamento.status in _STATUS_RECEBIMENTO_POSTERIOR_AUTORIZADO
    )


def decidir_cozinha(
    session: Session,
    tenant_id: str,
    unidade_id: str,
    pedido_id: str,
    instante: datetime,
) -> DecisaoCozinha:
    rows = session.scalars(
        select(PagamentoORM).where(
            PagamentoORM.tenant_id == tenant_id,
            PagamentoORM.unidade_id == unidade_id,
            PagamentoORM.pedido_id == pedido_id,
        )
    ).all()

    pago = bool(rows) and all(_quitado(pagamento) for pagamento in rows)
    posterior = bool(rows) and all(
        _recebimento_posterior_autorizado(pagamento) for pagamento in rows
    )

    if pago:
        codigo = CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_CONFIRMADO
        permitido = True
        risco = RiscoPedido.BAIXO
        motivo = "Pagamento confirmado"
    elif posterior:
        codigo = CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_POSTERIOR
        permitido = True
        risco = RiscoPedido.MEDIO
        motivo = "Recebimento posterior autorizado"
    else:
        codigo = CodigoDecisaoCozinha.BLOQUEADO_PAGAMENTO_PENDENTE
        permitido = False
        risco = RiscoPedido.BLOQUEADO
        motivo = "Pagamento pendente"

    return DecisaoCozinha(
        permitido=permitido,
        codigo_decisao=codigo,
        justificativa=motivo,
        confirmacao_exigida=not permitido,
        risco=risco,
        politica_aplicada="cozinha.v1",
        versao_politica="1",
        decidido_em=instante,
        metadados={"pedido_id": pedido_id, "pagamentos": len(rows)},
    )
