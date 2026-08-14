"""Configuração multi-tenant de serviços externos da V1."""

from .catalogo import CATALOGO_V1, CatalogoServicosExternos, EspecificacaoServico
from .google_maps import (
    ConfiguracaoGoogleMaps,
    Coordenada,
    ErroGoogleMaps,
    ErroGoogleMapsTransitorio,
    GoogleMapsAdapter,
    RespostaHTTPMaps,
    ResultadoGeocodificacao,
    ResultadoRota,
)
from .modelos import (
    AmbienteIntegracao,
    ConfiguracaoServicoExterno,
    ErroConfiguracaoServico,
    EstadoProntidaoServico,
    ProntidaoServicoExterno,
)
from .provedores import (
    ConfiguracaoGeminiTenant,
    ConfiguracaoMercadoPago,
    ConfiguracaoMeta,
    ErroProvedorExterno,
    ErroProvedorTransitorio,
    GeminiTenantAdapter,
    MercadoPagoAdapter,
    MetaAdapter,
)
from .servicos import ServicoConfiguracoesExternas

__all__ = [
    "CATALOGO_V1",
    "AmbienteIntegracao",
    "CatalogoServicosExternos",
    "ConfiguracaoGeminiTenant",
    "ConfiguracaoGoogleMaps",
    "ConfiguracaoMercadoPago",
    "ConfiguracaoMeta",
    "ConfiguracaoServicoExterno",
    "Coordenada",
    "ErroConfiguracaoServico",
    "ErroGoogleMaps",
    "ErroGoogleMapsTransitorio",
    "ErroProvedorExterno",
    "ErroProvedorTransitorio",
    "EspecificacaoServico",
    "EstadoProntidaoServico",
    "GeminiTenantAdapter",
    "GoogleMapsAdapter",
    "MercadoPagoAdapter",
    "MetaAdapter",
    "ProntidaoServicoExterno",
    "RespostaHTTPMaps",
    "ResultadoGeocodificacao",
    "ResultadoRota",
    "ServicoConfiguracoesExternas",
]
