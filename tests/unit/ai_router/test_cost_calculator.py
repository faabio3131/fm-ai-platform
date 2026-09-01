from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.ai_cost import CalculadoraCustoIA, OrigemCustoIA
from core.ai_pricing import PriceSnapshotIA, TarifaIA

AGORA = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def snapshot(*, incluir_cache: bool = True) -> PriceSnapshotIA:
    tarifas = [
        TarifaIA(
            componente="input_tokens",
            preco=Decimal("1.25"),
            unidades_por_preco=1_000_000,
        ),
        TarifaIA(
            componente="output_tokens",
            preco=Decimal("5.00"),
            unidades_por_preco=1_000_000,
        ),
    ]

    if incluir_cache:
        tarifas.append(
            TarifaIA(
                componente="cached_tokens",
                preco=Decimal("0.25"),
                unidades_por_preco=1_000_000,
            )
        )

    return PriceSnapshotIA(
        price_snapshot_id="price-a-v1",
        provider="provider-a",
        model="model-a",
        modalidade="text_tokens",
        moeda="USD",
        versao=1,
        vigencia_inicio=AGORA,
        vigencia_fim=None,
        tarifas=tuple(tarifas),
    )


def test_calcula_custo_estimado_deterministico_em_decimal() -> None:
    resultado = CalculadoraCustoIA().estimar_tokens(
        snapshot=snapshot(),
        input_tokens=1_000_000,
        output_tokens=500_000,
        cached_tokens=200_000,
    )

    assert resultado.valor == Decimal("3.80")
    assert resultado.moeda == "USD"
    assert resultado.origem is OrigemCustoIA.ESTIMADO_CATALOGO
    assert resultado.price_snapshot_id == "price-a-v1"


def test_mesmo_snapshot_e_usage_reproduzem_exatamente_o_mesmo_custo() -> None:
    calculadora = CalculadoraCustoIA()

    primeiro = calculadora.estimar_tokens(
        snapshot=snapshot(),
        input_tokens=123_456,
        output_tokens=7_890,
        cached_tokens=321,
    )
    segundo = calculadora.estimar_tokens(
        snapshot=snapshot(),
        input_tokens=123_456,
        output_tokens=7_890,
        cached_tokens=321,
    )

    assert primeiro == segundo


def test_usage_obrigatorio_ausente_marca_custo_indisponivel() -> None:
    resultado = CalculadoraCustoIA().estimar_tokens(
        snapshot=snapshot(),
        input_tokens=None,
        output_tokens=10,
        cached_tokens=None,
    )

    assert resultado.valor is None
    assert resultado.origem is OrigemCustoIA.INDISPONIVEL
    assert resultado.price_snapshot_id == "price-a-v1"


def test_cache_usado_sem_tarifa_marca_custo_indisponivel() -> None:
    resultado = CalculadoraCustoIA().estimar_tokens(
        snapshot=snapshot(incluir_cache=False),
        input_tokens=10,
        output_tokens=5,
        cached_tokens=3,
    )

    assert resultado.valor is None
    assert resultado.origem is OrigemCustoIA.INDISPONIVEL


def test_cache_nao_suportado_sem_usage_nao_invalida_estimativa() -> None:
    resultado = CalculadoraCustoIA().estimar_tokens(
        snapshot=snapshot(incluir_cache=False),
        input_tokens=10,
        output_tokens=5,
        cached_tokens=None,
    )

    assert resultado.valor is not None
    assert resultado.origem is OrigemCustoIA.ESTIMADO_CATALOGO


def test_usage_negativo_falha_fechado() -> None:
    with pytest.raises(ValueError, match="input_tokens_invalido"):
        CalculadoraCustoIA().estimar_tokens(
            snapshot=snapshot(),
            input_tokens=-1,
            output_tokens=1,
            cached_tokens=0,
        )


def test_custo_oficial_tem_precedencia_sem_conversao_de_moeda() -> None:
    resultado = CalculadoraCustoIA().observado_oficial(
        snapshot=snapshot(),
        valor=Decimal("0.0042"),
        moeda="usd",
    )

    assert resultado.valor == Decimal("0.0042")
    assert resultado.origem is OrigemCustoIA.OBSERVADO_OFICIAL
    assert resultado.moeda == "USD"

    with pytest.raises(ValueError, match="moeda_observada_diverge_snapshot"):
        CalculadoraCustoIA().observado_oficial(
            snapshot=snapshot(),
            valor=Decimal("0.0042"),
            moeda="BRL",
        )
