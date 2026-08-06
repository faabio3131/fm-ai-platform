"""Identificadores nominais: tipos distintos nunca comparam como iguais."""

from dataclasses import dataclass
from uuid import UUID

from .erros import IdentificadorInvalido


@dataclass(frozen=True)
class Identificador:
    valor: str

    def __post_init__(self) -> None:
        if not isinstance(self.valor, str) or not self.valor.strip():
            raise IdentificadorInvalido("Identificador deve ser uma string não vazia")
        object.__setattr__(self, "valor", self.valor.strip())

    @classmethod
    def de(cls, valor: str | UUID):
        return cls(str(valor))

    def __str__(self) -> str:
        return self.valor

    def para_dict(self) -> str:
        return self.valor


@dataclass(frozen=True)
class TenantId(Identificador):
    pass


@dataclass(frozen=True)
class UnidadeId(Identificador):
    pass


@dataclass(frozen=True)
class PedidoId(Identificador):
    pass


@dataclass(frozen=True)
class PedidoItemId(Identificador):
    pass


@dataclass(frozen=True)
class ClienteId(Identificador):
    pass


@dataclass(frozen=True)
class ProdutoId(Identificador):
    pass


@dataclass(frozen=True)
class PagamentoId(Identificador):
    pass


@dataclass(frozen=True)
class TransacaoPagamentoId(Identificador):
    pass


@dataclass(frozen=True)
class VendaId(Identificador):
    pass


@dataclass(frozen=True)
class MesaId(Identificador):
    pass


@dataclass(frozen=True)
class ComandaId(Identificador):
    pass


@dataclass(frozen=True)
class UsuarioId(Identificador):
    pass


@dataclass(frozen=True)
class GarcomId(Identificador):
    pass


@dataclass(frozen=True)
class SetorProducaoId(Identificador):
    pass


@dataclass(frozen=True)
class ProducaoItemId(Identificador):
    pass


@dataclass(frozen=True)
class EntregaId(Identificador):
    pass


@dataclass(frozen=True)
class EntregadorId(Identificador):
    pass


@dataclass(frozen=True)
class EventoId(Identificador):
    pass


@dataclass(frozen=True)
class CorrelationId(Identificador):
    pass


@dataclass(frozen=True)
class CausationId(Identificador):
    pass


@dataclass(frozen=True)
class IdempotencyKey(Identificador):
    pass


@dataclass(frozen=True)
class CommandId(Identificador):
    pass


__all__ = [
    "Identificador",
    "TenantId",
    "UnidadeId",
    "PedidoId",
    "PedidoItemId",
    "ClienteId",
    "ProdutoId",
    "PagamentoId",
    "TransacaoPagamentoId",
    "VendaId",
    "MesaId",
    "ComandaId",
    "UsuarioId",
    "GarcomId",
    "SetorProducaoId",
    "ProducaoItemId",
    "EntregaId",
    "EntregadorId",
    "EventoId",
    "CorrelationId",
    "CausationId",
    "IdempotencyKey",
    "CommandId",
]
