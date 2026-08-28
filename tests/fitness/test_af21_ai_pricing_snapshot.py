from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from core.ai_pricing import PriceSnapshotIA, TarifaIA

FORBIDDEN_PROVIDER_SDKS = (
    "google.genai",
    "google.generativeai",
    "openai",
    "anthropic",
)


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )
    encontrados: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            encontrados.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            encontrados.append(node.module)

    return tuple(encontrados)


def _snapshot() -> PriceSnapshotIA:
    return PriceSnapshotIA(
        price_snapshot_id="fixture-v1",
        provider="provider-fixture",
        model="model-fixture",
        modalidade="text_tokens",
        moeda="USD",
        versao=1,
        vigencia_inicio=datetime(2026, 1, 1, tzinfo=timezone.utc),
        vigencia_fim=None,
        tarifas=(
            TarifaIA(
                componente="input_tokens",
                preco=Decimal("1.00"),
                unidades_por_preco=1_000_000,
            ),
        ),
    )


def test_af21_snapshot_tem_identidade_e_vigencia_reprodutiveis() -> None:
    campos = set(PriceSnapshotIA.__dataclass_fields__)

    assert {
        "price_snapshot_id",
        "provider",
        "model",
        "modalidade",
        "moeda",
        "versao",
        "vigencia_inicio",
        "vigencia_fim",
        "tarifas",
    } <= campos

    item = _snapshot()

    with pytest.raises(FrozenInstanceError):
        item.versao = 2  # type: ignore[misc]


def test_af21_pricing_core_nao_importa_sdk_de_provider() -> None:
    path = Path("core/ai_pricing.py")

    for modulo in _imports(path):
        assert not modulo.startswith(FORBIDDEN_PROVIDER_SDKS)


def test_af21_pricing_core_nao_contem_preco_hardcoded_de_provider() -> None:
    texto = Path("core/ai_pricing.py").read_text(encoding="utf-8").lower()

    assert "gemini" not in texto
    assert "openai" not in texto
    assert "anthropic" not in texto
    assert "http://" not in texto
    assert "https://" not in texto
