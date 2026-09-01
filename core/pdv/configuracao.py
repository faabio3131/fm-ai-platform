"""Loader server-side do rollout do PDV V1.

O runtime permanece LEGACY por padrão. Canary fora do harness de teste só pode ser
ativado em staging/production com autorização explícita, escopo vindo do
RuntimeSettings e terminal comercial allowlisted.
"""

from __future__ import annotations

import os

from core.pagamentos.flags import FlagsPagamentosV1
from core.pedidos.flags import OrdersFeatureFlags
from core.runtime.config import RuntimeSettings

from .roteamento import (
    ConfiguracaoRolloutInvalida,
    ModoPDV,
    PDVFlags,
    PDVRolloutConfig,
)


def _flags_canary() -> PDVFlags:
    return PDVFlags(
        orders=OrdersFeatureFlags(orders_authoritative=True),
        payments=FlagsPagamentosV1(True, True, True),
        stock_ledger_authoritative=True,
    )


def _terminais_permitidos_comerciais() -> frozenset[str]:
    raw = os.getenv("FM_AI_PDV_ALLOWED_TERMINALS", "")
    return frozenset(
        terminal.strip()
        for terminal in raw.split(",")
        if terminal.strip()
    )


def carregar_terminal_pdv_ambiente() -> str:
    """Resolve a identidade local do terminal sem aceitar dado vindo da UI."""

    if os.getenv("FM_AI_TEST_MODE") == "1":
        return os.getenv("FM_AI_TEST_TERMINAL", "pdv-default").strip() or "pdv-default"
    return os.getenv("FM_AI_PDV_TERMINAL_ID", "pdv-default").strip() or "pdv-default"


def carregar_rollout_ambiente(
    *, runtime_settings: RuntimeSettings | None = None
) -> PDVRolloutConfig:
    """Carrega rollout governado.

    Testes preservam a configuração E2E histórica. Fora de teste, qualquer modo
    diferente de LEGACY exige runtime comercial explícito. O canary comercial
    também exige uma chave de autorização, terminal identificado e allowlist.
    """

    em_teste = os.getenv("FM_AI_TEST_MODE") == "1"
    solicitado_raw = os.getenv("FM_AI_PDV_MODE", ModoPDV.LEGACY.value).strip().lower()

    if em_teste:
        if solicitado_raw not in {modo.value for modo in ModoPDV}:
            solicitado_raw = ModoPDV.LEGACY.value
        modo = ModoPDV(solicitado_raw)
        tenant = os.getenv("FM_AI_TEST_TENANT", "legacy").strip() or "legacy"
        unidade = os.getenv("FM_AI_TEST_UNIDADE", "legacy").strip() or "legacy"
        terminal = carregar_terminal_pdv_ambiente()

        if modo is ModoPDV.SHADOW:
            flags = PDVFlags(
                orders=OrdersFeatureFlags(orders_shadow_write=True)
            )
        elif modo is ModoPDV.AUTHORITATIVE_CANARY:
            flags = _flags_canary()
        else:
            flags = PDVFlags()

        return PDVRolloutConfig(
            tenant,
            unidade,
            frozenset({terminal}),
            modo,
            flags,
            contexto_confiavel=True,
        )

    tenant = runtime_settings.tenant_id if runtime_settings is not None else "legacy"
    unidade = runtime_settings.unidade_id if runtime_settings is not None else "legacy"

    if solicitado_raw == ModoPDV.LEGACY.value:
        return PDVRolloutConfig(tenant, unidade)

    if runtime_settings is None or not runtime_settings.commercial:
        raise ConfiguracaoRolloutInvalida(
            "pdv_canary_fora_de_runtime_comercial"
        )

    if solicitado_raw != ModoPDV.AUTHORITATIVE_CANARY.value:
        raise ConfiguracaoRolloutInvalida(
            "pdv_modo_comercial_nao_suportado"
        )

    if os.getenv("FM_AI_PDV_COMMERCIAL_CANARY_ENABLED") != "1":
        raise ConfiguracaoRolloutInvalida(
            "pdv_canary_comercial_nao_autorizado"
        )

    terminal = os.getenv("FM_AI_PDV_TERMINAL_ID", "").strip()
    if not terminal:
        raise ConfiguracaoRolloutInvalida(
            "pdv_terminal_comercial_ausente"
        )

    permitidos = _terminais_permitidos_comerciais()
    if not permitidos:
        raise ConfiguracaoRolloutInvalida(
            "pdv_allowlist_terminais_ausente"
        )
    if terminal not in permitidos:
        raise ConfiguracaoRolloutInvalida(
            "pdv_terminal_fora_da_allowlist"
        )

    return PDVRolloutConfig(
        tenant,
        unidade,
        permitidos,
        ModoPDV.AUTHORITATIVE_CANARY,
        _flags_canary(),
        contexto_confiavel=True,
    )
