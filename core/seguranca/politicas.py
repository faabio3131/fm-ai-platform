"""Concessoes efetivas e alçadas puras."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.dominio.dinheiro import Dinheiro
from core.dominio.serializacao import Serializavel

from .permissoes import Papel, Permissao


@dataclass(frozen=True)
class Concessao:
    adicionais: frozenset[Permissao] = field(default_factory=frozenset)
    negadas: frozenset[Permissao] = field(default_factory=frozenset)
    unidades: frozenset[str] = field(default_factory=frozenset)
    valido_ate: datetime | None = None
    limites: tuple[tuple[Permissao, Dinheiro], ...] = field(default_factory=tuple)
    criticas_bloqueadas: frozenset[Permissao] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ResultadoAlcada(Serializavel):
    autorizado: bool
    confirmacao_exigida: bool
    papel_aprovador: Papel | None
    motivo: str
    limite_aplicado: Dinheiro | None
    valor_analisado: Dinheiro | None
    politica: str
    versao: int = 1
    metadata: tuple[tuple[str, Any], ...] = field(default_factory=tuple)


class PoliticaAlcada:
    def __init__(self, limites: dict[Permissao, Dinheiro] | None = None) -> None:
        self._limites = limites or {}

    def avaliar(self, permissao: Permissao, valor: Dinheiro | None) -> ResultadoAlcada:
        limite = self._limites.get(permissao)
        if limite is None or valor is None or not limite < valor:
            return ResultadoAlcada(
                True, False, None, "Dentro da alcada", limite, valor, "alcada_padrao"
            )
        return ResultadoAlcada(
            False,
            True,
            Papel.GERENTE,
            "Aprovacao adicional exigida",
            limite,
            valor,
            "alcada_padrao",
        )
