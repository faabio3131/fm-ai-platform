"""Estoque operacional V1, isolado do estoque legado."""

from .modelos import *  # noqa: F403
from .repositorios import RepositorioEstoqueEmMemoria
from .servicos import (
    consumir_reserva,
    liberar_reserva,
    registrar_devolucao,
    registrar_movimento,
    reservar_estoque,
)

__all__ = [
    "RepositorioEstoqueEmMemoria",
    "reservar_estoque",
    "consumir_reserva",
    "liberar_reserva",
    "registrar_movimento",
    "registrar_devolucao",
]
