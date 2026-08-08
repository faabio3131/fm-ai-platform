"""Central de Pedidos V1: leitura derivada e comandos normativos."""

from .adaptador_sqlalchemy import CentralPedidosSQLAlchemy
from .flags import order_center_v1_enabled
from .modelos import *  # noqa: F403
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria


def preparar_schema_teste(engine) -> None:
    """Cria apenas schema efemero quando a flag server-side de teste esta ativa."""
    if not order_center_v1_enabled():
        raise RuntimeError("Schema da Central so pode ser preparado em teste isolado")
    from core.pagamentos.modelos_orm import PaymentsBase
    from core.pdv.modelos_orm import PDVBase
    from core.pedidos.modelos_orm import OrdersBase

    OrdersBase.metadata.create_all(engine, checkfirst=True)
    PaymentsBase.metadata.create_all(engine, checkfirst=True)
    PDVBase.metadata.create_all(engine, checkfirst=True)


def contexto_central_teste(
    *, correlation_id: str, solicitado_em, papel: str = "administrador"
):
    """Contexto fixo apenas para o banco isolado do E2E, nunca para producao."""
    if not order_center_v1_enabled():
        raise RuntimeError("Contexto E2E indisponivel")
    from core.seguranca import ContextoExecucao, MATRIZ_PADRAO, Papel

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
    "order_center_v1_enabled",
    "preparar_schema_teste",
    "contexto_central_teste",
    "RepositorioAuditoriaEmMemoria",
]
