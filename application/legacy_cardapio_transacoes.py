"""Fronteira transacional do Cardápio/Ficha Técnica legado."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from infra.legacy_product_scope import (
    inserir_ficha_tecnica_legada,
    inserir_produto_legado,
)
from infra.transacoes.uow import UnitOfWorkV1

T = TypeVar("T")

SessionFactory = Callable[[], Session]


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")

    return uow.session


class AplicacaoLegacyCardapioV1:
    """Write boundary autoritativo para produto/ficha técnica legados."""

    def __init__(
        self,
        session_factory: SessionFactory,
    ) -> None:
        self._session_factory = session_factory

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

    def salvar_prato_com_ficha(
        self,
        contexto: ContextoExecucao,
        *,
        valores_produto: Mapping[str, Any],
        itens_ficha: Sequence[
            Mapping[str, Any]
        ],
    ) -> int:
        def acao(
            session: Session,
        ) -> int:
            produto_id = inserir_produto_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                valores=dict(
                    valores_produto
                ),
            )

            for item in itens_ficha:
                inserir_ficha_tecnica_legada(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    produto_id=produto_id,
                    insumo_id=int(
                        item["insumo_id"]
                    ),
                    quantidade=item[
                        "quantidade"
                    ],
                )

            return produto_id

        return self._executar(acao)

    def importar_produtos(
        self,
        contexto: ContextoExecucao,
        *,
        produtos: Sequence[
            Mapping[str, Any]
        ],
    ) -> int:
        def acao(
            session: Session,
        ) -> int:
            total = 0

            for valores in produtos:
                inserir_produto_legado(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    valores=dict(valores),
                )

                total += 1

            return total

        return self._executar(acao)
