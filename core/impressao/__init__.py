"""API pública da Impressão por Setor V1."""

from .adapters import ImpressoraFake, PortaImpressora
from .erros import ErroImpressao
from .flags import impressao_v1_enabled
from .modelos import (
    DestinoImpressao,
    JobImpressao,
    ResultadoEnfileiramento,
    ResultadoProcessamento,
    StatusImpressao,
)
from .repositorios import RepositorioSpoolEmMemoria, RepositorioSpoolImpressao
from .servicos import ServicoSpoolImpressao, renderizar_ticket_setor

__all__ = [
    "DestinoImpressao",
    "ErroImpressao",
    "ImpressoraFake",
    "JobImpressao",
    "PortaImpressora",
    "RepositorioSpoolEmMemoria",
    "RepositorioSpoolImpressao",
    "ResultadoEnfileiramento",
    "ResultadoProcessamento",
    "ServicoSpoolImpressao",
    "StatusImpressao",
    "impressao_v1_enabled",
    "renderizar_ticket_setor",
]
