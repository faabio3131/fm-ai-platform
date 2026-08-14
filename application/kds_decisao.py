from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.decisoes import DecisaoCozinha
from core.dominio.enums import CodigoDecisaoCozinha, RiscoPedido
from core.pagamentos.modelos_orm import PagamentoORM


def decidir_cozinha(session: Session, tenant_id: str, unidade_id: str, pedido_id: str, instante: datetime) -> DecisaoCozinha:
    rows = session.scalars(select(PagamentoORM).where(PagamentoORM.tenant_id == tenant_id, PagamentoORM.unidade_id == unidade_id, PagamentoORM.pedido_id == pedido_id)).all()
    def valor(x):
        return Decimal(str(x or 0))
    pago = bool(rows) and all(p.status == "pago" and valor(p.valor_pago) - valor(p.valor_estornado) >= valor(p.valor_previsto) for p in rows)
    posterior = bool(rows) and all((p.status == "pago" and valor(p.valor_pago) - valor(p.valor_estornado) >= valor(p.valor_previsto)) or (p.recebimento_posterior and p.status == "pendente") for p in rows)
    if pago:
        codigo, permitido, risco, motivo = CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_CONFIRMADO, True, RiscoPedido.BAIXO, "Pagamento confirmado"
    elif posterior:
        codigo, permitido, risco, motivo = CodigoDecisaoCozinha.PERMITIDO_PAGAMENTO_POSTERIOR, True, RiscoPedido.MEDIO, "Recebimento posterior autorizado"
    else:
        codigo, permitido, risco, motivo = CodigoDecisaoCozinha.BLOQUEADO_PAGAMENTO_PENDENTE, False, RiscoPedido.BLOQUEADO, "Pagamento pendente"
    return DecisaoCozinha(permitido=permitido, codigo_decisao=codigo, justificativa=motivo, confirmacao_exigida=not permitido, risco=risco, politica_aplicada="cozinha.v1", versao_politica="1", decidido_em=instante, metadados={"pedido_id": pedido_id, "pagamentos": len(rows)})
