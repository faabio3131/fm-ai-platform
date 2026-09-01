"""Fronteira transacional do gateway legado exclusivo de teste/E2E."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")

SessionFactory = Callable[[], Session]


def _session_ativa(
    uow: UnitOfWorkV1,
) -> Session:
    if uow.session is None:
        raise RuntimeError(
            "UnitOfWorkV1 sem Session ativa"
        )

    return uow.session


class AplicacaoLegacyGatewayTesteV1:
    """Write boundary do formulário legado de gateway usado somente em E2E."""

    def __init__(
        self,
        session_factory: SessionFactory,
        configuracao_model: type[Any],
    ) -> None:
        self._session_factory = (
            session_factory
        )
        self._configuracao_model = (
            configuracao_model
        )

    def _executar(
        self,
        acao: Callable[[Session], T],
    ) -> T:
        with UnitOfWorkV1(
            self._session_factory
        ) as uow:
            session = _session_ativa(uow)

            resultado = acao(session)

            uow.commit()

            return resultado

    def salvar(
        self,
        *,
        provider: str,
        pix_key: str,
        api_key: str,
    ) -> None:
        provider_normalizado = (
            provider.strip()
        )

        if not provider_normalizado:
            raise ValueError(
                "provider_obrigatorio"
            )

        def acao(
            session: Session,
        ) -> None:
            configuracao = (
                session.query(
                    self._configuracao_model
                ).first()
            )

            if configuracao is None:
                configuracao = (
                    self._configuracao_model()
                )
                session.add(configuracao)

            configuracao.gateway_provider = (
                provider_normalizado
            )
            configuracao.gateway_pix_key = (
                pix_key
            )
            configuracao.gateway_api_key = (
                api_key
            )

        self._executar(acao)
