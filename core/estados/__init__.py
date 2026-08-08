"""Serviços puros das máquinas operacionais V1."""

from .cozinha import PoliticaCozinha, pode_enviar_para_cozinha
from .maquinas import (
    MAQUINAS,
    ComandoTransicao,
    ErroTransicao,
    RegistroIdempotenciaEmMemoria,
    ResultadoTransicao,
    SnapshotEstado,
    transicionar,
)

__all__ = [
    "MAQUINAS",
    "ComandoTransicao",
    "ErroTransicao",
    "PoliticaCozinha",
    "RegistroIdempotenciaEmMemoria",
    "ResultadoTransicao",
    "SnapshotEstado",
    "pode_enviar_para_cozinha",
    "transicionar",
]
