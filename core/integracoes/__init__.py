"""Configuração multi-tenant de serviços externos da V1."""

from .catalogo import CATALOGO_V1, CatalogoServicosExternos, EspecificacaoServico
from .modelos import (
    AmbienteIntegracao,
    ConfiguracaoServicoExterno,
    ErroConfiguracaoServico,
    EstadoProntidaoServico,
    ProntidaoServicoExterno,
)
from .servicos import ServicoConfiguracoesExternas

__all__ = [
    "CATALOGO_V1",
    "AmbienteIntegracao",
    "CatalogoServicosExternos",
    "ConfiguracaoServicoExterno",
    "ErroConfiguracaoServico",
    "EspecificacaoServico",
    "EstadoProntidaoServico",
    "ProntidaoServicoExterno",
    "ServicoConfiguracoesExternas",
]
