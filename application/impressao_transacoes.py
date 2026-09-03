"""Fronteira transacional comercial da Impressão Operacional V1.

O spool é persistido sob Application + UnitOfWorkV1. O adapter físico é uma
porta injetada: esta camada não conhece Fake, driver, rede ou spool do SO.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy.orm import Session

from core.impressao import (
    DestinoImpressao,
    JobImpressao,
    PortaImpressora,
    RepositorioSpoolSQLAlchemy,
    ResultadoProcessamento,
    ServicoSpoolImpressao,
)
from core.seguranca import ContextoExecucao
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")
SessionFactory = Callable[[], Session]


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


class AplicacaoImpressaoV1:
    """Executa writes do spool sob uma única autoridade transacional."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        impressora: PortaImpressora,
        destinos: tuple[DestinoImpressao, ...],
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._impressora = impressora
        self._destinos = destinos
        self._agora = agora or _agora_utc

    def _servico(self, session: Session) -> ServicoSpoolImpressao:
        return ServicoSpoolImpressao(
            repositorio=RepositorioSpoolSQLAlchemy(session),
            impressora=self._impressora,
            auditoria=RepositorioAuditoriaSQLAlchemy(session),
            destinos=self._destinos,
        )

    def _executar(self, acao: Callable[[ServicoSpoolImpressao], T]) -> T:
        with UnitOfWorkV1(self._session_factory) as uow:
            servico = self._servico(_session_ativa(uow))
            resultado = acao(servico)
            uow.commit()
            return resultado

    def processar(
        self,
        *,
        contexto: ContextoExecucao,
        job_id: str,
        timestamp: datetime | None = None,
    ) -> ResultadoProcessamento:
        instante = timestamp or self._agora()
        return self._executar(
            lambda servico: servico.processar(
                contexto=contexto,
                job_id=job_id,
                timestamp=instante,
            )
        )

    def reimprimir(
        self,
        *,
        contexto: ContextoExecucao,
        job_id: str,
        motivo: str,
        idempotency_key: str,
        timestamp: datetime | None = None,
    ) -> JobImpressao:
        instante = timestamp or self._agora()
        return self._executar(
            lambda servico: servico.reimprimir(
                contexto=contexto,
                job_id=job_id,
                motivo=motivo,
                idempotency_key=idempotency_key,
                timestamp=instante,
            )[0]
        )
