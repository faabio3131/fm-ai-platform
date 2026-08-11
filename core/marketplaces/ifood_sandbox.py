"""Adapter iFood V1 sobre transporte sandbox sem rede/credenciais reais.

O contrato espelha o fluxo oficial baseado em eventos: polling, acknowledgement,
consulta do pedido e comandos de ciclo de vida. Nenhuma chamada HTTP real ocorre.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import uuid4

from .erros import ErroMarketplace, ErroMarketplaceTransitorio
from .modelos import (
    CapacidadeMarketplace,
    CapacidadesMarketplace,
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
    hash_payload,
)

IFOOD_EVENTS_BASE_URL = "https://merchant-api.ifood.com.br/events/v1.0"
IFOOD_POLLING_PATH = "/events:polling"
IFOOD_ACK_PATH = "/events/acknowledgment"

_STATUS_POR_CODIGO: dict[str, StatusPedidoExterno] = {
    "PLC": StatusPedidoExterno.RECEBIDO,
    "PLACED": StatusPedidoExterno.RECEBIDO,
    "CFM": StatusPedidoExterno.CONFIRMADO,
    "CONFIRMED": StatusPedidoExterno.CONFIRMADO,
    "RTP": StatusPedidoExterno.PRONTO,
    "READY_TO_PICKUP": StatusPedidoExterno.PRONTO,
    "DSP": StatusPedidoExterno.DESPACHADO,
    "DISPATCHED": StatusPedidoExterno.DESPACHADO,
    "CON": StatusPedidoExterno.CONCLUIDO,
    "CONCLUDED": StatusPedidoExterno.CONCLUIDO,
    "CAN": StatusPedidoExterno.CANCELADO,
    "CANCELLED": StatusPedidoExterno.CANCELADO,
}

IFOOD_CAPACIDADES = CapacidadesMarketplace(
    frozenset(
        {
            CapacidadeMarketplace.RECEBER_PEDIDO,
            CapacidadeMarketplace.CONFIRMAR,
            CapacidadeMarketplace.ATUALIZAR_STATUS,
            CapacidadeMarketplace.CANCELAR,
            CapacidadeMarketplace.RECONCILIAR,
        }
    )
)


class IfoodSandboxTransport:
    """Fila determinística que simula somente o contrato usado pelo adapter."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._eventos: list[dict[str, Any]] = []
        self._reconhecidos: set[str] = set()
        self._pedidos: dict[str, PedidoMarketplaceSnapshot] = {}
        self.comandos: list[tuple[str, str, str]] = []
        self.falhas_poll_restantes = 0
        self.falhas_consulta_restantes = 0

    def semear_pedido(
        self,
        snapshot: PedidoMarketplaceSnapshot,
        *,
        codigo: str = "PLC",
        evento_id: str | None = None,
        ocorrido_em: datetime | None = None,
    ) -> str:
        with self._lock:
            self._pedidos[snapshot.id_externo] = snapshot
            return self.emitir_evento(
                pedido_id=snapshot.id_externo,
                merchant_id=snapshot.merchant_id,
                codigo=codigo,
                evento_id=evento_id,
                ocorrido_em=ocorrido_em or snapshot.atualizado_em,
                versao_externa=snapshot.versao_externa,
            )

    def emitir_evento(
        self,
        *,
        pedido_id: str,
        merchant_id: str,
        codigo: str,
        evento_id: str | None = None,
        ocorrido_em: datetime | None = None,
        versao_externa: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        instante = ocorrido_em or datetime.now(timezone.utc)
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ErroMarketplace("timestamp_sem_timezone")
        eid = evento_id or str(uuid4())
        evento = {
            "id": eid,
            "code": codigo,
            "fullCode": codigo,
            "orderId": pedido_id,
            "merchantId": merchant_id,
            "createdAt": instante.astimezone(timezone.utc).isoformat(),
            "metadata": dict(metadata or {}),
            "version": versao_externa,
        }
        with self._lock:
            self._eventos.append(evento)
        return eid

    def atualizar_snapshot(self, snapshot: PedidoMarketplaceSnapshot) -> None:
        with self._lock:
            self._pedidos[snapshot.id_externo] = snapshot

    def polling(self, *, limite: int) -> tuple[Mapping[str, Any], ...]:
        with self._lock:
            if self.falhas_poll_restantes > 0:
                self.falhas_poll_restantes -= 1
                raise ErroMarketplaceTransitorio("ifood_poll_indisponivel")
            pendentes = [
                evento
                for evento in self._eventos
                if str(evento["id"]) not in self._reconhecidos
            ]
            return tuple(dict(evento) for evento in pendentes[:limite])

    def acknowledge(self, evento_ids: tuple[str, ...]) -> None:
        with self._lock:
            self._reconhecidos.update(evento_ids)

    def foi_reconhecido(self, evento_id: str) -> bool:
        with self._lock:
            return evento_id in self._reconhecidos

    def consultar(self, pedido_id: str) -> PedidoMarketplaceSnapshot:
        with self._lock:
            if self.falhas_consulta_restantes > 0:
                self.falhas_consulta_restantes -= 1
                raise ErroMarketplaceTransitorio("ifood_consulta_indisponivel")
            try:
                return self._pedidos[pedido_id]
            except KeyError as exc:
                raise ErroMarketplace("pedido_ifood_nao_encontrado") from exc

    def executar_comando(
        self,
        *,
        comando: str,
        pedido_id: str,
        idempotency_key: str,
        novo_status: StatusPedidoExterno | None = None,
    ) -> None:
        with self._lock:
            marcador = (comando, pedido_id, idempotency_key)
            if marcador in self.comandos:
                return
            self.comandos.append(marcador)
            if novo_status is not None:
                atual = self.consultar(pedido_id)
                self._pedidos[pedido_id] = replace(
                    atual,
                    status=novo_status,
                    atualizado_em=datetime.now(timezone.utc),
                )


class IfoodSandboxAdapter:
    def __init__(self, transport: IfoodSandboxTransport) -> None:
        self.transport = transport

    @property
    def plataforma(self) -> PlataformaMarketplace:
        return PlataformaMarketplace.IFOOD

    @property
    def capacidades(self) -> CapacidadesMarketplace:
        return IFOOD_CAPACIDADES

    @staticmethod
    def _validar_integracao(integracao: IntegracaoMarketplace) -> None:
        if integracao.plataforma is not PlataformaMarketplace.IFOOD:
            raise ErroMarketplace("integracao_plataforma_incompativel")

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int = 100
    ) -> tuple[EventoMarketplaceExterno, ...]:
        self._validar_integracao(integracao)
        eventos: list[EventoMarketplaceExterno] = []
        for bruto in self.transport.polling(limite=limite):
            codigo = str(bruto.get("code", ""))
            full_code = str(bruto.get("fullCode", codigo))
            status = _STATUS_POR_CODIGO.get(
                codigo,
                _STATUS_POR_CODIGO.get(
                    full_code, StatusPedidoExterno.DESCONHECIDO
                ),
            )
            created_at = datetime.fromisoformat(
                str(bruto["createdAt"]).replace("Z", "+00:00")
            )
            eventos.append(
                EventoMarketplaceExterno(
                    evento_id=str(bruto["id"]),
                    pedido_id_externo=str(bruto["orderId"]),
                    merchant_id=str(bruto["merchantId"]),
                    codigo=codigo,
                    codigo_completo=full_code,
                    status=status,
                    ocorrido_em=created_at,
                    payload_hash=hash_payload(bruto),
                    versao_externa=(
                        str(bruto["version"])
                        if bruto.get("version") is not None
                        else None
                    ),
                )
            )
        return tuple(eventos)

    def reconhecer_eventos(
        self, integracao: IntegracaoMarketplace, evento_ids: tuple[str, ...]
    ) -> None:
        self._validar_integracao(integracao)
        if evento_ids:
            self.transport.acknowledge(evento_ids)

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot:
        self._validar_integracao(integracao)
        snapshot = self.transport.consultar(pedido_id_externo)
        if snapshot.merchant_id != integracao.conta_externa:
            raise ErroMarketplace("pedido_de_outra_conta")
        return snapshot

    def confirmar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        idempotency_key: str,
    ) -> None:
        self.capacidades.exigir(CapacidadeMarketplace.CONFIRMAR)
        self.transport.executar_comando(
            comando="confirm",
            pedido_id=pedido_id_externo,
            idempotency_key=idempotency_key,
            novo_status=StatusPedidoExterno.CONFIRMADO,
        )

    def rejeitar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        del integracao, pedido_id_externo, motivo, idempotency_key
        self.capacidades.exigir(CapacidadeMarketplace.REJEITAR)

    def atualizar_status(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> None:
        del integracao
        self.capacidades.exigir(CapacidadeMarketplace.ATUALIZAR_STATUS)
        comandos = {
            StatusPedidoExterno.EM_PREPARO: "startPreparation",
            StatusPedidoExterno.PRONTO: "readyToPickup",
            StatusPedidoExterno.DESPACHADO: "dispatch",
        }
        comando = comandos.get(status)
        if comando is None:
            raise ErroMarketplace("status_ifood_nao_publicavel")
        self.transport.executar_comando(
            comando=comando,
            pedido_id=pedido_id_externo,
            idempotency_key=idempotency_key,
            novo_status=status,
        )

    def cancelar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        del integracao
        self.capacidades.exigir(CapacidadeMarketplace.CANCELAR)
        if not motivo.strip():
            raise ErroMarketplace("motivo_cancelamento_obrigatorio")
        self.transport.executar_comando(
            comando="requestCancellation",
            pedido_id=pedido_id_externo,
            idempotency_key=idempotency_key,
            novo_status=StatusPedidoExterno.CANCELADO,
        )
