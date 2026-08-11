"""Helpers exclusivos do runtime de teste da PR11."""

from datetime import datetime
from typing import Any

from core.pedidos.modelos_orm import OrdersBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

from .flags import salao_v1_enabled
from .modelos_orm import SalaoBase


def preparar_schema_teste(engine: Any) -> None:
    if not salao_v1_enabled():
        raise RuntimeError("Schema Salao V1 so pode ser preparado em teste isolado")
    OrdersBase.metadata.create_all(engine, checkfirst=True)
    SalaoBase.metadata.create_all(engine, checkfirst=True)


def contexto_salao_teste(
    *, correlation_id: str, solicitado_em: datetime, papel: str = "gerente"
) -> ContextoExecucao:
    if not salao_v1_enabled():
        raise RuntimeError("Contexto Salao E2E indisponivel")
    papel_efetivo = Papel(papel)
    return ContextoExecucao(
        "tenant-e2e",
        "unidade-e2e",
        f"{papel}-e2e",
        frozenset({papel_efetivo}),
        MATRIZ_PADRAO[papel_efetivo],
        correlation_id,
        solicitado_em,
        "salao-e2e",
        unidades_permitidas=frozenset({"unidade-e2e"}),
    )
