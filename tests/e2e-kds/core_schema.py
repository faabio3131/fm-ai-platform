"""Schema autoritativo adicional usado somente pelo banco efêmero KDS E2E."""

from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import CoreRuntimeBase
from infra.seguranca.modelos_orm import SecurityBase


def preparar(engine) -> None:
    EventBusBase.metadata.create_all(engine, checkfirst=True)
    CoreRuntimeBase.metadata.create_all(engine, checkfirst=True)
    SecurityBase.metadata.create_all(engine, checkfirst=True)
