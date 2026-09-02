"""API publica de mesas e comandas V1."""

from .adaptador_sqlalchemy import RepositorioSalaoSQLAlchemy
from .erros import ErroSalao
from .flags import salao_v1_enabled
from .modelos import (
    Comanda,
    EventoSalao,
    Mesa,
    MetodoFechamento,
    PagamentoConfirmadoComanda,
    ParcelaFechamento,
    ParticipanteComanda,
    PedidoNaComanda,
    SnapshotSalao,
    StatusComanda,
    StatusMesa,
)
from .modelos_orm import SalaoBase
from .servicos import ServicoSalao

__all__ = [
    "Comanda",
    "ErroSalao",
    "EventoSalao",
    "Mesa",
    "MetodoFechamento",
    "PagamentoConfirmadoComanda",
    "ParcelaFechamento",
    "ParticipanteComanda",
    "PedidoNaComanda",
    "RepositorioSalaoSQLAlchemy",
    "SalaoBase",
    "ServicoSalao",
    "SnapshotSalao",
    "StatusComanda",
    "StatusMesa",
    "salao_v1_enabled",
]
