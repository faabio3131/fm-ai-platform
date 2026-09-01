"""Schema autoritativo adicional usado somente pelo banco efêmero KDS E2E."""

from core.estoque.modelos_orm import StockBase
from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import CoreRuntimeBase
from infra.seguranca.modelos_orm import SecurityBase


def preparar(engine) -> None:
    StockBase.metadata.create_all(engine, checkfirst=True)
    EventBusBase.metadata.create_all(engine, checkfirst=True)
    CoreRuntimeBase.metadata.create_all(engine, checkfirst=True)
    SecurityBase.metadata.create_all(engine, checkfirst=True)
