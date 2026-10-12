"""Fronteira transacional do diagnóstico de IA, sem mutações comerciais."""
from __future__ import annotations

from infra.transacoes.uow import UnitOfWorkV1


def confirmar_auditoria_simulador(uow: UnitOfWorkV1) -> None:
    """Confirma somente os registros de auditoria e medição criados pelo Router."""
    uow.commit()
