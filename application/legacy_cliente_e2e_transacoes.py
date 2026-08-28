"""Fronteira transacional do cadastro legado de cliente exclusivo de E2E."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


def _session_ativa(
    uow: UnitOfWorkV1,
) -> Session:
    if uow.session is None:
        raise RuntimeError(
            "UnitOfWorkV1 sem Session ativa"
        )

    return uow.session


class AplicacaoLegacyClienteE2EV1:
    """Write boundary do cadastro legado de cliente usado apenas em E2E."""

    def __init__(
        self,
        session_factory: SessionFactory,
        cliente_model: type[Any],
    ) -> None:
        self._session_factory = (
            session_factory
        )
        self._cliente_model = (
            cliente_model
        )

    def cadastrar(
        self,
        *,
        nome: str,
        whatsapp: str,
        email: str | None,
        documento_fiscal: str | None,
    ) -> bool:
        nome_normalizado = (
            nome.strip()
        )
        whatsapp_normalizado = (
            whatsapp.strip()
        )

        if not nome_normalizado:
            raise ValueError(
                "nome_obrigatorio"
            )

        if not whatsapp_normalizado:
            raise ValueError(
                "whatsapp_obrigatorio"
            )

        with UnitOfWorkV1(
            self._session_factory
        ) as uow:
            session = _session_ativa(uow)

            existente = (
                session.query(
                    self._cliente_model
                )
                .filter(
                    self._cliente_model.whatsapp
                    == whatsapp_normalizado
                )
                .first()
            )

            if existente is not None:
                return False

            session.add(
                self._cliente_model(
                    nome=nome_normalizado,
                    whatsapp=whatsapp_normalizado,
                    email=(
                        email.strip()
                        if email
                        else None
                    ),
                    documento_fiscal=(
                        documento_fiscal.strip()
                        if documento_fiscal
                        else None
                    ),
                    status="Ativo",
                    saldo_cashback=0.0,
                )
            )

            uow.commit()

            return True
