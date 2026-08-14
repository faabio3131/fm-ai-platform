"""Identidade pública configurável do Assistente de Atendimento."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

NOME_ASSISTENTE_FALLBACK = "Assistente de Atendimento"
_ATRIBUTOS_SENSIVEIS = frozenset(
    {"senha", "password", "token", "secret", "segredo", "api_key", "authorization"}
)


def _nome_publico(valor: str) -> str:
    nome = " ".join(valor.split())
    if not nome:
        return NOME_ASSISTENTE_FALLBACK
    if len(nome) > 80:
        raise ValueError("nome_publico_assistente_muito_longo")
    return nome


def _validar_atributo(chave: str, valor: Any) -> None:
    if not chave.strip() or chave.casefold() in _ATRIBUTOS_SENSIVEIS:
        raise ValueError("atributos_assistente_invalidos")
    if not isinstance(valor, (str, int, float, bool, type(None))):
        raise TypeError("atributos_assistente_invalidos")
    if isinstance(valor, str) and len(valor) > 500:
        raise ValueError("atributos_assistente_invalidos")


@dataclass(frozen=True)
class ConfiguracaoIdentidadeAssistente:
    tenant_id: str
    unidade_id: str
    nome_publico: str = NOME_ASSISTENTE_FALLBACK
    atributos: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    versao: int = 1
    atualizado_em: datetime | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.unidade_id.strip():
            raise ValueError("escopo_assistente_invalido")
        object.__setattr__(self, "nome_publico", _nome_publico(self.nome_publico))
        if self.versao < 1:
            raise ValueError("versao_assistente_invalida")
        nomes = [chave for chave, _ in self.atributos]
        if len(nomes) != len(set(nomes)) or any(not chave.strip() for chave in nomes):
            raise ValueError("atributos_assistente_invalidos")
        if len(nomes) > 32:
            raise ValueError("atributos_assistente_invalidos")
        for chave, valor in self.atributos:
            _validar_atributo(chave, valor)
        object.__setattr__(self, "atributos", tuple(sorted(self.atributos)))
        if self.atualizado_em is not None:
            if self.atualizado_em.tzinfo is None:
                raise ValueError("timestamp_sem_timezone")
            object.__setattr__(
                self, "atualizado_em", self.atualizado_em.astimezone(timezone.utc)
            )

    @classmethod
    def fallback(cls, *, tenant_id: str, unidade_id: str) -> ConfiguracaoIdentidadeAssistente:
        return cls(tenant_id=tenant_id, unidade_id=unidade_id)
