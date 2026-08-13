"""Claim transacional para impedir dupla finalizacao concorrente."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from .modelos_orm import FinalizacaoPendentePDVORM

PENDENTE = "PENDENTE"
PROCESSANDO = "PROCESSANDO"
FINALIZADA = "FINALIZADA"


def adquirir(session: Session, row: FinalizacaoPendentePDVORM) -> bool:
    resultado = session.execute(
        update(FinalizacaoPendentePDVORM)
        .where(
            FinalizacaoPendentePDVORM.id == row.id,
            FinalizacaoPendentePDVORM.status == PENDENTE,
        )
        .values(status=PROCESSANDO)
    )
    adquirido = getattr(resultado, "rowcount", 0) == 1
    session.flush()
    session.refresh(row)
    return adquirido
