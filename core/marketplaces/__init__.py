"""Framework de adapters de marketplace — PR17."""

from .adapters import MarketplaceAdapter, RegistroAdaptersMarketplace
from .erros import (
    ErroMarketplace,
    ErroMarketplacePermanente,
    ErroMarketplaceTransitorio,
)
from .flags import marketplace_v1_enabled
from .ifood_sandbox import IfoodSandboxAdapter, IfoodSandboxTransport
from .modelos import (
    CapacidadeMarketplace,
    CapacidadesMarketplace,
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    PedidoExterno,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    ResultadoReconciliacao,
    ResultadoSincronizacao,
    StatusPedidoExterno,
)
from .servicos import ServicoMarketplaces

__all__ = [
    "CapacidadeMarketplace",
    "CapacidadesMarketplace",
    "ErroMarketplace",
    "ErroMarketplacePermanente",
    "ErroMarketplaceTransitorio",
    "EventoMarketplaceExterno",
    "IfoodSandboxAdapter",
    "IfoodSandboxTransport",
    "IntegracaoMarketplace",
    "MarketplaceAdapter",
    "PedidoExterno",
    "PedidoMarketplaceSnapshot",
    "PlataformaMarketplace",
    "RegistroAdaptersMarketplace",
    "ResultadoReconciliacao",
    "ResultadoSincronizacao",
    "ServicoMarketplaces",
    "StatusPedidoExterno",
    "marketplace_v1_enabled",
]
