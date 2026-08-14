"""Loader server-side do rollout do PDV V1."""

import os

from core.pagamentos.flags import FlagsPagamentosV1
from core.pedidos.flags import OrdersFeatureFlags

from .roteamento import ModoPDV, PDVFlags, PDVRolloutConfig


def carregar_rollout_ambiente() -> PDVRolloutConfig:
    seguro = os.getenv("FM_AI_TEST_MODE") == "1"
    tenant = os.getenv("FM_AI_TEST_TENANT", "legacy")
    unidade = os.getenv("FM_AI_TEST_UNIDADE", "legacy")
    terminal = os.getenv("FM_AI_TEST_TERMINAL", "pdv-default")
    solicitado = os.getenv("FM_AI_PDV_MODE", "legacy")
    if not seguro or solicitado not in {m.value for m in ModoPDV}:
        solicitado = ModoPDV.LEGACY.value
    modo = ModoPDV(solicitado)
    if modo is ModoPDV.SHADOW:
        flags = PDVFlags(orders=OrdersFeatureFlags(orders_shadow_write=True))
    elif modo is ModoPDV.AUTHORITATIVE_CANARY:
        flags = PDVFlags(
            orders=OrdersFeatureFlags(orders_authoritative=True),
            payments=FlagsPagamentosV1(True, True, True),
            stock_ledger_authoritative=True,
        )
    else:
        flags = PDVFlags()
    return PDVRolloutConfig(
        tenant,
        unidade,
        frozenset({terminal}) if seguro else frozenset(),
        modo,
        flags,
        contexto_confiavel=seguro,
    )
