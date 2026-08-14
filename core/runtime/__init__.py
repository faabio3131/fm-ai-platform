"""Composição do runtime comercial da V1.

Esta camada separa explicitamente ambiente, infraestrutura e disponibilidade de
módulos. Nenhum módulo de produção deve depender de ``FM_AI_TEST_MODE`` para
ficar acessível; em runtime normal ele só é liberado quando a flag operacional e
os adapters reais necessários estiverem configurados.
"""

from .config import RuntimeEnvironment, RuntimeSettings, load_runtime_settings
from .database import DatabaseHealth, build_engine, check_database_health
from .registry import (
    ModuleReadiness,
    ModuleSpec,
    adapter_real_configured,
    module_readiness,
    module_v1_enabled,
)

__all__ = [
    "DatabaseHealth",
    "ModuleReadiness",
    "ModuleSpec",
    "RuntimeEnvironment",
    "RuntimeSettings",
    "adapter_real_configured",
    "build_engine",
    "check_database_health",
    "load_runtime_settings",
    "module_readiness",
    "module_v1_enabled",
]
