"""Fronteira transacional dos comandos da interface do Garçom V1."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy.orm import Session

from core.garcom import ServicoGarcom
from core.kds import RepositorioKDSSQLAlchemy
from core.salao import (
    Comanda,
    ParticipanteComanda,
    RepositorioSalaoSQLAlchemy,
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


class AplicacaoGarcomV1:
    """Executa writes do Garçom sob uma única autoridade transacional."""

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
        acao: Callable[[ServicoGarcom], T],
    ) -> T:
        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)

            servico = ServicoGarcom(
                RepositorioSalaoSQLAlchemy(session),
                RepositorioKDSSQLAlchemy(session),
                agora=self._agora,
            )

            resultado = acao(servico)

            uow.commit()

            return resultado

    def abrir_comanda(
        self,
        contexto: ContextoExecucao,
        *,
        mesa_id: str,
        expected_mesa_version: int,
        numero: str | None = None,
        comanda_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Comanda:
        return self._executar(
            lambda servico: servico.abrir_comanda(
                contexto,
                mesa_id=mesa_id,
                expected_mesa_version=expected_mesa_version,
                numero=numero,
                comanda_id=comanda_id,
                idempotency_key=idempotency_key,
            )
        )

    def adicionar_participante(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        apelido: str,
        expected_version: int,
        participante_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ParticipanteComanda:
        return self._executar(
            lambda servico: servico.adicionar_participante(
                contexto,
                comanda_id=comanda_id,
                apelido=apelido,
                expected_version=expected_version,
                participante_id=participante_id,
                idempotency_key=idempotency_key,
            )
        )

    def vincular_pedido(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        pedido_id: str,
        expected_version: int,
        participante_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Comanda:
        return self._executar(
            lambda servico: servico.vincular_pedido(
                contexto,
                comanda_id=comanda_id,
                pedido_id=pedido_id,
                expected_version=expected_version,
                participante_id=participante_id,
                idempotency_key=idempotency_key,
            )
        )

    def solicitar_conta(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> Comanda:
        return self._executar(
            lambda servico: servico.solicitar_conta(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        )

    def retomar_consumo(
        self,
        contexto: ContextoExecucao,
        *,
        comanda_id: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> Comanda:
        return self._executar(
            lambda servico: servico.retomar_consumo(
                contexto,
                comanda_id=comanda_id,
                expected_version=expected_version,
                idempotency_key=idempotency_key,
            )
        )
