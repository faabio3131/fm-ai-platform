"""KDS V1 por setor."""

from datetime import datetime

from core.seguranca import ContextoExecucao, MATRIZ_PADRAO, Papel
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria

from .adaptador_sqlalchemy import RepositorioKDSSQLAlchemy
from .erros import ErroKDS
from .flags import kds_v1_enabled
from .modelos import (
    EstadoSLA,
    FilaKDS,
    IndicadorSLA,
    ItemFilaKDS,
    ProducaoItem,
    SetorProducao,
)
from .modelos_orm import KDSBase
from .observabilidade import ColetorMetricasKDS
from .servicos import (
    CacheFilaKDS,
    ConfiguracaoSLAKDS,
    ResultadoComandoKDS,
    ServicoKDS,
    calcular_sla,
)


def preparar_schema_teste(engine) -> None:
    """Cria schema KDS/Pedido somente no runtime E2E isolado."""
    if not kds_v1_enabled():
        raise RuntimeError("Schema KDS so pode ser preparado em teste isolado")
    from core.pedidos.modelos_orm import OrdersBase

    OrdersBase.metadata.create_all(engine, checkfirst=True)
    KDSBase.metadata.create_all(engine, checkfirst=True)


def contexto_kds_teste(
    *, correlation_id: str, solicitado_em: datetime, papel: str = "administrador"
) -> ContextoExecucao:
    if not kds_v1_enabled():
        raise RuntimeError("Contexto KDS E2E indisponivel")
    papel_efetivo = Papel(papel)
    return ContextoExecucao(
        "tenant-e2e",
        "unidade-e2e",
        f"{papel}-e2e",
        frozenset({papel_efetivo}),
        MATRIZ_PADRAO[papel_efetivo],
        correlation_id,
        solicitado_em,
        "kds-e2e",
        unidades_permitidas=frozenset({"unidade-e2e"}),
    )


__all__ = [
    "CacheFilaKDS",
    "ColetorMetricasKDS",
    "ConfiguracaoSLAKDS",
    "ErroKDS",
    "EstadoSLA",
    "FilaKDS",
    "IndicadorSLA",
    "ItemFilaKDS",
    "KDSBase",
    "ProducaoItem",
    "RepositorioAuditoriaEmMemoria",
    "RepositorioKDSSQLAlchemy",
    "ResultadoComandoKDS",
    "ServicoKDS",
    "SetorProducao",
    "calcular_sla",
    "contexto_kds_teste",
    "kds_v1_enabled",
    "preparar_schema_teste",
]
