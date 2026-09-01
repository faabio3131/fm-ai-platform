from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.ai_pricing import (
    CatalogoPrecosIAEmMemoria,
    ErroPricingCatalog,
    PriceSnapshotIA,
    SnapshotPrecoAusente,
    SnapshotPrecoDuplicado,
    TarifaIA,
    VigenciaPrecoAmbigua,
)

AGORA = datetime(2026, 8, 28, 18, 0, tzinfo=timezone.utc)


def tarifa(
    componente: str,
    preco: str,
    unidades_por_preco: int = 1_000_000,
) -> TarifaIA:
    return TarifaIA(
        componente=componente,
        preco=Decimal(preco),
        unidades_por_preco=unidades_por_preco,
    )


def snapshot(
    *,
    snapshot_id: str,
    inicio: datetime,
    fim: datetime | None,
    versao: int,
    input_price: str,
) -> PriceSnapshotIA:
    return PriceSnapshotIA(
        price_snapshot_id=snapshot_id,
        provider="provider-a",
        model="model-a",
        modalidade="text_tokens",
        moeda="usd",
        versao=versao,
        vigencia_inicio=inicio,
        vigencia_fim=fim,
        tarifas=(
            tarifa("input_tokens", input_price),
            tarifa("output_tokens", "2.50"),
        ),
    )


def test_snapshot_e_tarifas_sao_imutaveis_e_normalizados() -> None:
    item = snapshot(
        snapshot_id="price-a-v1",
        inicio=AGORA,
        fim=None,
        versao=1,
        input_price="1.2500",
    )

    assert item.provider == "provider-a"
    assert item.modalidade == "text_tokens"
    assert item.moeda == "USD"
    assert item.tarifa("INPUT_TOKENS") == tarifa(
        "input_tokens",
        "1.2500",
    )

    with pytest.raises(FrozenInstanceError):
        item.model = "alterado"  # type: ignore[misc]


def test_catalogo_resolve_snapshot_por_vigencia_sem_fallback_temporal() -> None:
    corte = AGORA + timedelta(days=30)
    antigo = snapshot(
        snapshot_id="price-a-v1",
        inicio=AGORA,
        fim=corte,
        versao=1,
        input_price="1.00",
    )
    novo = snapshot(
        snapshot_id="price-a-v2",
        inicio=corte,
        fim=None,
        versao=2,
        input_price="0.80",
    )
    catalogo = CatalogoPrecosIAEmMemoria((novo, antigo))

    assert catalogo.resolver(
        provider="PROVIDER-A",
        model="model-a",
        modalidade="TEXT_TOKENS",
        instante=AGORA + timedelta(days=1),
    ).price_snapshot_id == "price-a-v1"

    assert catalogo.resolver(
        provider="provider-a",
        model="model-a",
        modalidade="text_tokens",
        instante=corte,
    ).price_snapshot_id == "price-a-v2"

    with pytest.raises(SnapshotPrecoAusente):
        catalogo.resolver(
            provider="provider-a",
            model="model-a",
            modalidade="text_tokens",
            instante=AGORA - timedelta(seconds=1),
        )


def test_af21_snapshot_historico_permanece_reproduzivel_por_id() -> None:
    corte = AGORA + timedelta(days=30)
    antigo = snapshot(
        snapshot_id="price-a-v1",
        inicio=AGORA,
        fim=corte,
        versao=1,
        input_price="1.00",
    )
    novo = snapshot(
        snapshot_id="price-a-v2",
        inicio=corte,
        fim=None,
        versao=2,
        input_price="0.80",
    )
    catalogo = CatalogoPrecosIAEmMemoria((antigo, novo))

    historico = catalogo.obter_snapshot(
        price_snapshot_id="price-a-v1"
    )

    assert historico is antigo
    assert historico.versao == 1
    assert historico.tarifa("input_tokens") == tarifa(
        "input_tokens",
        "1.00",
    )


def test_catalogo_rejeita_snapshot_id_duplicado() -> None:
    primeiro = snapshot(
        snapshot_id="price-a-v1",
        inicio=AGORA,
        fim=AGORA + timedelta(days=10),
        versao=1,
        input_price="1.00",
    )
    segundo = snapshot(
        snapshot_id="price-a-v1",
        inicio=AGORA + timedelta(days=10),
        fim=None,
        versao=2,
        input_price="0.90",
    )

    with pytest.raises(SnapshotPrecoDuplicado):
        CatalogoPrecosIAEmMemoria((primeiro, segundo))


def test_catalogo_rejeita_vigencias_sobrepostas_fail_closed() -> None:
    primeiro = snapshot(
        snapshot_id="price-a-v1",
        inicio=AGORA,
        fim=AGORA + timedelta(days=20),
        versao=1,
        input_price="1.00",
    )
    segundo = snapshot(
        snapshot_id="price-a-v2",
        inicio=AGORA + timedelta(days=10),
        fim=None,
        versao=2,
        input_price="0.90",
    )

    with pytest.raises(VigenciaPrecoAmbigua):
        CatalogoPrecosIAEmMemoria((primeiro, segundo))


def test_snapshot_rejeita_timezone_ausente_e_tarifa_invalida() -> None:
    with pytest.raises(ErroPricingCatalog):
        snapshot(
            snapshot_id="price-a-v1",
            inicio=AGORA.replace(tzinfo=None),
            fim=None,
            versao=1,
            input_price="1.00",
        )

    with pytest.raises(ErroPricingCatalog):
        tarifa("input_tokens", "-0.01")

    with pytest.raises(ErroPricingCatalog):
        tarifa("input_tokens", "NaN")


def test_snapshot_rejeita_componentes_duplicados() -> None:
    with pytest.raises(ErroPricingCatalog):
        PriceSnapshotIA(
            price_snapshot_id="price-a-v1",
            provider="provider-a",
            model="model-a",
            modalidade="text_tokens",
            moeda="USD",
            versao=1,
            vigencia_inicio=AGORA,
            vigencia_fim=None,
            tarifas=(
                tarifa("input_tokens", "1.00"),
                tarifa("INPUT_TOKENS", "2.00"),
            ),
        )
