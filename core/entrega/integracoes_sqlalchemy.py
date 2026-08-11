"""Leituras autoritativas usadas pela PR13 sem assumir autoridade financeira."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM


def financeiro_resolvido_sqlalchemy(
    session: Session, tenant_id: str, unidade_id: str, pedido_id: str
) -> bool:
    """Confere critério financeiro sem criar/confirmar pagamento.

    Todos os pagamentos existentes do pedido precisam estar pagos ou ter
    recebimento posterior explicitamente autorizado. Ausência de obrigação
    financeira não é interpretada como autorização implícita.
    """
    rows = session.scalars(
        select(PagamentoORM).where(
            PagamentoORM.tenant_id == tenant_id,
            PagamentoORM.unidade_id == unidade_id,
            PagamentoORM.pedido_id == pedido_id,
        )
    ).all()
    if not rows:
        return False
    return all(row.status == "pago" or row.recebimento_posterior for row in rows)


def pedido_cancelado_sqlalchemy(
    session: Session, tenant_id: str, unidade_id: str, pedido_id: str
) -> bool:
    status = session.scalar(
        select(PedidoORM.status).where(
            PedidoORM.tenant_id == tenant_id,
            PedidoORM.unidade_id == unidade_id,
            PedidoORM.id == pedido_id,
        )
    )
    return status == "cancelado"
