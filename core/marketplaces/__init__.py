"""Framework de adapters de marketplace — PR17/PR18."""

from .adapters import MarketplaceAdapter, RegistroAdaptersMarketplace
from .erros import (
    ErroMarketplace,
    ErroMarketplacePermanente,
    ErroMarketplaceTransitorio,
)
from .flags import (
    food99_adapter_v1_enabled,
    ifood_adapter_v1_enabled,
    keeta_adapter_v1_enabled,
    marketplace_v1_enabled,
)
from .food99_partner import FOOD99_CAPACIDADES_PUBLICAS, Food99PartnerAdapter
from .ifood_http import (
    CredencialIfood,
    IfoodHttpAdapter,
    PortaHttpMarketplace,
    PortaSegredosIfood,
    RespostaHttpMarketplace,
)
from .ifood_sandbox import IfoodSandboxAdapter, IfoodSandboxTransport
from .keeta_auth import (
    KEETA_CODIGOS_CANCELAMENTO,
    KEETA_CONTRATO,
    KEETA_MODOS_CANCELAMENTO,
    KEETA_OPEN_DELIVERY_BASE_URL,
    KEETA_TOKEN_URL,
    KEETA_VERSAO,
    CredencialKeeta,
    KeetaAuthOpenDelivery,
    PoliticaCancelamentoKeeta,
    PortaSegredosKeeta,
    gerar_assinatura_keeta,
)
from .keeta_partner import KEETA_CAPACIDADES_PUBLICAS, KeetaPartnerAdapter
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
from .opendelivery import (
    ConfiguracaoOpenDelivery,
    HttpxOpenDeliveryTransport,
    OpenDeliveryPartnerTransport,
    PortaAutenticacaoOpenDelivery,
    PortaHttpOpenDelivery,
    PortaPoliticaCancelamentoOpenDelivery,
    RespostaHttpOpenDelivery,
    RotasOpenDelivery,
)
from .partner_transport import TransporteParceiroNormalizado
from .runtime import (
    HttpxMarketplaceTransport,
    compor_adapters_marketplace_reais,
    compor_ifood_http_real,
    compor_keeta_opendelivery_real,
)
from .servicos import ServicoMarketplaces

__all__ = [
    "FOOD99_CAPACIDADES_PUBLICAS",
    "KEETA_CAPACIDADES_PUBLICAS",
    "KEETA_CODIGOS_CANCELAMENTO",
    "KEETA_CONTRATO",
    "KEETA_MODOS_CANCELAMENTO",
    "KEETA_OPEN_DELIVERY_BASE_URL",
    "KEETA_TOKEN_URL",
    "KEETA_VERSAO",
    "CapacidadeMarketplace",
    "CapacidadesMarketplace",
    "ConfiguracaoOpenDelivery",
    "CredencialIfood",
    "CredencialKeeta",
    "ErroMarketplace",
    "ErroMarketplacePermanente",
    "ErroMarketplaceTransitorio",
    "EventoMarketplaceExterno",
    "Food99PartnerAdapter",
    "HttpxMarketplaceTransport",
    "HttpxOpenDeliveryTransport",
    "IfoodHttpAdapter",
    "IfoodSandboxAdapter",
    "IfoodSandboxTransport",
    "IntegracaoMarketplace",
    "KeetaAuthOpenDelivery",
    "KeetaPartnerAdapter",
    "MarketplaceAdapter",
    "OpenDeliveryPartnerTransport",
    "PedidoExterno",
    "PedidoMarketplaceSnapshot",
    "PlataformaMarketplace",
    "PoliticaCancelamentoKeeta",
    "PortaAutenticacaoOpenDelivery",
    "PortaHttpMarketplace",
    "PortaHttpOpenDelivery",
    "PortaPoliticaCancelamentoOpenDelivery",
    "PortaSegredosIfood",
    "PortaSegredosKeeta",
    "RegistroAdaptersMarketplace",
    "RespostaHttpMarketplace",
    "RespostaHttpOpenDelivery",
    "ResultadoReconciliacao",
    "ResultadoSincronizacao",
    "RotasOpenDelivery",
    "ServicoMarketplaces",
    "StatusPedidoExterno",
    "TransporteParceiroNormalizado",
    "compor_adapters_marketplace_reais",
    "compor_ifood_http_real",
    "compor_keeta_opendelivery_real",
    "food99_adapter_v1_enabled",
    "gerar_assinatura_keeta",
    "ifood_adapter_v1_enabled",
    "keeta_adapter_v1_enabled",
    "marketplace_v1_enabled",
]
