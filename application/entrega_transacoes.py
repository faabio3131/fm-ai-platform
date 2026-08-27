"""Fronteira transacional dos comandos de Expedição e Entrega V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy.orm import Session

from core.entrega import (
    ChecklistExpedicao,
    Entrega,
    ProvaEntrega,
    RepositorioEntregaSQLAlchemy,
    ServicoEntrega,
    financeiro_resolvido_sqlalchemy,
    pedido_cancelado_sqlalchemy,
)
from core.seguranca import ContextoExecucao
from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")

SessionFactory = Callable[[], Session]


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")

    return uow.session


def _servico(
    session: Session,
    *,
    agora: Callable[[], datetime],
) -> ServicoEntrega:
    return ServicoEntrega(
        RepositorioEntregaSQLAlchemy(session),
        financeiro_resolvido=(
            lambda tenant_id, unidade_id, pedido_id:
            financeiro_resolvido_sqlalchemy(
                session,
                tenant_id,
                unidade_id,
                pedido_id,
            )
        ),
        pedido_cancelado=(
            lambda tenant_id, unidade_id, pedido_id:
            pedido_cancelado_sqlalchemy(
                session,
                tenant_id,
                unidade_id,
                pedido_id,
            )
        ),
        agora=agora,
    )


class AplicacaoEntregaV1:
    """Executa writes de Entrega sob uma única autoridade transacional."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agora = agora or _agora_utc

    def _executar(
        self,
        acao: Callable[[ServicoEntrega], T],
    ) -> T:
        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)

            servico = _servico(
                session,
                agora=self._agora,
            )

            resultado = acao(servico)

            uow.commit()

            return resultado

    def concluir_checklist(
        self,
        entrega_id: str,
        checklist: ChecklistExpedicao,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        return self._executar(
            lambda servico: servico.concluir_checklist(
                entrega_id,
                checklist,
                versao_esperada=versao_esperada,
                contexto=contexto,
                idempotency_key=idempotency_key,
            )
        )

    def atribuir(
        self,
        entrega_id: str,
        entregador_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        return self._executar(
            lambda servico: servico.atribuir(
                entrega_id,
                entregador_id,
                versao_esperada=versao_esperada,
                contexto=contexto,
                idempotency_key=idempotency_key,
            )
        )

    def coletar(
        self,
        entrega_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        return self._executar(
            lambda servico: servico.coletar(
                entrega_id,
                versao_esperada=versao_esperada,
                contexto=contexto,
                idempotency_key=idempotency_key,
            )
        )

    def sair_em_rota(
        self,
        entrega_id: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        return self._executar(
            lambda servico: servico.sair_em_rota(
                entrega_id,
                versao_esperada=versao_esperada,
                contexto=contexto,
                idempotency_key=idempotency_key,
            )
        )

    def confirmar_entrega(
        self,
        entrega_id: str,
        prova: ProvaEntrega,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        return self._executar(
            lambda servico: servico.confirmar_entrega(
                entrega_id,
                prova,
                versao_esperada=versao_esperada,
                contexto=contexto,
                idempotency_key=idempotency_key,
            )
        )

    def registrar_tentativa_falha(
        self,
        entrega_id: str,
        motivo: str,
        *,
        versao_esperada: int,
        contexto: ContextoExecucao,
        idempotency_key: str,
    ) -> Entrega:
        return self._executar(
            lambda servico: servico.registrar_tentativa_falha(
                entrega_id,
                motivo,
                versao_esperada=versao_esperada,
                contexto=contexto,
                idempotency_key=idempotency_key,
            )
        )
