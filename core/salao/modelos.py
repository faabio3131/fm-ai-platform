"""Contratos imutaveis para mesas, comandas e fechamento do salao V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from .erros import ErroSalao


class StatusMesa(StrEnum):
    LIVRE = "livre"
    OCUPADA = "ocupada"
    INATIVA = "inativa"


class StatusComanda(StrEnum):
    ABERTA = "aberta"
    EM_CONSUMO = "em_consumo"
    CONTA_SOLICITADA = "conta_solicitada"
    FECHAMENTO_EM_ANDAMENTO = "fechamento_em_andamento"
    PARCIALMENTE_PAGA = "parcialmente_paga"
    FECHADA = "fechada"
    CANCELADA = "cancelada"


class MetodoFechamento(StrEnum):
    DINHEIRO = "dinheiro"
    PIX = "pix"
    CARTAO_CREDITO = "cartao_credito"
    CARTAO_DEBITO = "cartao_debito"
    VOUCHER = "voucher"
    RECEBIMENTO_POSTERIOR = "recebimento_posterior"


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ErroSalao("timestamp_invalido")
    return valor.astimezone(timezone.utc)


def _dinheiro(valor: Decimal) -> Decimal:
    if not isinstance(valor, Decimal):
        raise ErroSalao("valor_deve_ser_decimal")
    return valor.quantize(Decimal("0.01"))


@dataclass(frozen=True)
class Mesa:
    mesa_id: str
    tenant_id: str
    unidade_id: str
    codigo: str
    capacidade: int
    status: StatusMesa
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    versao: int
    nome: str | None = None
    posicao_x: Decimal | None = None
    posicao_y: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.mesa_id or not self.tenant_id or not self.unidade_id or not self.codigo.strip():
            raise ErroSalao("mesa_invalida")
        if self.capacidade < 1 or self.versao < 1:
            raise ErroSalao("mesa_invalida")
        object.__setattr__(self, "criado_em", _utc(self.criado_em))
        object.__setattr__(self, "atualizado_em", _utc(self.atualizado_em))


@dataclass(frozen=True)
class Comanda:
    comanda_id: str
    tenant_id: str
    unidade_id: str
    numero: str
    status: StatusComanda
    responsavel_id: str
    aberta_em: datetime
    total: Decimal
    saldo: Decimal
    versao: int
    mesa_id: str | None = None
    fechada_em: datetime | None = None
    recebimento_posterior_autorizado: bool = False

    def __post_init__(self) -> None:
        if not self.comanda_id or not self.numero.strip() or not self.responsavel_id:
            raise ErroSalao("comanda_invalida")
        if self.versao < 1:
            raise ErroSalao("comanda_invalida")
        total = _dinheiro(self.total)
        saldo = _dinheiro(self.saldo)
        if total < Decimal(0) or saldo < Decimal(0) or saldo > total:
            raise ErroSalao("saldo_comanda_invalido")
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "saldo", saldo)
        object.__setattr__(self, "aberta_em", _utc(self.aberta_em))
        if self.fechada_em is not None:
            object.__setattr__(self, "fechada_em", _utc(self.fechada_em))


@dataclass(frozen=True)
class ParticipanteComanda:
    participante_id: str
    tenant_id: str
    unidade_id: str
    comanda_id: str
    ordem: int
    cliente_id: str | None = None
    apelido: str | None = None
    quota: Decimal | None = None

    def __post_init__(self) -> None:
        if self.ordem < 1:
            raise ErroSalao("participante_invalido")
        if self.quota is not None:
            quota = _dinheiro(self.quota)
            if quota < Decimal(0):
                raise ErroSalao("quota_invalida")
            object.__setattr__(self, "quota", quota)


@dataclass(frozen=True)
class PedidoNaComanda:
    vinculo_id: str
    tenant_id: str
    unidade_id: str
    comanda_id: str
    pedido_id: str
    valor: Decimal
    criado_em: datetime
    participante_id: str | None = None

    def __post_init__(self) -> None:
        valor = _dinheiro(self.valor)
        if valor < Decimal(0):
            raise ErroSalao("valor_pedido_invalido")
        object.__setattr__(self, "valor", valor)
        object.__setattr__(self, "criado_em", _utc(self.criado_em))


@dataclass(frozen=True)
class ParcelaFechamento:
    parcela_id: str
    comanda_id: str
    metodo: MetodoFechamento
    valor: Decimal
    ordem: int
    participante_id: str | None = None

    def __post_init__(self) -> None:
        valor = _dinheiro(self.valor)
        if valor <= Decimal(0) or self.ordem < 1:
            raise ErroSalao("parcela_fechamento_invalida")
        object.__setattr__(self, "valor", valor)


@dataclass(frozen=True)
class PagamentoConfirmadoComanda:
    registro_id: str
    tenant_id: str
    unidade_id: str
    comanda_id: str
    pagamento_id: str
    metodo: MetodoFechamento
    valor: Decimal
    idempotency_key: str
    confirmado_em: datetime

    def __post_init__(self) -> None:
        valor = _dinheiro(self.valor)
        if valor <= Decimal(0) or not self.idempotency_key.strip():
            raise ErroSalao("pagamento_confirmado_invalido")
        object.__setattr__(self, "valor", valor)
        object.__setattr__(self, "confirmado_em", _utc(self.confirmado_em))


@dataclass(frozen=True)
class EventoSalao:
    evento_id: str
    tenant_id: str
    unidade_id: str
    agregado_tipo: str
    agregado_id: str
    tipo: str
    versao: int
    ator_id: str
    correlation_id: str
    idempotency_key: str
    ocorrido_em: datetime
    payload: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.versao < 1 or not self.idempotency_key.strip():
            raise ErroSalao("evento_invalido")
        object.__setattr__(self, "ocorrido_em", _utc(self.ocorrido_em))


@dataclass(frozen=True)
class SnapshotSalao:
    mesas: tuple[Mesa, ...]
    comandas: tuple[Comanda, ...]
