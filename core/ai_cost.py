"""Cálculo determinístico e provider-neutral de custo de IA no Kordena V1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import StrEnum

from core.ai_pricing import PriceSnapshotIA, TarifaIA


class OrigemCustoIA(StrEnum):
    OBSERVADO_OFICIAL = "observed_official"
    ESTIMADO_CATALOGO = "estimated_catalog"
    INDISPONIVEL = "unavailable"


@dataclass(frozen=True, kw_only=True)
class CustoCalculadoIA:
    valor: Decimal | None
    moeda: str | None
    origem: OrigemCustoIA
    price_snapshot_id: str

    def __post_init__(self) -> None:
        snapshot_id = self.price_snapshot_id.strip()

        if not snapshot_id:
            raise ValueError("price_snapshot_id_obrigatorio")

        object.__setattr__(self, "price_snapshot_id", snapshot_id)

        if self.origem is OrigemCustoIA.INDISPONIVEL:
            if self.valor is not None:
                raise ValueError("custo_indisponivel_com_valor")
            return

        if self.valor is None:
            raise ValueError("custo_disponivel_sem_valor")

        if not self.valor.is_finite() or self.valor < 0:
            raise ValueError("valor_custo_invalido")

        if self.moeda is None:
            raise ValueError("custo_disponivel_sem_moeda")

        moeda = self.moeda.strip().upper()

        if len(moeda) != 3 or not moeda.isascii() or not moeda.isalpha():
            raise ValueError("moeda_custo_invalida")

        object.__setattr__(self, "moeda", moeda)


class CalculadoraCustoIA:
    """Calcula estimativa O(1) usando apenas usage e snapshot local."""

    _COMPONENTES_OBRIGATORIOS = (
        "input_tokens",
        "output_tokens",
    )

    def estimar_tokens(
        self,
        *,
        snapshot: PriceSnapshotIA,
        input_tokens: int | None,
        output_tokens: int | None,
        cached_tokens: int | None,
    ) -> CustoCalculadoIA:
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
        }

        if any(
            usage[componente] is None
            for componente in self._COMPONENTES_OBRIGATORIOS
        ):
            return self._indisponivel(snapshot)

        for componente, unidades in usage.items():
            if unidades is not None and unidades < 0:
                raise ValueError(f"{componente}_invalido")

        tarifas = {
            componente: snapshot.tarifa(componente)
            for componente in usage
        }

        if any(
            tarifas[componente] is None
            for componente in self._COMPONENTES_OBRIGATORIOS
        ):
            return self._indisponivel(snapshot)

        cached = cached_tokens or 0

        if cached > 0 and tarifas["cached_tokens"] is None:
            return self._indisponivel(snapshot)

        total = Decimal(0)

        with localcontext() as contexto:
            contexto.prec = 28

            for componente, unidades in usage.items():
                quantidade = unidades or 0

                if quantidade == 0:
                    continue

                tarifa = tarifas[componente]

                if tarifa is None:
                    return self._indisponivel(snapshot)

                total += _custo_componente(
                    unidades=quantidade,
                    tarifa=tarifa,
                )

        return CustoCalculadoIA(
            valor=total,
            moeda=snapshot.moeda,
            origem=OrigemCustoIA.ESTIMADO_CATALOGO,
            price_snapshot_id=snapshot.price_snapshot_id,
        )

    def observado_oficial(
        self,
        *,
        snapshot: PriceSnapshotIA,
        valor: Decimal,
        moeda: str,
    ) -> CustoCalculadoIA:
        moeda_normalizada = moeda.strip().upper()

        if moeda_normalizada != snapshot.moeda:
            raise ValueError("moeda_observada_diverge_snapshot")

        return CustoCalculadoIA(
            valor=valor,
            moeda=moeda_normalizada,
            origem=OrigemCustoIA.OBSERVADO_OFICIAL,
            price_snapshot_id=snapshot.price_snapshot_id,
        )

    @staticmethod
    def _indisponivel(snapshot: PriceSnapshotIA) -> CustoCalculadoIA:
        return CustoCalculadoIA(
            valor=None,
            moeda=snapshot.moeda,
            origem=OrigemCustoIA.INDISPONIVEL,
            price_snapshot_id=snapshot.price_snapshot_id,
        )


def _custo_componente(*, unidades: int, tarifa: TarifaIA) -> Decimal:
    try:
        return (
            Decimal(unidades)
            * tarifa.preco
            / Decimal(tarifa.unidades_por_preco)
        )
    except (InvalidOperation, ZeroDivisionError) as exc:
        raise ValueError("calculo_custo_invalido") from exc
