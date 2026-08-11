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
from .runtime_teste import contexto_salao_teste, preparar_schema_teste
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
    "contexto_salao_teste",
    "preparar_schema_teste",
    "salao_v1_enabled",
]
