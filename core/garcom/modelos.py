"""Projeções imutáveis da interface do garçom V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from .erros import ErroGarcom


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroGarcom("timestamp_invalido")
    return valor.astimezone(timezone.utc)


def _dinheiro(valor: Decimal) -> Decimal:
    if not isinstance(valor, Decimal):
        raise ErroGarcom("valor_deve_ser_decimal")
    return valor.quantize(Decimal("0.01"))


@dataclass(frozen=True)
class ResumoMesaGarcom:
    mesa_id: str
    codigo: str
    capacidade: int
    status: str
    versao: int
    nome: str | None = None
    disponivel_para_abertura: bool = False

    def __post_init__(self) -> None:
        if not self.mesa_id or not self.codigo.strip() or self.capacidade < 1 or self.versao < 1:
            raise ErroGarcom("mesa_invalida")


@dataclass(frozen=True)
class ResumoComandaGarcom:
    comanda_id: str
    mesa_id: str | None
    numero: str
    status: str
    responsavel_id: str
    total: Decimal
    saldo: Decimal
    versao: int
    propria: bool

    def __post_init__(self) -> None:
        if not self.comanda_id or not self.numero.strip() or not self.responsavel_id:
            raise ErroGarcom("comanda_invalida")
        if self.versao < 1:
            raise ErroGarcom("comanda_invalida")
        total = _dinheiro(self.total)
        saldo = _dinheiro(self.saldo)
        if total < Decimal("0.00") or saldo < Decimal("0.00") or saldo > total:
            raise ErroGarcom("saldo_comanda_invalido")
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "saldo", saldo)


@dataclass(frozen=True)
class AlertaProntoGarcom:
    producao_id: str
    pedido_id: str
    setor_id: str
    setor_nome: str
    comanda_id: str
    comanda_numero: str
    mesa_id: str | None
    mesa_codigo: str | None
    pronta_em: datetime
    versao: int

    def __post_init__(self) -> None:
        if not self.producao_id or not self.pedido_id or not self.comanda_id:
            raise ErroGarcom("alerta_pronto_invalido")
        if self.versao < 1:
            raise ErroGarcom("alerta_pronto_invalido")
        object.__setattr__(self, "pronta_em", _utc(self.pronta_em))


@dataclass(frozen=True)
class PainelGarcom:
    mesas: tuple[ResumoMesaGarcom, ...]
    comandas: tuple[ResumoComandaGarcom, ...]
    alertas_prontos: tuple[AlertaProntoGarcom, ...]
    atualizado_em: datetime
    papel: str
    kds_degradado: bool = False

    def __post_init__(self) -> None:
        if not self.papel.strip():
            raise ErroGarcom("papel_invalido")
        object.__setattr__(self, "atualizado_em", _utc(self.atualizado_em))
