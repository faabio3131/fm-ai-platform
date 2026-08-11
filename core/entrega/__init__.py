"""API pública inicial da Expedição e Entrega V1."""

from .erros import ErroEntrega
from .flags import entrega_v1_enabled
from .modelos import (
    ChecklistExpedicao,
    Entrega,
    ModalidadeEntrega,
    ProvaEntrega,
    StatusEntrega,
    TentativaEntrega,
)

__all__ = [
    "ChecklistExpedicao",
    "Entrega",
    "ErroEntrega",
    "ModalidadeEntrega",
    "ProvaEntrega",
    "StatusEntrega",
    "TentativaEntrega",
    "entrega_v1_enabled",
]
