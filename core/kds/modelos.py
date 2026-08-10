"""Contratos imutaveis do KDS V1 por setor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum


class EstadoSLA(StrEnum):
    SEM_SLA = "sem_sla"
    DENTRO = "dentro"
    ATENCAO = "atencao"
    ESTOURADO = "estourado"


@dataclass(frozen=True)
class SetorProducao:
    setor_id: str
    tenant_id: str
    unidade_id: str
    codigo: str
    nome: str
    ordem: int
    sla_segundos: int | None
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime

    def __post_init__(self) -> None:
        if not all(
            valor.strip()
            for valor in (
                self.setor_id,
                self.tenant_id,
                self.unidade_id,
                self.codigo,
                self.nome,
            )
        ):
            raise ValueError("setor_invalido")
        if self.ordem < 0 or (self.sla_segundos is not None and self.sla_segundos <= 0):
            raise ValueError("configuracao_setor_invalida")
        for campo in ("criado_em", "atualizado_em"):
            instante = getattr(self, campo)
            if instante.tzinfo is None:
                raise ValueError("timestamp_invalido")
            object.__setattr__(self, campo, instante.astimezone(timezone.utc))


@dataclass(frozen=True)
class ProducaoItem:
    producao_id: str
    tenant_id: str
    unidade_id: str
    pedido_id: str
    pedido_item_id: str
    setor_id: str
    status: str
    prioridade: int
    quantidade: Decimal
    tentativa: int
    versao: int
    criado_em: datetime
    atualizado_em: datetime
    aceita_em: datetime | None = None
    iniciada_em: datetime | None = None
    pausa_iniciada_em: datetime | None = None
    pronta_em: datetime | None = None
    retirada_em: datetime | None = None
    responsavel_id: str | None = None
    pausa_acumulada_segundos: int = 0

    def __post_init__(self) -> None:
        if not all(
            valor.strip()
            for valor in (
                self.producao_id,
                self.tenant_id,
                self.unidade_id,
                self.pedido_id,
                self.pedido_item_id,
                self.setor_id,
                self.status,
            )
        ):
            raise ValueError("producao_invalida")
        if self.quantidade <= 0 or self.tentativa < 1 or self.versao < 1:
            raise ValueError("producao_invalida")
        if self.pausa_acumulada_segundos < 0:
            raise ValueError("pausa_invalida")
        for campo in (
            "criado_em",
            "atualizado_em",
            "aceita_em",
            "iniciada_em",
            "pausa_iniciada_em",
            "pronta_em",
            "retirada_em",
        ):
            instante = getattr(self, campo)
            if instante is not None:
                if instante.tzinfo is None:
                    raise ValueError("timestamp_invalido")
                object.__setattr__(self, campo, instante.astimezone(timezone.utc))


@dataclass(frozen=True)
class IndicadorSLA:
    estado: EstadoSLA
    decorrido_segundos: int
    restante_segundos: int | None
    percentual: float | None


@dataclass(frozen=True)
class ItemFilaKDS:
    producao: ProducaoItem
    setor: SetorProducao
    sla: IndicadorSLA


@dataclass(frozen=True)
class FilaKDS:
    itens: tuple[ItemFilaKDS, ...]
    atualizado_em: datetime
    degradado: bool = False
    somente_leitura: bool = False
    motivo_degradacao: str | None = None

    def __post_init__(self) -> None:
        if self.atualizado_em.tzinfo is None:
            raise ValueError("timestamp_invalido")
        object.__setattr__(
            self, "atualizado_em", self.atualizado_em.astimezone(timezone.utc)
        )
        if self.degradado and not self.somente_leitura:
            raise ValueError("modo_degradado_deve_ser_somente_leitura")
