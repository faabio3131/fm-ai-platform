"""Fronteira transacional session-aware do Gerente IA para a Web V1.

Não autentica novamente nem recria regras do domínio: recebe o ContextoExecucao já
resolvido pela sessão assinada e delega ao runtime/canonical Core existente.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from application.gerente_ia_runtime import compor_runtime_gerente_ia
from core.gerente_ia.modelos import ChamadaTool
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.transacoes.uow import UnitOfWorkV1


class AplicacaoGerenteIAWebV1:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._secret_store = secret_store

    @staticmethod
    def _session(uow: UnitOfWorkV1) -> Session:
        if uow.session is None:
            raise RuntimeError("UnitOfWorkV1 sem Session ativa")
        return uow.session

    def executar_tool(
        self,
        *,
        contexto: ContextoExecucao,
        chamada: ChamadaTool,
    ) -> Any:
        with UnitOfWorkV1(self._session_factory) as uow:
            runtime = compor_runtime_gerente_ia(
                session=self._session(uow),
                secret_store=self._secret_store,
            )
            resultado = runtime.executar_tool(contexto=contexto, chamada=chamada)
            uow.commit()
            return resultado

    def perguntar(
        self,
        *,
        contexto: ContextoExecucao,
        pergunta: str,
    ) -> tuple[Any, ChamadaTool, Any]:
        with UnitOfWorkV1(self._session_factory) as uow:
            runtime = compor_runtime_gerente_ia(
                session=self._session(uow),
                secret_store=self._secret_store,
            )
            identidade, chamada, resultado = runtime.perguntar(
                contexto=contexto,
                pergunta=pergunta,
            )
            uow.commit()
            return identidade, chamada, resultado

    def confirmar_acao(
        self,
        *,
        contexto: ContextoExecucao,
        preview_id: str,
        fingerprint: str,
        idempotency_key: str,
    ) -> Any:
        with UnitOfWorkV1(self._session_factory) as uow:
            runtime = compor_runtime_gerente_ia(
                session=self._session(uow),
                secret_store=self._secret_store,
            )
            resultado = runtime.confirmar_acao(
                contexto=contexto,
                preview_id=preview_id,
                fingerprint=fingerprint,
                idempotency_key=idempotency_key,
            )
            uow.commit()
            return resultado
