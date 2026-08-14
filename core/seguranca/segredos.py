"""Resolução segura de segredos por referência.

Adapters de produção devem receber referências (por exemplo ``env:IFOOD_CLIENT_SECRET``)
em vez de gravar tokens/API keys em tabelas de configuração ou logs. A implementação
inicial usa ambiente ou mapping injetado e já define o contrato para um secret store
externo futuro.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from .erros import ReferenciaSegredoInvalida, SegredoAusente


@dataclass(frozen=True, repr=False)
class SecretValue:
    _value: str

    def __post_init__(self) -> None:
        if not self._value:
            raise SegredoAusente("segredo vazio")

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue(***)"

    def __str__(self) -> str:
        return "***"


class SecretStore(Protocol):
    def resolve(self, reference: str) -> SecretValue: ...


class ReferenceSecretStore:
    """Secret store por referência, sem persistir o valor resolvido."""

    def __init__(self, *, mapping: Mapping[str, str] | None = None) -> None:
        self._mapping = mapping or {}

    def resolve(self, reference: str) -> SecretValue:
        if not isinstance(reference, str) or ":" not in reference:
            raise ReferenciaSegredoInvalida("use referencia no formato origem:chave")
        source, key = reference.split(":", 1)
        source = source.strip().lower()
        key = key.strip()
        if not key:
            raise ReferenciaSegredoInvalida("chave de segredo ausente")

        if source == "env":
            value = os.getenv(key)
        elif source == "mapping":
            value = self._mapping.get(key)
        else:
            raise ReferenciaSegredoInvalida("origem de segredo nao suportada")

        if value is None or not str(value).strip():
            raise SegredoAusente(f"segredo indisponivel: {source}:{key}")
        return SecretValue(str(value))


def env_reference(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ReferenciaSegredoInvalida("nome de variavel vazio")
    return f"env:{cleaned}"
