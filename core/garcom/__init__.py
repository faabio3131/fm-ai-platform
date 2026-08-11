"""API pública da interface do garçom V1."""

from .erros import ErroGarcom
from .flags import garcom_v1_enabled
from .modelos import (
    AlertaProntoGarcom,
    PainelGarcom,
    ResumoComandaGarcom,
    ResumoMesaGarcom,
)
from .observabilidade import ColetorMetricasGarcom
from .runtime_teste import contexto_garcom_teste, preparar_schema_teste
from .servicos import ServicoGarcom

__all__ = [
    "AlertaProntoGarcom",
    "ColetorMetricasGarcom",
    "ErroGarcom",
    "PainelGarcom",
    "ResumoComandaGarcom",
    "ResumoMesaGarcom",
    "ServicoGarcom",
    "contexto_garcom_teste",
    "garcom_v1_enabled",
    "preparar_schema_teste",
]
