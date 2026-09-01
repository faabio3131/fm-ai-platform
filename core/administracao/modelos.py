"""Modelos puros da administração empresarial do Kordena V1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType


def _texto(valor: str, *, nome: str, maximo: int) -> str:
    if not isinstance(valor, str):
        raise TypeError(f"{nome}_invalido")
    normalizado = " ".join(valor.split())
    if not normalizado or len(normalizado) > maximo:
        raise ValueError(f"{nome}_invalido")
    return normalizado


def _mapping(valor: Mapping[str, object] | None) -> Mapping[str, object]:
    return MappingProxyType(dict(valor or {}))


@dataclass(frozen=True, kw_only=True)
class EmpresaAdministrativa:
    tenant_id: str
    nome_exibicao: str
    moeda: str = "BRL"
    timezone: str = "America/Sao_Paulo"
    ativa: bool = True
    versao: int = 1
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _texto(self.tenant_id, nome="tenant_id", maximo=64))
        object.__setattr__(
            self,
            "nome_exibicao",
            _texto(self.nome_exibicao, nome="nome_exibicao", maximo=255),
        )
        moeda = self.moeda.strip().upper()
        if len(moeda) != 3 or not moeda.isalpha() or not moeda.isascii():
            raise ValueError("moeda_invalida")
        object.__setattr__(self, "moeda", moeda)
        object.__setattr__(
            self,
            "timezone",
            _texto(self.timezone, nome="timezone", maximo=80),
        )
        if self.versao < 1:
            raise ValueError("versao_invalida")


@dataclass(frozen=True, kw_only=True)
class UnidadeAdministrativa:
    tenant_id: str
    unidade_id: str
    codigo: str
    nome_fantasia: str
    tipo: str = "unidade"
    documento_fiscal: str | None = None
    telefone: str | None = None
    email: str | None = None
    endereco: Mapping[str, object] = field(default_factory=dict)
    horarios: Mapping[str, object] = field(default_factory=dict)
    ativa: bool = True
    versao: int = 1
    criado_em: datetime | None = None
    atualizado_em: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _texto(self.tenant_id, nome="tenant_id", maximo=64))
        object.__setattr__(self, "unidade_id", _texto(self.unidade_id, nome="unidade_id", maximo=64))
        object.__setattr__(self, "codigo", _texto(self.codigo, nome="codigo", maximo=64))
        object.__setattr__(
            self,
            "nome_fantasia",
            _texto(self.nome_fantasia, nome="nome_fantasia", maximo=255),
        )
        tipo = self.tipo.strip().casefold()
        if tipo not in {"matriz", "filial", "unidade"}:
            raise ValueError("tipo_unidade_invalido")
        object.__setattr__(self, "tipo", tipo)
        for nome in ("documento_fiscal", "telefone", "email"):
            valor = getattr(self, nome)
            if valor is not None:
                normalizado = " ".join(str(valor).split())
                object.__setattr__(self, nome, normalizado or None)
        object.__setattr__(self, "endereco", _mapping(self.endereco))
        object.__setattr__(self, "horarios", _mapping(self.horarios))
        if self.versao < 1:
            raise ValueError("versao_invalida")


@dataclass(frozen=True, kw_only=True)
class ConfiguracaoEstabelecimento:
    tenant_id: str
    unidade_id: str
    formas_pagamento: tuple[str, ...] = ()
    taxa_servico_percentual: Decimal = Decimal(0)
    parametros_operacionais: Mapping[str, object] = field(default_factory=dict)
    politica_financeira: Mapping[str, object] = field(default_factory=dict)
    versao: int = 1
    atualizado_em: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _texto(self.tenant_id, nome="tenant_id", maximo=64))
        object.__setattr__(self, "unidade_id", _texto(self.unidade_id, nome="unidade_id", maximo=64))
        formas = tuple(
            dict.fromkeys(
                str(item).strip().casefold()
                for item in self.formas_pagamento
                if str(item).strip()
            )
        )
        object.__setattr__(self, "formas_pagamento", formas)
        taxa = Decimal(self.taxa_servico_percentual)
        if not taxa.is_finite() or taxa < 0 or taxa > 100:
            raise ValueError("taxa_servico_invalida")
        object.__setattr__(self, "taxa_servico_percentual", taxa)
        object.__setattr__(
            self,
            "parametros_operacionais",
            _mapping(self.parametros_operacionais),
        )
        object.__setattr__(
            self,
            "politica_financeira",
            _mapping(self.politica_financeira),
        )
        if self.versao < 1:
            raise ValueError("versao_invalida")
