"""Handoff pós-commit do KDS para a logística canônica de Entrega V1."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from core.entrega import (
    Entrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


class HandoffEntregaKDSV1:
    """Promove a Entrega após Pedido PRONTO sem compartilhar a UoW do KDS."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def notificar_pedido_pronto(
        self,
        *,
        contexto: ContextoExecucao,
        pedido_id: str,
    ) -> Entrega | None:
        pedido = pedido_id.strip()
        if not pedido:
            raise ValueError("pedido_id obrigatorio")

        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)
            repositorio = RepositorioEntregaSQLAlchemy(session)
            entrega = repositorio.buscar_por_pedido(
                contexto.tenant_id,
                contexto.unidade_id,
                pedido,
            )
            # Pedidos de retirada/salão podem não possuir Entrega canônica.
            if entrega is None:
                return None
            # Replay pós-commit: se a produção já foi registrada como pronta,
            # nenhuma versão/evento adicional deve ser criado.
            if entrega.producao_pronta_em is not None:
                return entrega

            contexto_sistema = ContextoExecucao.sistema(
                identidade="kds-entrega-handoff-v1",
                motivo="promover entrega após Pedido PRONTO autoritativo do KDS",
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                correlation_id=contexto.correlation_id,
                solicitado_em=contexto.solicitado_em,
            )
            servico = ServicoEntrega(
                repositorio,
                financeiro_resolvido=(
                    lambda tenant_id, unidade_id, pedido_ref:
                    financeiro_resolvido_sqlalchemy(
                        session,
                        tenant_id,
                        unidade_id,
                        pedido_ref,
                    )
                ),
                pedido_cancelado=(
                    lambda tenant_id, unidade_id, pedido_ref:
                    pedido_cancelado_sqlalchemy(
                        session,
                        tenant_id,
                        unidade_id,
                        pedido_ref,
                    )
                ),
            )
            resultado = servico.marcar_pedido_pronto(
                entrega.entrega_id,
                versao_esperada=entrega.versao,
                contexto=contexto_sistema,
                idempotency_key=f"kds:entrega:pedido-pronto:{pedido}",
            )
            uow.commit()
            return resultado
