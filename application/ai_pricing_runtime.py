"""Leitura de tarifas de IA versionadas configuradas pela FM no control plane.

Os snapshots são dados de configuração do provider, nunca constantes no
repositório. O módulo não faz requisições de rede nem chama um modelo.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from core.ai_pricing import (
    CatalogoPrecosIAEmMemoria,
    ErroPricingCatalog,
    PriceSnapshotIA,
    TarifaIA,
)
from core.ai_router import RotaIA


class ConfiguracaoPrecoIAInvalida(ErroPricingCatalog):
    pass


def _instante(value: object, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ConfiguracaoPrecoIAInvalida(f"ai_pricing_{field}_ausente")
    try:
        instante = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfiguracaoPrecoIAInvalida(f"ai_pricing_{field}_invalido") from exc
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ConfiguracaoPrecoIAInvalida(f"ai_pricing_{field}_sem_timezone")
    return instante.astimezone(timezone.utc)


def snapshot_configurado_ia(
    documento: dict[str, Any], *, provider: str, model: str,
    snapshot_id: str,
) -> PriceSnapshotIA:
    """Parse e verifica identidade; não aceita preço negativo ou vigência implícita."""
    if documento.get("price_snapshot_id") != snapshot_id:
        raise ConfiguracaoPrecoIAInvalida("ai_pricing_snapshot_divergente")
    if documento.get("provider") != provider or documento.get("model") != model:
        raise ConfiguracaoPrecoIAInvalida("ai_pricing_modelo_divergente")
    tarifas_raw = documento.get("tarifas")
    if not isinstance(tarifas_raw, list) or not tarifas_raw:
        raise ConfiguracaoPrecoIAInvalida("ai_pricing_tarifas_invalidas")
    tarifas = []
    for item in tarifas_raw:
        if not isinstance(item, dict):
            raise ConfiguracaoPrecoIAInvalida("ai_pricing_tarifa_invalida")
        try:
            tarifa = TarifaIA(
                componente=str(item["componente"]),
                preco=Decimal(str(item["preco"])),
                unidades_por_preco=int(item["unidades_por_preco"]),
            )
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise ConfiguracaoPrecoIAInvalida("ai_pricing_tarifa_invalida") from exc
        tarifas.append(tarifa)
    try:
        versao = int(documento["versao"])
    except (KeyError, ValueError, TypeError) as exc:
        raise ConfiguracaoPrecoIAInvalida("ai_pricing_versao_invalida") from exc
    fim = documento.get("vigencia_fim")
    return PriceSnapshotIA(
        price_snapshot_id=snapshot_id,
        provider=provider,
        model=model,
        modalidade=str(documento.get("modalidade") or "text_tokens"),
        moeda=str(documento.get("moeda") or ""),
        versao=versao,
        vigencia_inicio=_instante(
            documento.get("vigencia_inicio"), field="inicio"
        ),
        vigencia_fim=(
            _instante(fim, field="fim") if fim is not None else None
        ),
        tarifas=tuple(tarifas),
    )


def montar_catalogo_precos_ia(
    *,
    rotas: tuple[RotaIA, ...],
    configuracoes: tuple[object, ...],
) -> CatalogoPrecosIAEmMemoria | None:
    """Somente configurações de rotas homologadas podem formar catálogo.

    Rota com preço ausente não recebe custo inventado. Quando a proteção
    financeira for exigida, o chamador deverá negar falta de catálogo.
    """
    rotas_validas = {
        (r.provider, r.model, r.price_snapshot_id) for r in rotas
    }
    snapshots: dict[str, PriceSnapshotIA] = {}
    for config in configuracoes:
        if not (
            getattr(config, "habilitada", False)
            and getattr(config, "homologada", False)
        ):
            continue
        params = getattr(config, "parametros", None)
        if not isinstance(params, dict):
            continue
        documento = params.get("price_snapshot")
        if documento is None:
            continue
        if not isinstance(documento, dict):
            raise ConfiguracaoPrecoIAInvalida("ai_pricing_documento_invalido")
        provider = getattr(config, "provedor", "")
        model = str(params.get("model") or "")
        snapshot_id = str(params.get("price_snapshot_id") or "")
        if (provider, model, snapshot_id) not in rotas_validas:
            raise ConfiguracaoPrecoIAInvalida("ai_pricing_rota_nao_homologada")
        snapshot = snapshot_configurado_ia(
            documento, provider=provider,
            model=model, snapshot_id=snapshot_id,
        )
        old = snapshots.get(snapshot_id)
        if old is not None and old != snapshot:
            raise ConfiguracaoPrecoIAInvalida("ai_pricing_id_duplicado")
        snapshots[snapshot_id] = snapshot
    if not snapshots:
        return None
    return CatalogoPrecosIAEmMemoria(tuple(snapshots.values()))
