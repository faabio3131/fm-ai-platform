from __future__ import annotations

from decimal import Decimal

from core.comercial.catalogo import EntitlementPlano
from core.comercial.entitlement import (
    EstadoComercial,
    ModoAcessoComercial,
    capabilities_do_plano,
    capability_por_chave,
    desserializar_capabilities,
    modo_para_estado,
    serializar_capabilities,
)


def test_estado_comercial_resolve_modo_fail_closed() -> None:
    assert modo_para_estado(EstadoComercial.TRIAL_ACTIVE) == ModoAcessoComercial.FULL
    assert (
        modo_para_estado(EstadoComercial.SUBSCRIPTION_ACTIVE)
        == ModoAcessoComercial.FULL
    )
    assert modo_para_estado(EstadoComercial.PAST_DUE) == ModoAcessoComercial.LIMITED
    assert (
        modo_para_estado(EstadoComercial.TRIAL_EXPIRED)
        == ModoAcessoComercial.BILLING_ONLY
    )
    assert (
        modo_para_estado(EstadoComercial.CONFIGURATION_PENDING)
        == ModoAcessoComercial.BLOCKED
    )


def test_capabilities_roundtrip_preserva_limites_e_config() -> None:
    source = (
        EntitlementPlano(
            capability_key="users.max",
            enabled=True,
            limit_value=Decimal("5"),
            limit_unit="users",
            config={"scope": "tenant"},
        ),
        EntitlementPlano(
            capability_key="core_ai.enabled",
            enabled=False,
            limit_value=None,
            limit_unit=None,
            config={},
        ),
    )
    normalized = capabilities_do_plano(source)
    payload = serializar_capabilities(normalized)
    restored = desserializar_capabilities(payload)

    assert restored == normalized
    users = capability_por_chave(restored, "USERS.MAX")
    assert users is not None
    assert users.enabled is True
    assert users.limit_value == Decimal("5")
