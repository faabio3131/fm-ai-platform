"""Vertical slice seguro do PDV V1."""

from .modelos import EntradaPDV, ResultadoPDV
from .roteamento import ModoPDV, PDVRolloutConfig, decidir_modo
from .servicos import finalizar_venda_pdv

__all__ = [
    "EntradaPDV",
    "ModoPDV",
    "PDVRolloutConfig",
    "ResultadoPDV",
    "decidir_modo",
    "finalizar_venda_pdv",
]
