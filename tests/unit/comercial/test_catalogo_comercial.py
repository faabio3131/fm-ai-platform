from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.comercial.catalogo import (
    KORDENA_PLAN_CODES,
    StatusConfiguracaoCatalogo,
    TipoDescontoPromocao,
    normalizar_billing_period,
    normalizar_capability_key,
    normalizar_currency,
    normalizar_plan_code,
    validar_desconto,
    validar_intervalo,
    validar_transicao_configuracao,
)
from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida


def test_quatro_planos_canonicos_sao_estaveis() -> None:
    assert KORDENA_PLAN_CODES == (
        "KORDENA_PLAN_A",
        "KORDENA_PLAN_B",
        "KORDENA_PLAN_C",
        "KORDENA_PLAN_D",
    )
    assert normalizar_plan_code("kordena_plan_a") == "KORDENA_PLAN_A"
    with pytest.raises(DadoComercialInvalido, match="plan_code_nao_canonico"):
        normalizar_plan_code("KORDENA_PLAN_E")


def test_normalizacoes_de_pricing_sao_deterministicas() -> None:
    assert normalizar_currency(" brl ") == "BRL"
    assert normalizar_billing_period(" mensal ") == "MENSAL"
    assert normalizar_capability_key(" Users.Max ") == "users.max"

    with pytest.raises(DadoComercialInvalido, match="currency_invalida"):
        normalizar_currency("REAL")
    with pytest.raises(DadoComercialInvalido, match="billing_period_invalido"):
        normalizar_billing_period("mensal!")
    with pytest.raises(DadoComercialInvalido, match="capability_key_invalida"):
        normalizar_capability_key("users/max")


def test_promocao_percentual_e_monetaria_validam_currency() -> None:
    percentual, currency = validar_desconto(
        TipoDescontoPromocao.PERCENTAGE,
        Decimal("20"),
        None,
    )
    assert percentual == Decimal("20.00")
    assert currency is None

    monetario, currency = validar_desconto(
        TipoDescontoPromocao.FIXED_AMOUNT,
        Decimal("15.5"),
        "brl",
    )
    assert monetario == Decimal("15.50")
    assert currency == "BRL"

    with pytest.raises(DadoComercialInvalido):
        validar_desconto(TipoDescontoPromocao.PERCENTAGE, Decimal("101"), None)
    with pytest.raises(DadoComercialInvalido):
        validar_desconto(TipoDescontoPromocao.FIXED_PRICE, Decimal("10"), None)


def test_intervalo_exige_timezone_e_fim_posterior() -> None:
    inicio = datetime(2026, 10, 1, tzinfo=timezone.utc)
    fim = datetime(2026, 10, 2, tzinfo=timezone.utc)
    assert validar_intervalo(inicio, fim) == (inicio, fim)

    with pytest.raises(DadoComercialInvalido, match="datetime_sem_timezone"):
        validar_intervalo(datetime(2026, 10, 1), fim)
    with pytest.raises(DadoComercialInvalido, match="intervalo_invalido"):
        validar_intervalo(inicio, inicio)


def test_publicacao_exige_validacao_previa() -> None:
    validar_transicao_configuracao(
        StatusConfiguracaoCatalogo.DRAFT,
        StatusConfiguracaoCatalogo.VALIDATED,
    )
    validar_transicao_configuracao(
        StatusConfiguracaoCatalogo.VALIDATED,
        StatusConfiguracaoCatalogo.PUBLISHED,
    )
    with pytest.raises(TransicaoComercialInvalida):
        validar_transicao_configuracao(
            StatusConfiguracaoCatalogo.DRAFT,
            StatusConfiguracaoCatalogo.PUBLISHED,
        )
