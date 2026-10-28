"""Price snapshots governados, sem preços hardcoded e sem chamadas externas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from application.ai_pricing_runtime import (
    ConfiguracaoPrecoIAInvalida,
    montar_catalogo_precos_ia,
    snapshot_configurado_ia,
)
from core.ai_router import CapabilityIA, RotaIA

NOW = datetime(2026, 10, 18, 18, 0, tzinfo=timezone.utc)


def _price(*, provider="openai", model="test-model", ident="pricing-v1"):
    return {
        "price_snapshot_id": ident,
        "provider": provider,
        "model": model,
        "modalidade": "text_tokens",
        "moeda": "USD",
        "versao": 1,
        "vigencia_inicio": (NOW - timedelta(days=1)).isoformat(),
        "vigencia_fim": (NOW + timedelta(days=30)).isoformat(),
        "tarifas": [
            {"componente": "input_tokens", "preco": "0.55",
             "unidades_por_preco": 1_000_000},
            {"componente": "output_tokens", "preco": "4.00",
             "unidades_por_preco": 1_000_000},
        ],
    }


def _route():
    return RotaIA(
        configuracao_id="cfg",
        provider="openai",
        model="test-model",
        capability=CapabilityIA.TOOL_PLANNING,
        prioridade=100,
        price_snapshot_id="pricing-v1",
    )


def _config(payload, *, homologada=True):
    return SimpleNamespace(
        provedor="openai", habilitada=True, homologada=homologada,
        parametros={
            "model": "test-model",
            "price_snapshot_id": "pricing-v1",
            "price_snapshot": payload,
        },
    )


def test_catalogo_reaproveita_snapshot_versionado_por_modelo() -> None:
    catalog = montar_catalogo_precos_ia(
        rotas=(_route(),), configuracoes=(_config(_price()),),
    )
    assert catalog is not None
    snapshot = catalog.obter_snapshot(price_snapshot_id="pricing-v1")
    assert snapshot.provider == "openai"
    assert snapshot.model == "test-model"
    assert snapshot.tarifa("input_tokens").preco == Decimal("0.55")
    assert snapshot.vigente_em(NOW)


def test_sem_rate_card_nao_inventa_preco() -> None:
    assert montar_catalogo_precos_ia(
        rotas=(_route(),), configuracoes=(_config(None),),
    ) is None


@pytest.mark.parametrize("field,bad", [
    ("model", "another"),
    ("provider", "gemini"),
    ("price_snapshot_id", "other-id"),
])
def test_nao_aceita_snapshot_que_nao_pertence_a_rota(field, bad) -> None:
    payload = _price()
    payload[field] = bad
    with pytest.raises(ConfiguracaoPrecoIAInvalida):
        snapshot_configurado_ia(
            payload, provider="openai", model="test-model",
            snapshot_id="pricing-v1",
        )


def test_tarifas_negativas_sao_rejeitadas() -> None:
    payload = _price()
    payload["tarifas"][0]["preco"] = "-1"
    with pytest.raises(ValueError):
        snapshot_configurado_ia(
            payload, provider="openai", model="test-model",
            snapshot_id="pricing-v1",
        )


def test_nao_inclui_configuracao_nao_homologada() -> None:
    assert montar_catalogo_precos_ia(
        rotas=(_route(),),
        configuracoes=(_config(_price(), homologada=False),),
    ) is None
