"""Fronteiras transacionais dos writes canônicos do KDS V1.

As UIs trabalham com sessões de leitura. Roteamento e transições de produção
possuem sua própria fronteira Application + UnitOfWorkV1.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from application.assistente_operational_notifications import (
    notificar_status_assistente_best_effort,
)
from application.kds_runtime import (
    ResultadoKDSCanonico,
    ServicoKDSCanonico,
)
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


def rotear_item_kds_v1(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    pedido_id: str,
    pedido_item_id: str,
    setor_id: str,
    quantidade: Decimal,
    idempotency_key: str,
    prioridade: int = 0,
    tentativa: int = 1,
    producao_id: str | None = None,
) -> ResultadoKDSCanonico:
    """Roteia um item sob ownership transacional da Application."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = ServicoKDSCanonico(
            _session_ativa(uow)
        ).rotear_item(
            contexto,
            pedido_id=pedido_id,
            pedido_item_id=pedido_item_id,
            setor_id=setor_id,
            quantidade=quantidade,
            idempotency_key=idempotency_key,
            prioridade=prioridade,
            tentativa=tentativa,
            producao_id=producao_id,
        )

        uow.commit()

    notificar_status_assistente_best_effort(
        session_factory=session_factory,
        contexto=contexto,
        pedido_id=resultado.item.pedido_id,
    )
    return resultado


def transicionar_kds_v1(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    producao_id: str,
    destino: str,
    versao_esperada: int,
    idempotency_key: str,
    precondicoes: dict[str, bool] | None = None,
    motivo: str | None = None,
) -> ResultadoKDSCanonico:
    """Transiciona produção sob ownership transacional da Application."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = ServicoKDSCanonico(
            _session_ativa(uow)
        ).transicionar(
            contexto,
            producao_id=producao_id,
            destino=destino,
            versao_esperada=versao_esperada,
            idempotency_key=idempotency_key,
            precondicoes=precondicoes,
            motivo=motivo,
        )

        uow.commit()

    notificar_status_assistente_best_effort(
        session_factory=session_factory,
        contexto=contexto,
        pedido_id=resultado.item.pedido_id,
    )
    return resultado
