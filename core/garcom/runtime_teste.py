"""Helpers exclusivos do runtime de teste da interface do garçom V1."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.kds.modelos_orm import KDSBase
from core.pagamentos.modelos_orm import PaymentsBase
from core.pedidos.modelos_orm import OrdersBase
from core.salao.modelos_orm import SalaoBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

from .flags import garcom_v1_enabled


def preparar_schema_teste(engine: Any) -> None:
    if not garcom_v1_enabled():
        raise RuntimeError("Schema Garcom V1 so pode ser preparado em teste isolado")
    OrdersBase.metadata.create_all(engine, checkfirst=True)
    PaymentsBase.metadata.create_all(engine, checkfirst=True)
    SalaoBase.metadata.create_all(engine, checkfirst=True)
    KDSBase.metadata.create_all(engine, checkfirst=True)


def contexto_garcom_teste(
    *,
    correlation_id: str,
    solicitado_em: datetime,
    papel: str = "garcom",
    usuario_id: str | None = None,
    tenant_id: str = "tenant-e2e",
    unidade_id: str = "unidade-e2e",
) -> ContextoExecucao:
    if not garcom_v1_enabled():
        raise RuntimeError("Contexto Garcom E2E indisponivel")
    papel_efetivo = Papel(papel)
    return ContextoExecucao(
        tenant_id,
        unidade_id,
        usuario_id or f"{papel}-e2e",
        frozenset({papel_efetivo}),
        MATRIZ_PADRAO[papel_efetivo],
        correlation_id,
        solicitado_em,
        "garcom-e2e",
        unidades_permitidas=frozenset({unidade_id}),
    )
