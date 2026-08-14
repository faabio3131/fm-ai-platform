"""Registry de prontidão operacional dos módulos V1.

Em testes preservamos as flags E2E existentes. Fora de teste, um módulo somente
fica habilitado quando sua própria flag está ativa *e* todos os adapters reais
necessários foram declarados prontos. Isso evita promover UI test-only para o
restaurante antes da infraestrutura correspondente existir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE_VALUES = {"1", "true", "yes", "on"}
_REAL_ADAPTER_VALUES = {"1", "true", "yes", "on", "real", "production", "sqlalchemy", "http"}


@dataclass(frozen=True)
class ModuleSpec:
    name: str
    flag_env: str
    required_adapters: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModuleReadiness:
    name: str
    requested: bool
    enabled: bool
    test_mode: bool
    missing_adapters: tuple[str, ...]


def _enabled_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def adapter_real_configured(adapter_name: str) -> bool:
    key = f"FM_AI_ADAPTER_{adapter_name.strip().upper()}"
    value = os.getenv(key, "").strip().lower()
    return value in _REAL_ADAPTER_VALUES


def module_readiness(spec: ModuleSpec) -> ModuleReadiness:
    test_mode = os.getenv("FM_AI_TEST_MODE") == "1"
    requested = _enabled_env(spec.flag_env)

    if test_mode:
        return ModuleReadiness(
            name=spec.name,
            requested=requested,
            enabled=requested,
            test_mode=True,
            missing_adapters=(),
        )

    missing = tuple(
        adapter for adapter in spec.required_adapters if not adapter_real_configured(adapter)
    )
    return ModuleReadiness(
        name=spec.name,
        requested=requested,
        enabled=requested and not missing,
        test_mode=False,
        missing_adapters=missing,
    )


def module_v1_enabled(
    *, name: str, flag_env: str, required_adapters: tuple[str, ...] = ()
) -> bool:
    return module_readiness(
        ModuleSpec(name=name, flag_env=flag_env, required_adapters=required_adapters)
    ).enabled
