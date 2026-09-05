"""Fronteiras transacionais dos writes canônicos do KDS V1.

As UIs trabalham com sessões de leitura. Roteamento e transições de produção
possuem sua própria fronteira Application + UnitOfWorkV1.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from decimal import Decimal

from sqlalchemy.orm import Session

from application.assistente_operational_notifications import (
    notificar_status_assistente_best_effort,
)
from application.entrega_kds_handoff import HandoffEntregaKDSV1
from application.impressao_kds import IntegracaoImpressaoKDSV1
from application.kds_runtime import (
    ResultadoKDSCanonico,
    ServicoKDSCanonico,
)
from core.dominio.enums import PedidoStatus
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1

logger = logging.getLogger(__name__)


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


def _enfileirar_impressao_best_effort(
    *,
    integracao: IntegracaoImpressaoKDSV1 | None,
    contexto: ContextoExecucao,
    resultado: ResultadoKDSCanonico,
    idempotency_key: str,
) -> None:
    if integracao is None:
        return
    try:
        integracao.enfileirar_roteamento(
            contexto=contexto,
            producao=resultado.item,
            idempotency_key=idempotency_key,
        )
    except Exception:
        logger.exception(
            "falha_impressao_kds_best_effort",
            extra={
                "tenant_id": contexto.tenant_id,
                "unidade_id": contexto.unidade_id,
                "producao_id": resultado.item.producao_id,
            },
        )


def _notificar_entrega_pedido_pronto_best_effort(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    resultado: ResultadoKDSCanonico,
) -> None:
    if resultado.pedido_status is not PedidoStatus.PRONTO:
        return
    try:
        HandoffEntregaKDSV1(session_factory).notificar_pedido_pronto(
            contexto=contexto,
            pedido_id=resultado.item.pedido_id,
        )
    except Exception:
        # O Pedido/KDS já foi commitado. Logística é uma continuação
        # retriável e nunca pode reabrir/rollbackar a transação autoritativa.
        logger.exception(
            "falha_handoff_entrega_kds_best_effort",
            extra={
                "tenant_id": contexto.tenant_id,
                "unidade_id": contexto.unidade_id,
                "pedido_id": resultado.item.pedido_id,
                "producao_id": resultado.item.producao_id,
            },
        )


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
    integracao_impressao: IntegracaoImpressaoKDSV1 | None = None,
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

    _enfileirar_impressao_best_effort(
        integracao=integracao_impressao,
        contexto=contexto,
        resultado=resultado,
        idempotency_key=idempotency_key,
    )
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

    _notificar_entrega_pedido_pronto_best_effort(
        session_factory=session_factory,
        contexto=contexto,
        resultado=resultado,
    )
    notificar_status_assistente_best_effort(
        session_factory=session_factory,
        contexto=contexto,
        pedido_id=resultado.item.pedido_id,
    )
    return resultado
