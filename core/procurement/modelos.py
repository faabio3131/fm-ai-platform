"""Modelos imutáveis da autoridade canônica de Procurement V1."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from kordena_fiscal.domain import ExecutionScope, FiscalValidationError


def _texto(valor: str, campo: str, limite: int = 256) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise FiscalValidationError(f"{campo} obrigatorio")
    normalizado = valor.strip()
    if len(normalizado) > limite:
        raise FiscalValidationError(f"{campo} excede {limite} caracteres")
    return normalizado


def _decimal(valor: Decimal | str | int, campo: str, *, zero: bool = True) -> Decimal:
    numero = Decimal(str(valor))
    if not numero.is_finite() or numero < 0 or (not zero and numero == 0):
        raise FiscalValidationError(f"{campo} invalido")
    return numero


def _instante(valor: datetime, campo: str) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise FiscalValidationError(f"{campo} deve conter timezone")
    return valor.astimezone(timezone.utc)


class StatusPedidoCompra(StrEnum):
    RASCUNHO = "rascunho"
    APROVADO = "aprovado"
    PARCIALMENTE_RECEBIDO = "parcialmente_recebido"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"


class StatusRecebimento(StrEnum):
    DIVERGENTE = "divergente"
    PARCIAL = "parcial"
    CONCLUIDO = "concluido"
    REJEITADO = "rejeitado"
    DEVOLVIDO = "devolvido"


class TipoDivergencia(StrEnum):
    PRODUTO = "produto"
    QUANTIDADE = "quantidade"
    UNIDADE = "unidade"
    PRECO = "preco"
    DESCONTO = "desconto"
    FRETE = "frete"
    TOTAL = "total"


@dataclass(frozen=True, slots=True)
class Fornecedor:
    fornecedor_id: str
    scope: ExecutionScope
    documento: str
    nome: str
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime
    versao: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fornecedor_id", _texto(self.fornecedor_id, "fornecedor_id", 64)
        )
        object.__setattr__(self, "documento", _texto(self.documento, "documento", 32))
        object.__setattr__(self, "nome", _texto(self.nome, "nome", 256))
        object.__setattr__(self, "criado_em", _instante(self.criado_em, "criado_em"))
        object.__setattr__(
            self, "atualizado_em", _instante(self.atualizado_em, "atualizado_em")
        )
        if self.versao < 1:
            raise FiscalValidationError("versao deve ser positiva")


@dataclass(frozen=True, slots=True)
class ItemPedidoCompra:
    linha: int
    insumo_id: str
    codigo_fornecedor: str
    descricao: str
    unidade_medida: str
    quantidade: Decimal
    valor_unitario: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.linha, int)
            or isinstance(self.linha, bool)
            or self.linha < 1
        ):
            raise FiscalValidationError("linha deve ser inteira positiva")
        for campo, limite in (
            ("insumo_id", 64),
            ("codigo_fornecedor", 128),
            ("descricao", 512),
            ("unidade_medida", 16),
        ):
            object.__setattr__(self, campo, _texto(getattr(self, campo), campo, limite))
        object.__setattr__(self, "unidade_medida", self.unidade_medida.upper())
        object.__setattr__(
            self, "quantidade", _decimal(self.quantidade, "quantidade", zero=False)
        )
        object.__setattr__(
            self, "valor_unitario", _decimal(self.valor_unitario, "valor_unitario")
        )

    @property
    def total(self) -> Decimal:
        return self.quantidade * self.valor_unitario


@dataclass(frozen=True, slots=True)
class PedidoCompra:
    pedido_id: str
    scope: ExecutionScope
    fornecedor_id: str
    itens: tuple[ItemPedidoCompra, ...]
    frete: Decimal
    desconto: Decimal
    total: Decimal
    status: StatusPedidoCompra
    criado_por: str
    criado_em: datetime
    atualizado_em: datetime
    versao: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "pedido_id", _texto(self.pedido_id, "pedido_id", 64))
        object.__setattr__(
            self, "fornecedor_id", _texto(self.fornecedor_id, "fornecedor_id", 64)
        )
        object.__setattr__(
            self, "criado_por", _texto(self.criado_por, "criado_por", 128)
        )
        object.__setattr__(self, "itens", tuple(self.itens))
        if not self.itens or len({i.linha for i in self.itens}) != len(self.itens):
            raise FiscalValidationError("pedido exige linhas unicas")
        for campo in ("frete", "desconto", "total"):
            object.__setattr__(self, campo, _decimal(getattr(self, campo), campo))
        esperado = (
            sum((item.total for item in self.itens), Decimal(0))
            + self.frete
            - self.desconto
        )
        if esperado != self.total:
            raise FiscalValidationError("total do pedido diverge dos componentes")
        object.__setattr__(self, "criado_em", _instante(self.criado_em, "criado_em"))
        object.__setattr__(
            self, "atualizado_em", _instante(self.atualizado_em, "atualizado_em")
        )
        if self.versao < 1:
            raise FiscalValidationError("versao deve ser positiva")


@dataclass(frozen=True, slots=True)
class ItemRecebido:
    linha_pedido: int
    linha_fiscal: int
    insumo_id: str
    quantidade: Decimal
    unidade_medida: str
    valor_unitario: Decimal
    condicao_aceita: bool

    def __post_init__(self) -> None:
        if self.linha_pedido < 1 or self.linha_fiscal < 1:
            raise FiscalValidationError("linhas de recebimento devem ser positivas")
        object.__setattr__(self, "insumo_id", _texto(self.insumo_id, "insumo_id", 64))
        object.__setattr__(
            self,
            "unidade_medida",
            _texto(self.unidade_medida, "unidade_medida", 16).upper(),
        )
        object.__setattr__(
            self, "quantidade", _decimal(self.quantidade, "quantidade", zero=False)
        )
        object.__setattr__(
            self, "valor_unitario", _decimal(self.valor_unitario, "valor_unitario")
        )


@dataclass(frozen=True, slots=True)
class Divergencia:
    tipo: TipoDivergencia
    linha_pedido: int | None
    esperado: str
    encontrado: str


@dataclass(frozen=True, slots=True)
class RecebimentoCompra:
    recebimento_id: str
    scope: ExecutionScope
    pedido_id: str
    inbound_id: str
    chave_acesso: str
    idempotency_key: str
    itens: tuple[ItemRecebido, ...]
    divergencias: tuple[Divergencia, ...]
    status: StatusRecebimento
    confirmado_por: str
    confirmado_em: datetime
    versao: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for campo, limite in (
            ("recebimento_id", 64),
            ("pedido_id", 64),
            ("inbound_id", 64),
            ("chave_acesso", 64),
            ("idempotency_key", 160),
            ("confirmado_por", 128),
        ):
            object.__setattr__(self, campo, _texto(getattr(self, campo), campo, limite))
        object.__setattr__(self, "itens", tuple(self.itens))
        object.__setattr__(self, "divergencias", tuple(self.divergencias))
        object.__setattr__(
            self, "confirmado_em", _instante(self.confirmado_em, "confirmado_em")
        )
        seguros = {
            str(k): v
            for k, v in self.metadata.items()
            if isinstance(v, (str, int, float, bool, type(None)))
            and not any(
                x in str(k).lower()
                for x in ("senha", "token", "secret", "authorization")
            )
        }
        object.__setattr__(
            self, "metadata", MappingProxyType(dict(sorted(seguros.items())))
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "scope": self.scope.partition_key,
            "pedido": self.pedido_id,
            "inbound": self.inbound_id,
            "itens": [
                (
                    i.linha_pedido,
                    i.linha_fiscal,
                    i.insumo_id,
                    str(i.quantidade),
                    i.unidade_medida,
                    str(i.valor_unitario),
                    i.condicao_aceita,
                )
                for i in self.itens
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class VinculoProdutoFornecedor:
    scope: ExecutionScope
    fornecedor_id: str
    codigo_fornecedor: str
    insumo_id: str
    valido_desde: datetime
    criado_por: str

    def __post_init__(self) -> None:
        for campo, limite in (
            ("fornecedor_id", 64),
            ("codigo_fornecedor", 128),
            ("insumo_id", 64),
            ("criado_por", 128),
        ):
            object.__setattr__(self, campo, _texto(getattr(self, campo), campo, limite))
        object.__setattr__(
            self, "valido_desde", _instante(self.valido_desde, "valido_desde")
        )


@dataclass(frozen=True, slots=True)
class CustoAquisicao:
    scope: ExecutionScope
    insumo_id: str
    recebimento_id: str
    valor_unitario: Decimal
    unidade_medida: str
    politica: str
    registrado_por: str
    registrado_em: datetime

    def __post_init__(self) -> None:
        for campo, limite in (
            ("insumo_id", 64),
            ("recebimento_id", 64),
            ("unidade_medida", 16),
            ("politica", 64),
            ("registrado_por", 128),
        ):
            object.__setattr__(self, campo, _texto(getattr(self, campo), campo, limite))
        object.__setattr__(self, "unidade_medida", self.unidade_medida.upper())
        object.__setattr__(
            self, "valor_unitario", _decimal(self.valor_unitario, "valor_unitario")
        )
        object.__setattr__(
            self, "registrado_em", _instante(self.registrado_em, "registrado_em")
        )
