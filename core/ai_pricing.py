"""Pricing Catalog canônico e provider-neutral para uso de IA no Kordena V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import pairwise
from typing import Protocol


class ErroPricingCatalog(ValueError):
    """Erro seguro e estável do catálogo local/versionado de preços de IA."""


class SnapshotPrecoAusente(ErroPricingCatalog):
    pass


class SnapshotPrecoDuplicado(ErroPricingCatalog):
    pass


class VigenciaPrecoAmbigua(ErroPricingCatalog):
    pass


@dataclass(frozen=True, kw_only=True)
class TarifaIA:
    """Preço de um componente de usage para uma quantidade-base determinística."""

    componente: str
    preco: Decimal
    unidades_por_preco: int

    def __post_init__(self) -> None:
        componente = self.componente.strip().casefold()

        if not componente:
            raise ErroPricingCatalog("componente_preco_obrigatorio")

        if self.unidades_por_preco < 1:
            raise ErroPricingCatalog("unidades_por_preco_invalida")

        if not self.preco.is_finite() or self.preco < 0:
            raise ErroPricingCatalog("preco_unitario_invalido")

        object.__setattr__(self, "componente", componente)


@dataclass(frozen=True, kw_only=True)
class PriceSnapshotIA:
    """Snapshot imutável de preço com vigência temporal explícita."""

    price_snapshot_id: str
    provider: str
    model: str
    modalidade: str
    moeda: str
    versao: int
    vigencia_inicio: datetime
    vigencia_fim: datetime | None
    tarifas: tuple[TarifaIA, ...]

    def __post_init__(self) -> None:
        price_snapshot_id = self.price_snapshot_id.strip()
        provider = self.provider.strip().casefold()
        model = self.model.strip()
        modalidade = self.modalidade.strip().casefold()
        moeda = self.moeda.strip().upper()

        if not price_snapshot_id:
            raise ErroPricingCatalog("price_snapshot_id_obrigatorio")

        if not provider:
            raise ErroPricingCatalog("provider_obrigatorio")

        if not model:
            raise ErroPricingCatalog("model_obrigatorio")

        if not modalidade:
            raise ErroPricingCatalog("modalidade_obrigatoria")

        if len(moeda) != 3 or not moeda.isalpha():
            raise ErroPricingCatalog("moeda_invalida")

        if self.versao < 1:
            raise ErroPricingCatalog("versao_preco_invalida")

        inicio = _utc(self.vigencia_inicio, "vigencia_inicio")
        fim = (
            _utc(self.vigencia_fim, "vigencia_fim")
            if self.vigencia_fim is not None
            else None
        )

        if fim is not None and fim <= inicio:
            raise ErroPricingCatalog("vigencia_preco_invalida")

        if not self.tarifas:
            raise ErroPricingCatalog("tarifas_obrigatorias")

        componentes = tuple(tarifa.componente for tarifa in self.tarifas)

        if len(componentes) != len(set(componentes)):
            raise ErroPricingCatalog("componente_preco_duplicado")

        object.__setattr__(self, "price_snapshot_id", price_snapshot_id)
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "modalidade", modalidade)
        object.__setattr__(self, "moeda", moeda)
        object.__setattr__(self, "vigencia_inicio", inicio)
        object.__setattr__(self, "vigencia_fim", fim)
        object.__setattr__(
            self,
            "tarifas",
            tuple(sorted(self.tarifas, key=lambda tarifa: tarifa.componente)),
        )

    @property
    def chave_roteamento(self) -> tuple[str, str, str]:
        return self.provider, self.model, self.modalidade

    def tarifa(self, componente: str) -> TarifaIA | None:
        alvo = componente.strip().casefold()
        return next(
            (
                tarifa
                for tarifa in self.tarifas
                if tarifa.componente == alvo
            ),
            None,
        )

    def vigente_em(self, instante: datetime) -> bool:
        momento = _utc(instante, "instante_consulta")

        if momento < self.vigencia_inicio:
            return False

        return self.vigencia_fim is None or momento < self.vigencia_fim


class CatalogoPrecosIA(Protocol):
    def obter_snapshot(self, *, price_snapshot_id: str) -> PriceSnapshotIA: ...

    def resolver(
        self,
        *,
        provider: str,
        model: str,
        modalidade: str,
        instante: datetime,
    ) -> PriceSnapshotIA: ...


class CatalogoPrecosIAEmMemoria:
    """Catálogo local imutável; falha fechado para IDs ou vigências ambíguas."""

    def __init__(self, snapshots: tuple[PriceSnapshotIA, ...]) -> None:
        por_id: dict[str, PriceSnapshotIA] = {}
        por_chave: dict[tuple[str, str, str], list[PriceSnapshotIA]] = {}

        for snapshot in snapshots:
            if snapshot.price_snapshot_id in por_id:
                raise SnapshotPrecoDuplicado("price_snapshot_id_duplicado")

            por_id[snapshot.price_snapshot_id] = snapshot
            por_chave.setdefault(snapshot.chave_roteamento, []).append(snapshot)

        indexado: dict[tuple[str, str, str], tuple[PriceSnapshotIA, ...]] = {}

        for chave, itens in por_chave.items():
            ordenados = tuple(
                sorted(
                    itens,
                    key=lambda snapshot: (
                        snapshot.vigencia_inicio,
                        snapshot.versao,
                        snapshot.price_snapshot_id,
                    ),
                )
            )

            _validar_sem_sobreposicao(ordenados)
            indexado[chave] = ordenados

        self._por_id = por_id
        self._por_chave = indexado

    def obter_snapshot(self, *, price_snapshot_id: str) -> PriceSnapshotIA:
        snapshot = self._por_id.get(price_snapshot_id.strip())

        if snapshot is None:
            raise SnapshotPrecoAusente("price_snapshot_id_nao_encontrado")

        return snapshot

    def resolver(
        self,
        *,
        provider: str,
        model: str,
        modalidade: str,
        instante: datetime,
    ) -> PriceSnapshotIA:
        chave = (
            provider.strip().casefold(),
            model.strip(),
            modalidade.strip().casefold(),
        )
        candidatos = self._por_chave.get(chave, ())
        vigentes = tuple(
            snapshot
            for snapshot in candidatos
            if snapshot.vigente_em(instante)
        )

        if not vigentes:
            raise SnapshotPrecoAusente("snapshot_preco_vigente_nao_encontrado")

        if len(vigentes) != 1:
            raise VigenciaPrecoAmbigua("snapshot_preco_vigente_ambiguo")

        return vigentes[0]


def _utc(valor: datetime, campo: str) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroPricingCatalog(f"{campo}_sem_timezone")

    return valor.astimezone(timezone.utc)


def _validar_sem_sobreposicao(
    snapshots: tuple[PriceSnapshotIA, ...],
) -> None:
    for anterior, atual in pairwise(snapshots):
        fim_anterior = anterior.vigencia_fim

        if fim_anterior is None or atual.vigencia_inicio < fim_anterior:
            raise VigenciaPrecoAmbigua("vigencias_preco_sobrepostas")
