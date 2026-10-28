"""Adapters SQLAlchemy para configurações externas."""

from .fabrica_adapters import FabricaAdaptersExternos
from .modelos_orm import IntegrationConfigBase, ServicoExternoConfigORM
from .repositorio_sqlalchemy import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from .transportes import (
    GoogleGenAITenantGateway,
    OpenAIChatTenantGateway,
    RequestsGoogleMapsTransport,
    RequestsProviderTransport,
)

__all__ = [
    "FabricaAdaptersExternos",
    "GoogleGenAITenantGateway",
    "OpenAIChatTenantGateway",
    "IntegrationConfigBase",
    "ProntidaoCredenciaisSQLAlchemy",
    "RepositorioConfiguracoesExternasSQLAlchemy",
    "RequestsGoogleMapsTransport",
    "RequestsProviderTransport",
    "ServicoExternoConfigORM",
]
