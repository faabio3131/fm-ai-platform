"""Central de Pedidos V1: leitura derivada e comandos normativos."""

from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria

from .adaptador_sqlalchemy import CentralPedidosSQLAlchemy
from .flags import order_center_v1_enabled
from .modelos import *


def preparar_schema_teste(engine) -> None:
    """Cria schema efemero completo somente no E2E isolado da Central."""
    if not order_center_v1_enabled():
        raise RuntimeError("Schema da Central so pode ser preparado em teste isolado")
    from core.pagamentos.modelos_orm import PaymentsBase
    from core.pdv.modelos_orm import PDVBase
    from core.pedidos.modelos_orm import OrdersBase
    from infra.eventos.modelos_orm import EventBusBase
    from infra.seguranca.modelos_orm import SecurityBase

    OrdersBase.metadata.create_all(engine, checkfirst=True)
    PaymentsBase.metadata.create_all(engine, checkfirst=True)
    PDVBase.metadata.create_all(engine, checkfirst=True)
    EventBusBase.metadata.create_all(engine, checkfirst=True)
    SecurityBase.metadata.create_all(engine, checkfirst=True)


def contexto_central_teste(
    *, correlation_id: str, solicitado_em, papel: str = "administrador"
):
    """Contexto fixo apenas para o banco isolado do E2E, nunca para producao."""
    if not order_center_v1_enabled():
        raise RuntimeError("Contexto E2E indisponivel")
    from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

    papel_efetivo = Papel(papel)
    return ContextoExecucao(
        "tenant-e2e",
        "unidade-e2e",
        "admin-e2e",
        frozenset({papel_efetivo}),
        MATRIZ_PADRAO[papel_efetivo],
        correlation_id,
        solicitado_em,
        "streamlit-e2e",
        unidades_permitidas=frozenset({"unidade-e2e"}),
    )


__all__ = [
    "CentralPedidosSQLAlchemy",
    "RepositorioAuditoriaEmMemoria",
    "contexto_central_teste",
    "order_center_v1_enabled",
    "preparar_schema_teste",
]
