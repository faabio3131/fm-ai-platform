"""API pública da Impressão por Setor V1."""

from .adaptador_sqlalchemy import RepositorioSpoolSQLAlchemy
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
from .modelos_orm import ImpressaoBase
from .repositorios import RepositorioSpoolEmMemoria, RepositorioSpoolImpressao
from .servicos import ServicoSpoolImpressao, renderizar_ticket_setor

__all__ = [
    "DestinoImpressao",
    "ErroImpressao",
    "ImpressaoBase",
    "ImpressoraFake",
    "JobImpressao",
    "PortaImpressora",
    "RepositorioSpoolEmMemoria",
    "RepositorioSpoolImpressao",
    "RepositorioSpoolSQLAlchemy",
    "ResultadoEnfileiramento",
    "ResultadoProcessamento",
    "ServicoSpoolImpressao",
    "StatusImpressao",
    "impressao_v1_enabled",
    "renderizar_ticket_setor",
]
