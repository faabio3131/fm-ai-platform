"""Escrita governada do alcance máximo de entrega por unidade."""
from collections.abc import Callable

from sqlalchemy.orm import Session

from core.delivery.alcance_rota import AlcanceEntrega
from infra.delivery.alcance_sqlalchemy import configurar_alcance
from infra.transacoes.uow import UnitOfWorkV1


def alterar_alcance_da_unidade(*, tenant_id: str, unidade_id: str, limite_km: int, session_factory: Callable[[], Session]) -> AlcanceEntrega:
    politica = AlcanceEntrega(tenant_id=tenant_id, unidade_id=unidade_id, limite_km=limite_km)
    with UnitOfWorkV1(session_factory) as uow:
        if uow.session is None:
            raise RuntimeError("uow_alcance_entrega_indisponivel")
        resultado = configurar_alcance(uow.session, politica)
        uow.commit()
        return resultado
