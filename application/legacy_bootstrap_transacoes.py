"""Fronteira transacional da inicialização legada do app."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from infra.legacy_product_scope import (
    contar_insumos_legados,
    inserir_insumo_legado,
)
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


class AplicacaoLegacyBootstrapV1:
    """Inicialização legada sob uma única fronteira transacional."""

    def __init__(
        self,
        session_factory: SessionFactory,
        configuracao_model: type[Any],
    ) -> None:
        self._session_factory = session_factory
        self._configuracao_model = (
            configuracao_model
        )

    def executar(
        self,
        contexto: ContextoExecucao,
        *,
        habilitar_gateway_teste: bool,
        agora: datetime,
    ) -> bool:
        with UnitOfWorkV1(
            self._session_factory
        ) as uow:
            session = _session_ativa(uow)

            alterado = False

            if (
                habilitar_gateway_teste
                and session.query(
                    self._configuracao_model
                ).count()
                == 0
            ):
                session.add(
                    self._configuracao_model(
                        gateway_provider=(
                            "Mercado Pago"
                        )
                    )
                )
                alterado = True

            if (
                contar_insumos_legados(
                    session,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                )
                == 0
            ):
                insumos_padrao = (
                    {
                        "nome":
                            "Hambúrguer 180g Angus",
                        "unidade_medida":
                            "un",
                        "saldo_atual":
                            500.0,
                        "estoque_minimo":
                            50.0,
                        "custo_unitario":
                            6.50,
                        "data_validade":
                            agora
                            + timedelta(
                                days=90
                            ),
                    },
                    {
                        "nome":
                            "Queijo Provolone / Cheddar",
                        "unidade_medida":
                            "fatias",
                        "saldo_atual":
                            400.0,
                        "estoque_minimo":
                            60.0,
                        "custo_unitario":
                            1.20,
                        "data_validade":
                            agora
                            + timedelta(
                                days=30
                            ),
                    },
                    {
                        "nome":
                            "Pão Brioche Artesanal",
                        "unidade_medida":
                            "un",
                        "saldo_atual":
                            120.0,
                        "estoque_minimo":
                            50.0,
                        "custo_unitario":
                            2.00,
                        "data_validade":
                            agora
                            + timedelta(
                                days=5
                            ),
                        "dias_alerta_vencimento":
                            3,
                    },
                )

                for valores in insumos_padrao:
                    inserir_insumo_legado(
                        session,
                        tenant_id=contexto.tenant_id,
                        unidade_id=contexto.unidade_id,
                        valores=dict(valores),
                    )

                alterado = True

            if alterado:
                uow.commit()

            return alterado
