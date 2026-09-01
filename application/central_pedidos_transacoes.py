"""Fronteira transacional dos comandos da Central de Pedidos V1."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlalchemy.orm import Session

from core.central_pedidos.servicos import (
    ResultadoComandoCentral,
    ServicoComandosCentral,
)
from core.estados.maquinas import ErroTransicao
from core.seguranca.contexto import ContextoExecucao
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


class AplicacaoCentralPedidosTransacoesV1:
    """Write boundary autoritativo da Central de Pedidos."""

    def __init__(
        self,
        session_factory: SessionFactory,
    ) -> None:
        self._session_factory = (
            session_factory
        )

    def transicionar(
        self,
        *,
        contexto: ContextoExecucao,
        pedido_id: str,
        destino: str,
        versao_esperada: int,
        idempotency_key: str,
        precondicoes: (
            Mapping[str, bool] | None
        ) = None,
        motivo: str | None = None,
        metadata: (
            Mapping[str, object] | None
        ) = None,
    ) -> ResultadoComandoCentral:
        erro_transicao: (
            ErroTransicao | None
        ) = None

        resultado: (
            ResultadoComandoCentral | None
        ) = None

        with UnitOfWorkV1(
            self._session_factory
        ) as uow:
            session = _session_ativa(
                uow
            )

            try:
                resultado = (
                    ServicoComandosCentral(
                        session
                    ).transicionar(
                        contexto=contexto,
                        pedido_id=pedido_id,
                        destino=destino,
                        versao_esperada=(
                            versao_esperada
                        ),
                        idempotency_key=(
                            idempotency_key
                        ),
                        precondicoes=(
                            precondicoes
                        ),
                        motivo=motivo,
                        metadata=metadata,
                    )
                )
            except ErroTransicao as exc:
                # A negativa pode produzir trilha
                # autoritativa de auditoria.
                erro_transicao = exc

            # Sucesso e negativa de domínio compartilham
            # exatamente um owner transacional.
            uow.commit()

        if erro_transicao is not None:
            raise erro_transicao

        if resultado is None:
            raise RuntimeError(
                "resultado_central_ausente"
            )

        return resultado
