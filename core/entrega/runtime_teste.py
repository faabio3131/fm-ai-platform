"""Runtime isolado e fail-closed da Expedição e Entrega V1."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.pagamentos.modelos_orm import PaymentsBase
from core.pedidos.modelos_orm import OrdersBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

from .flags import entrega_v1_enabled
from .modelos_orm import DeliveryBase


def preparar_schema_teste(engine: Any) -> None:
    if not entrega_v1_enabled():
        raise RuntimeError("Schema Entrega V1 so pode ser preparado em teste isolado")
    OrdersBase.metadata.create_all(engine, checkfirst=True)
    PaymentsBase.metadata.create_all(engine, checkfirst=True)
    DeliveryBase.metadata.create_all(engine, checkfirst=True)


def contexto_entrega_teste(
    *,
    correlation_id: str,
    solicitado_em: datetime,
    papel: str,
    usuario_id: str | None = None,
    tenant_id: str = "tenant-e2e",
    unidade_id: str = "unidade-e2e",
) -> ContextoExecucao:
    if not entrega_v1_enabled():
        raise RuntimeError("Contexto Entrega E2E indisponivel")
    papel_efetivo = Papel(papel)
    return ContextoExecucao(
        tenant_id,
        unidade_id,
        usuario_id or f"{papel}-e2e",
        frozenset({papel_efetivo}),
        MATRIZ_PADRAO[papel_efetivo],
        correlation_id,
        solicitado_em,
        "entrega-e2e",
        unidades_permitidas=frozenset({unidade_id}),
    )
