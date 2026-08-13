from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .erros import ValorMonetarioInvalido
from .serializacao import Serializavel


@dataclass(frozen=True)
class Dinheiro(Serializavel):
    valor: Decimal
    moeda: str = "BRL"

    def __post_init__(self) -> None:
        if isinstance(self.valor, float) or not isinstance(
            self.valor, (str, int, Decimal)
        ):
            raise ValorMonetarioInvalido(
                "Float não é aceito; use string, inteiro ou Decimal"
            )
        try:
            normalizado = Decimal(self.valor).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except Exception as exc:
            raise ValorMonetarioInvalido("Valor monetário inválido") from exc
        if not self.moeda or len(self.moeda) != 3:
            raise ValorMonetarioInvalido("Moeda deve usar código ISO de três letras")
        object.__setattr__(self, "valor", normalizado)
        object.__setattr__(self, "moeda", self.moeda.upper())

    def _compat(self, outro: "Dinheiro") -> None:
        if not isinstance(outro, Dinheiro) or self.moeda != outro.moeda:
            raise ValorMonetarioInvalido("Moedas incompatíveis")

    def __add__(self, outro: "Dinheiro") -> "Dinheiro":
        self._compat(outro)
        return Dinheiro(self.valor + outro.valor, self.moeda)

    def __sub__(self, outro: "Dinheiro") -> "Dinheiro":
        self._compat(outro)
        return Dinheiro(self.valor - outro.valor, self.moeda)

    def __mul__(self, quantidade: int | Decimal) -> "Dinheiro":
        if isinstance(quantidade, float):
            raise ValorMonetarioInvalido("Multiplicador float não é aceito")
        return Dinheiro(self.valor * Decimal(quantidade), self.moeda)

    def __lt__(self, outro: "Dinheiro") -> bool:
        self._compat(outro)
        return self.valor < outro.valor
