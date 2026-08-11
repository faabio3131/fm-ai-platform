"""Contratos puros para integração anticorrupção com marketplaces."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from .erros import ErroMarketplace

CENTAVO = Decimal("0.01")


def moeda(valor: Decimal | str | int) -> Decimal:
    convertido = Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    if convertido < 0:
        raise ErroMarketplace("valor_monetario_negativo")
    return convertido


def utc(instante: datetime) -> datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ErroMarketplace("timestamp_sem_timezone")
    return instante.astimezone(timezone.utc)


def hash_payload(payload: Mapping[str, Any]) -> str:
    canonico = json.dumps(
        dict(payload), sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(canonico).hexdigest()


class PlataformaMarketplace(StrEnum):
    IFOOD = "ifood"
    FOOD99 = "99food"
    KEETA = "keeta"


class StatusIntegracao(StrEnum):
    ATIVA = "ativa"
    PAUSADA = "pausada"
    ERRO = "erro"


class CapacidadeMarketplace(StrEnum):
    RECEBER_PEDIDO = "receber_pedido"
    CONFIRMAR = "confirmar"
    REJEITAR = "rejeitar"
    ATUALIZAR_STATUS = "atualizar_status"
    CANCELAR = "cancelar"
    RECONCILIAR = "reconciliar"


class StatusPedidoExterno(StrEnum):
    RECEBIDO = "recebido"
    CONFIRMADO = "confirmado"
    EM_PREPARO = "em_preparo"
    PRONTO = "pronto"
    DESPACHADO = "despachado"
    CONCLUIDO = "concluido"
    CANCELADO = "cancelado"
    DESCONHECIDO = "desconhecido"


@dataclass(frozen=True)
class CapacidadesMarketplace:
    acoes: frozenset[CapacidadeMarketplace]

    def suporta(self, acao: CapacidadeMarketplace) -> bool:
        return acao in self.acoes

    def exigir(self, acao: CapacidadeMarketplace) -> None:
        if not self.suporta(acao):
            raise ErroMarketplace(f"capacidade_nao_suportada:{acao.value}")


@dataclass(frozen=True)
class IntegracaoMarketplace:
    integracao_id: str
    tenant_id: str
    unidade_id: str
    plataforma: PlataformaMarketplace
    conta_externa: str
    segredo_ref: str
    capacidades: CapacidadesMarketplace
    status: StatusIntegracao = StatusIntegracao.ATIVA
    cursor: str | None = None

    def __post_init__(self) -> None:
        valores = (
            self.integracao_id,
            self.tenant_id,
            self.unidade_id,
            self.conta_externa,
            self.segredo_ref,
        )
        if any(not valor.strip() for valor in valores):
            raise ErroMarketplace("integracao_invalida")
        if any(
            marcador in self.segredo_ref.lower()
            for marcador in ("bearer ", "access_token=", "client_secret=")
        ):
            raise ErroMarketplace("segredo_deve_ser_referencia")


@dataclass(frozen=True)
class ItemMarketplace:
    item_id_externo: str
    sku: str | None
    nome: str
    quantidade: Decimal
    preco_unitario: Decimal

    def __post_init__(self) -> None:
        if not self.item_id_externo.strip() or not self.nome.strip():
            raise ErroMarketplace("item_marketplace_invalido")
        quantidade = Decimal(self.quantidade)
        if quantidade <= 0:
            raise ErroMarketplace("quantidade_invalida")
        object.__setattr__(self, "quantidade", quantidade)
        object.__setattr__(self, "preco_unitario", moeda(self.preco_unitario))


@dataclass(frozen=True)
class PedidoMarketplaceSnapshot:
    id_externo: str
    merchant_id: str
    status: StatusPedidoExterno
    total: Decimal
    itens: tuple[ItemMarketplace, ...]
    atualizado_em: datetime
    versao_externa: str | None = None

    def __post_init__(self) -> None:
        if not self.id_externo.strip() or not self.merchant_id.strip():
            raise ErroMarketplace("snapshot_marketplace_invalido")
        if not self.itens:
            raise ErroMarketplace("snapshot_sem_itens")
        object.__setattr__(self, "total", moeda(self.total))
        object.__setattr__(self, "atualizado_em", utc(self.atualizado_em))


@dataclass(frozen=True)
class EventoMarketplaceExterno:
    evento_id: str
    pedido_id_externo: str
    merchant_id: str
    codigo: str
    codigo_completo: str
    status: StatusPedidoExterno
    ocorrido_em: datetime
    payload_hash: str
    versao_externa: str | None = None

    def __post_init__(self) -> None:
        valores = (
            self.evento_id,
            self.pedido_id_externo,
            self.merchant_id,
            self.codigo,
            self.codigo_completo,
            self.payload_hash,
        )
        if any(not valor.strip() for valor in valores):
            raise ErroMarketplace("evento_marketplace_invalido")
        object.__setattr__(self, "ocorrido_em", utc(self.ocorrido_em))


@dataclass(frozen=True)
class PedidoExterno:
    integracao_id: str
    id_externo: str
    pedido_id: str
    status_externo: StatusPedidoExterno
    status_interno: str
    payload_hash: str
    recebido_em: datetime
    ultima_ocorrencia_em: datetime
    ultimo_evento_id: str
    versao_externa: str | None = None

    def __post_init__(self) -> None:
        valores = (
            self.integracao_id,
            self.id_externo,
            self.pedido_id,
            self.status_interno,
            self.payload_hash,
            self.ultimo_evento_id,
        )
        if any(not valor.strip() for valor in valores):
            raise ErroMarketplace("pedido_externo_invalido")
        object.__setattr__(self, "recebido_em", utc(self.recebido_em))
        object.__setattr__(
            self, "ultima_ocorrencia_em", utc(self.ultima_ocorrencia_em)
        )


@dataclass(frozen=True)
class ResultadoSincronizacao:
    recebidos: int
    processados: int
    duplicados: int
    retry: int
    dlq: int
    reconhecidos: int


@dataclass(frozen=True)
class ResultadoComandoMarketplace:
    idempotente: bool
    publicado: bool


@dataclass(frozen=True)
class ResultadoReconciliacao:
    pedido_externo: PedidoExterno
    alterado: bool
