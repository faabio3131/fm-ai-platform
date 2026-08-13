"""Contratos puros e imutaveis do ledger de estoque V1."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class TipoMovimento(StrEnum):
    ENTRADA = "entrada"
    RESERVA = "reserva"
    LIBERACAO_RESERVA = "liberacao_reserva"
    CONSUMO = "consumo"
    PERDA = "perda"
    AJUSTE_POSITIVO = "ajuste_positivo"
    AJUSTE_NEGATIVO = "ajuste_negativo"
    DEVOLUCAO = "devolucao"
    COMPENSACAO = "compensacao"


class StatusReserva(StrEnum):
    ATIVA = "ativa"
    CONSUMIDA = "consumida"
    LIBERADA = "liberada"


def quantidade(valor: Decimal | str | int) -> Decimal:
    numero = Decimal(str(valor))
    if not numero.is_finite() or numero <= 0:
        raise ValueError("quantidade deve ser positiva e finita")
    return numero


def instante_utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("timestamp deve conter timezone")
    return valor.astimezone(timezone.utc)


@dataclass(frozen=True)
class InsumoEstoque:
    insumo_id: str
    tenant_id: str
    unidade_id: str
    nome: str
    unidade_medida: str
    ativo: bool = True


@dataclass(frozen=True)
class SaldoEstoque:
    tenant_id: str
    unidade_id: str
    insumo_id: str
    saldo_fisico: Decimal
    saldo_reservado: Decimal
    versao: int

    @property
    def saldo_disponivel(self) -> Decimal:
        return self.saldo_fisico - self.saldo_reservado


@dataclass(frozen=True)
class MovimentoEstoque:
    movimento_id: str
    tenant_id: str
    unidade_id: str
    insumo_id: str
    tipo_movimento: TipoMovimento
    quantidade: Decimal
    unidade_medida: str
    origem_tipo: str
    origem_id: str
    origem_versao: int
    idempotency_key: str
    occurred_at: datetime
    correlation_id: str
    causation_id: str | None
    ator: str
    motivo: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for nome in (
            "movimento_id",
            "tenant_id",
            "unidade_id",
            "insumo_id",
            "unidade_medida",
            "origem_tipo",
            "origem_id",
            "idempotency_key",
            "correlation_id",
            "ator",
        ):
            if not str(getattr(self, nome)).strip():
                raise ValueError(f"{nome} obrigatorio")
        object.__setattr__(self, "quantidade", quantidade(self.quantidade))
        object.__setattr__(self, "occurred_at", instante_utc(self.occurred_at))
        seguros = {
            str(k): v
            for k, v in self.metadata.items()
            if not any(
                x in str(k).lower()
                for x in ("senha", "token", "secret", "authorization")
            )
            and isinstance(v, (str, int, float, bool, type(None)))
        }
        object.__setattr__(
            self, "metadata", MappingProxyType(dict(sorted(seguros.items())))
        )

    @property
    def chave_logica(self) -> tuple[str, str, str, str, TipoMovimento, str, int]:
        return (
            self.tenant_id,
            self.unidade_id,
            self.origem_tipo,
            self.origem_id,
            self.tipo_movimento,
            self.insumo_id,
            self.origem_versao,
        )


@dataclass(frozen=True)
class ItemSnapshotFicha:
    produto_id: str
    item_pedido_id: str
    insumo_id: str
    quantidade_por_unidade: Decimal
    quantidade_total: Decimal
    unidade_medida: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "quantidade_por_unidade", quantidade(self.quantidade_por_unidade)
        )
        object.__setattr__(self, "quantidade_total", quantidade(self.quantidade_total))


@dataclass(frozen=True)
class SnapshotFichaEstoque:
    pedido_id: str
    versao_ficha: str
    capturado_em: datetime
    itens: tuple[ItemSnapshotFicha, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "capturado_em", instante_utc(self.capturado_em))
        object.__setattr__(self, "itens", tuple(self.itens))
        if not self.itens:
            raise ValueError("snapshot exige itens")


@dataclass(frozen=True)
class ReservaEstoque:
    reserva_id: str
    tenant_id: str
    unidade_id: str
    pedido_id: str
    pedido_versao: int
    snapshot: SnapshotFichaEstoque
    status: StatusReserva
    idempotency_key: str
    criada_em: datetime
    resolvida_em: datetime | None = None


@dataclass(frozen=True)
class ResultadoMovimento:
    movimentos: tuple[MovimentoEstoque, ...]
    saldos: tuple[SaldoEstoque, ...]
    idempotente: bool
    eventos: tuple[Any, ...] = ()
    auditorias: tuple[Any, ...] = ()


@dataclass(frozen=True)
class ResultadoReserva(ResultadoMovimento):
    reserva: ReservaEstoque | None = None
