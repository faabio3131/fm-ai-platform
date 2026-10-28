from __future__ import annotations

import pytest

from application.commercial_billing import BillingProviderAdapterRegistryV1
from core.comercial.billing import BillingConnectionTestResult
from core.comercial.billing_config import (
    BillingConnectionTestStatus,
    BillingProviderAccountStatus,
    normalizar_provider_code,
    normalizar_secret_reference,
    validar_transicao_provider_account,
)
from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida


class _Provider:
    def __init__(self, code: str) -> None:
        self.provider_code = code

    def test_connection(self, **_kwargs) -> BillingConnectionTestResult:
        return BillingConnectionTestResult(
            ok=True,
            provider_code=self.provider_code,
            detail_code="ok",
        )


def test_provider_code_is_open_and_normalized_not_closed_enum() -> None:
    assert normalizar_provider_code("gateway-custom-01") == "GATEWAY-CUSTOM-01"
    assert normalizar_provider_code("provider.alpha") == "PROVIDER.ALPHA"


def test_secret_reference_requires_reference_not_raw_value() -> None:
    assert normalizar_secret_reference("env:FM_BILLING_ACCOUNT_A") == (
        "env:FM_BILLING_ACCOUNT_A"
    )
    with pytest.raises(DadoComercialInvalido):
        normalizar_secret_reference("raw-secret-without-reference")


def test_activation_requires_successful_connection_test() -> None:
    with pytest.raises(
        TransicaoComercialInvalida,
        match="activation_requires_connection_test",
    ):
        validar_transicao_provider_account(
            BillingProviderAccountStatus.VALIDATING,
            BillingProviderAccountStatus.ACTIVE,
            last_test_status=BillingConnectionTestStatus.FAIL,
        )

    validar_transicao_provider_account(
        BillingProviderAccountStatus.VALIDATING,
        BillingProviderAccountStatus.ACTIVE,
        last_test_status=BillingConnectionTestStatus.PASS,
    )


def test_adapter_registry_accepts_multiple_runtime_providers() -> None:
    registry = BillingProviderAdapterRegistryV1(
        (_Provider("PROVIDER_ALPHA"), _Provider("PROVIDER_BETA"))
    )
    assert registry.available_provider_codes() == (
        "PROVIDER_ALPHA",
        "PROVIDER_BETA",
    )
    assert registry.resolve("provider_alpha").provider_code == "PROVIDER_ALPHA"

    with pytest.raises(DadoComercialInvalido, match="adapter_duplicado"):
        registry.register(_Provider("provider_alpha"))

    with pytest.raises(DadoComercialInvalido, match="adapter_nao_registrado"):
        registry.resolve("provider_gamma")
