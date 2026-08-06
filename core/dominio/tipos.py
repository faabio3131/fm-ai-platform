from dataclasses import dataclass
from decimal import Decimal

from .erros import ErroValidacaoDominio
from .serializacao import Serializavel


@dataclass(frozen=True)
class QuantidadeItem(Serializavel):
    valor: int

    def __post_init__(self):
        if (
            not isinstance(self.valor, int)
            or isinstance(self.valor, bool)
            or self.valor <= 0
        ):
            raise ErroValidacaoDominio("Quantidade deve ser inteira e positiva")


@dataclass(frozen=True)
class QuantidadeInsumo(Serializavel):
    valor: Decimal

    def __post_init__(self):
        if isinstance(self.valor, float):
            raise ErroValidacaoDominio("Quantidade de insumo não aceita float")
        object.__setattr__(self, "valor", Decimal(self.valor))
        if self.valor <= 0:
            raise ErroValidacaoDominio("Quantidade de insumo deve ser positiva")


@dataclass(frozen=True)
class Percentual(Serializavel):
    valor: Decimal

    def __post_init__(self):
        if isinstance(self.valor, float):
            raise ErroValidacaoDominio("Percentual não aceita float")
        object.__setattr__(self, "valor", Decimal(self.valor))
        if not Decimal(0) <= self.valor <= Decimal(100):
            raise ErroValidacaoDominio("Percentual deve estar entre 0 e 100")


@dataclass(frozen=True)
class NumeroMesa(Serializavel):
    valor: int

    def __post_init__(self):
        if not isinstance(self.valor, int) or self.valor <= 0:
            raise ErroValidacaoDominio("Número da mesa deve ser positivo")


@dataclass(frozen=True)
class PrioridadePedido(Serializavel):
    valor: int = 0

    def __post_init__(self):
        if not isinstance(self.valor, int) or not 0 <= self.valor <= 100:
            raise ErroValidacaoDominio("Prioridade deve estar entre 0 e 100")
