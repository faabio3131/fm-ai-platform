"""Fronteira transacional do Estoque legado."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from infra.legacy_product_scope import (
    atualizar_insumo_legado,
    excluir_insumo_legado,
    inserir_insumo_legado,
    obter_insumo_por_nome_legado,
)
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


class AplicacaoLegacyEstoqueV1:
    """Write boundary autoritativo para o estoque legado."""

    def __init__(
        self,
        session_factory: SessionFactory,
    ) -> None:
        self._session_factory = (
            session_factory
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

    def excluir_insumo(
        self,
        contexto: ContextoExecucao,
        *,
        insumo_id: int,
    ) -> None:
        def acao(
            session: Session,
        ) -> None:
            excluir_insumo_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                insumo_id=insumo_id,
            )

        self._executar(acao)

    def salvar_insumo(
        self,
        contexto: ContextoExecucao,
        *,
        valores: Mapping[str, Any],
    ) -> int:
        def acao(
            session: Session,
        ) -> int:
            return inserir_insumo_legado(
                session,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                valores=dict(valores),
            )

        return self._executar(acao)

    def aplicar_lote_leitura(
        self,
        contexto: ContextoExecucao,
        *,
        itens: Sequence[
            Mapping[str, Any]
        ],
    ) -> int:
        def acao(
            session: Session,
        ) -> int:
            total = 0

            for item in itens:
                nome = str(
                    item.get(
                        "nome",
                        "",
                    )
                ).strip()

                quantidade = float(
                    item.get(
                        "quantidade",
                        0.0,
                    )
                )

                if (
                    not nome
                    or quantidade <= 0
                ):
                    continue

                atual = (
                    obter_insumo_por_nome_legado(
                        session,
                        tenant_id=contexto.tenant_id,
                        unidade_id=contexto.unidade_id,
                        nome=nome,
                    )
                )

                data_validade = item.get(
                    "data_validade"
                )

                if atual:
                    valores = {
                        "saldo_atual": (
                            float(
                                atual.saldo_atual
                                or 0
                            )
                            + quantidade
                        ),
                    }

                    if data_validade:
                        valores[
                            "data_validade"
                        ] = data_validade

                    atualizar_insumo_legado(
                        session,
                        tenant_id=contexto.tenant_id,
                        unidade_id=contexto.unidade_id,
                        insumo_id=int(
                            atual.id
                        ),
                        valores=valores,
                    )
                else:
                    inserir_insumo_legado(
                        session,
                        tenant_id=contexto.tenant_id,
                        unidade_id=contexto.unidade_id,
                        valores={
                            "nome":
                                nome,
                            "unidade_medida":
                                item.get(
                                    "unidade",
                                    "un",
                                ),
                            "saldo_atual":
                                quantidade,
                            "estoque_minimo":
                                quantidade
                                * 0.15,
                            "data_validade":
                                data_validade,
                            "dias_alerta_vencimento":
                                15,
                        },
                    )

                total += 1

            return total

        return self._executar(acao)
