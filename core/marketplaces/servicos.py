"""Orquestração segura de inbox/outbox, adapters e PedidoExterno."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.dominio.tempo import Clock
from core.eventos.modelos import EnvelopeMensagem, StatusProcessamento
from core.eventos.observabilidade import MetricasEventos
from core.eventos.processador import ProcessadorMensagens, RegistroHandlers
from core.eventos.repositorios import (
    RepositorioDLQ,
    RepositorioInbox,
    RepositorioOutbox,
    StatusOutbox,
)

from .adapters import (
    PortaPedidosMarketplaceInternos,
    RegistroAdaptersMarketplace,
)
from .erros import ErroMarketplace, ErroMarketplacePermanente
from .modelos import (
    CapacidadeMarketplace,
    IntegracaoMarketplace,
    PedidoExterno,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    ResultadoComandoMarketplace,
    ResultadoReconciliacao,
    ResultadoSincronizacao,
    StatusIntegracao,
    StatusPedidoExterno,
)
from .repositorios import RepositorioIntegracoesMarketplace, RepositorioPedidosExternos
from .retry import PoliticaRetryMarketplace


def _hash_curto(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()[:24]


def _plataforma(valor: str) -> PlataformaMarketplace:
    try:
        return PlataformaMarketplace(valor)
    except ValueError as exc:
        raise ErroMarketplacePermanente("plataforma_externa_desconhecida") from exc


def _status(valor: str) -> StatusPedidoExterno:
    try:
        return StatusPedidoExterno(valor)
    except ValueError as exc:
        raise ErroMarketplacePermanente("status_externo_invalido") from exc


class ServicoMarketplaces:
    def __init__(
        self,
        *,
        integracoes: RepositorioIntegracoesMarketplace,
        pedidos_externos: RepositorioPedidosExternos,
        pedidos_internos: PortaPedidosMarketplaceInternos,
        adapters: RegistroAdaptersMarketplace,
        inbox: RepositorioInbox,
        outbox: RepositorioOutbox,
        dlq: RepositorioDLQ,
        metricas: MetricasEventos,
        clock: Clock,
        retry: PoliticaRetryMarketplace,
    ) -> None:
        self._integracoes = integracoes
        self._pedidos_externos = pedidos_externos
        self._pedidos_internos = pedidos_internos
        self._adapters = adapters
        self._inbox = inbox
        self._outbox = outbox
        self._dlq = dlq
        self._metricas = metricas
        self._clock = clock
        self._retry = retry
        self._adiados: dict[IdempotencyKey, datetime] = {}
        handlers = RegistroHandlers()
        handlers.registrar("marketplace.external.event", self._processar_evento)
        self._processador = ProcessadorMensagens(
            inbox=inbox,
            dlq=dlq,
            handlers=handlers,
            retry=retry,
            metricas=metricas,
            clock=clock,
        )

    def _integracao(
        self, *, tenant_id: str, unidade_id: str, integracao_id: str
    ) -> IntegracaoMarketplace:
        integracao = self._integracoes.obter(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
        )
        if integracao is None:
            raise ErroMarketplace("recurso_indisponivel")
        if integracao.status is not StatusIntegracao.ATIVA:
            raise ErroMarketplace("integracao_inativa")
        return integracao

    @staticmethod
    def _envelope(
        integracao: IntegracaoMarketplace,
        evento,
    ) -> EnvelopeMensagem:
        chave = IdempotencyKey.de(
            f"marketplace:{integracao.integracao_id}:{evento.evento_id}"
        )
        correlation = CorrelationId.de(
            f"mkt-{_hash_curto(str(chave))}"
        )
        payload = {
            "integracao_id": integracao.integracao_id,
            "plataforma": integracao.plataforma.value,
            "pedido_id_externo": evento.pedido_id_externo,
            "merchant_id": evento.merchant_id,
            "codigo": evento.codigo,
            "codigo_completo": evento.codigo_completo,
            "status": evento.status.value,
            "payload_hash": evento.payload_hash,
            "versao_externa": evento.versao_externa,
            "ocorrido_em": evento.ocorrido_em.isoformat(),
        }
        return EnvelopeMensagem(
            event_id=EventoId.de(
                f"mkt-in-{_hash_curto(integracao.integracao_id + ':' + evento.evento_id)}"
            ),
            event_type="marketplace.external.event",
            aggregate_id=evento.pedido_id_externo,
            aggregate_type="PedidoExterno",
            tenant_id=TenantId.de(integracao.tenant_id),
            unidade_id=UnidadeId.de(integracao.unidade_id),
            correlation_id=correlation,
            causation_id=None,
            idempotency_key=chave,
            occurred_at=evento.ocorrido_em,
            payload=payload,
        )

    def sincronizar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        limite: int = 100,
    ) -> ResultadoSincronizacao:
        integracao = self._integracao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
        )
        integracao.capacidades.exigir(CapacidadeMarketplace.RECEBER_PEDIDO)
        adapter = self._adapters.obter(integracao.plataforma)
        eventos = adapter.receber_eventos(integracao, limite=limite)
        agora = self._clock.agora()
        reconhecidos: list[str] = []
        processados = duplicados = retry = dlq = 0
        for evento in eventos:
            envelope = self._envelope(integracao, evento)
            adiado_ate = self._adiados.get(envelope.idempotency_key)
            if adiado_ate is not None and agora < adiado_ate:
                retry += 1
                continue
            resultado = self._processador.processar(envelope)
            if resultado.status is StatusProcessamento.PROCESSADO:
                processados += 1
                reconhecidos.append(evento.evento_id)
                self._adiados.pop(envelope.idempotency_key, None)
            elif resultado.status is StatusProcessamento.DUPLICADO:
                duplicados += 1
                reconhecidos.append(evento.evento_id)
                self._adiados.pop(envelope.idempotency_key, None)
            elif resultado.status is StatusProcessamento.RETRY:
                retry += 1
                if resultado.next_attempt_at is not None:
                    self._adiados[envelope.idempotency_key] = resultado.next_attempt_at
            else:
                dlq += 1
                reconhecidos.append(evento.evento_id)
                self._adiados.pop(envelope.idempotency_key, None)
        adapter.reconhecer_eventos(integracao, tuple(reconhecidos))
        return ResultadoSincronizacao(
            recebidos=len(eventos),
            processados=processados,
            duplicados=duplicados,
            retry=retry,
            dlq=dlq,
            reconhecidos=len(reconhecidos),
        )

    def _processar_evento(self, mensagem: EnvelopeMensagem) -> None:
        payload = mensagem.payload
        integracao = self._integracao(
            tenant_id=str(mensagem.tenant_id),
            unidade_id=str(mensagem.unidade_id),
            integracao_id=str(payload["integracao_id"]),
        )
        if _plataforma(str(payload["plataforma"])) is not integracao.plataforma:
            raise ErroMarketplacePermanente("plataforma_divergente")
        merchant_id = str(payload["merchant_id"])
        if merchant_id != integracao.conta_externa:
            raise ErroMarketplacePermanente("evento_de_outra_conta")
        adapter = self._adapters.obter(integracao.plataforma)
        pedido_id_externo = str(payload["pedido_id_externo"])
        status_evento = _status(str(payload["status"]))
        ocorrido_em = datetime.fromisoformat(str(payload["ocorrido_em"]))
        existente = self._pedidos_externos.obter(
            integracao_id=integracao.integracao_id,
            id_externo=pedido_id_externo,
        )
        snapshot = adapter.consultar_pedido(integracao, pedido_id_externo)
        if existente is not None and ocorrido_em < existente.ultima_ocorrencia_em:
            self._reconciliar_snapshot(
                integracao=integracao,
                existente=existente,
                snapshot=snapshot,
                idempotency_key=f"reconcile:out-of-order:{mensagem.event_id}",
            )
            return

        if existente is None:
            pedido_id, _ = self._pedidos_internos.criar_ou_obter(
                tenant_id=integracao.tenant_id,
                unidade_id=integracao.unidade_id,
                integracao_id=integracao.integracao_id,
                snapshot=snapshot,
                idempotency_key=(
                    f"marketplace:pedido:{integracao.integracao_id}:{pedido_id_externo}"
                ),
            )
            recebido_em = self._clock.agora()
        else:
            pedido_id = existente.pedido_id
            recebido_em = existente.recebido_em

        status_aplicado = (
            snapshot.status
            if status_evento is StatusPedidoExterno.DESCONHECIDO
            else status_evento
        )
        status_interno = self._pedidos_internos.atualizar_status_marketplace(
            tenant_id=integracao.tenant_id,
            unidade_id=integracao.unidade_id,
            pedido_id=pedido_id,
            status=status_aplicado,
            idempotency_key=f"marketplace:status:{mensagem.idempotency_key}",
        )
        novo = PedidoExterno(
            integracao_id=integracao.integracao_id,
            id_externo=pedido_id_externo,
            pedido_id=pedido_id,
            status_externo=status_aplicado,
            status_interno=status_interno,
            payload_hash=str(payload["payload_hash"]),
            recebido_em=recebido_em,
            ultima_ocorrencia_em=ocorrido_em,
            ultimo_evento_id=str(mensagem.event_id),
            versao_externa=(
                str(payload["versao_externa"])
                if payload.get("versao_externa") is not None
                else None
            ),
        )
        self._pedidos_externos.salvar(novo)

    def _reconciliar_snapshot(
        self,
        *,
        integracao: IntegracaoMarketplace,
        existente: PedidoExterno,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> ResultadoReconciliacao:
        if snapshot.atualizado_em < existente.ultima_ocorrencia_em:
            return ResultadoReconciliacao(existente, False)
        status_interno = self._pedidos_internos.reconciliar_marketplace(
            tenant_id=integracao.tenant_id,
            unidade_id=integracao.unidade_id,
            pedido=existente,
            snapshot=snapshot,
            idempotency_key=idempotency_key,
        )
        alterado = (
            snapshot.status is not existente.status_externo
            or status_interno != existente.status_interno
            or snapshot.atualizado_em != existente.ultima_ocorrencia_em
        )
        if not alterado:
            return ResultadoReconciliacao(existente, False)
        novo = replace(
            existente,
            status_externo=snapshot.status,
            status_interno=status_interno,
            ultima_ocorrencia_em=snapshot.atualizado_em,
            versao_externa=snapshot.versao_externa,
        )
        self._pedidos_externos.salvar(novo)
        return ResultadoReconciliacao(novo, True)

    def reconciliar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        pedido_id_externo: str,
    ) -> ResultadoReconciliacao:
        integracao = self._integracao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
        )
        integracao.capacidades.exigir(CapacidadeMarketplace.RECONCILIAR)
        existente = self._pedidos_externos.obter(
            integracao_id=integracao_id, id_externo=pedido_id_externo
        )
        if existente is None:
            raise ErroMarketplace("pedido_externo_nao_encontrado")
        adapter = self._adapters.obter(integracao.plataforma)
        snapshot = adapter.consultar_pedido(integracao, pedido_id_externo)
        return self._reconciliar_snapshot(
            integracao=integracao,
            existente=existente,
            snapshot=snapshot,
            idempotency_key=f"marketplace:reconcile:{integracao_id}:{pedido_id_externo}",
        )

    def _executar_saida(
        self,
        *,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        acao: CapacidadeMarketplace,
        idempotency_key: str,
        executar: Callable[[], None],
    ) -> ResultadoComandoMarketplace:
        if not idempotency_key.strip():
            raise ErroMarketplace("idempotency_key_obrigatoria")
        integracao.capacidades.exigir(acao)
        event_id = EventoId.de(f"mkt-out-{_hash_curto(idempotency_key)}")
        mensagem = EnvelopeMensagem(
            event_id=event_id,
            event_type=f"marketplace.command.{acao.value}",
            aggregate_id=pedido_id_externo,
            aggregate_type="PedidoExterno",
            tenant_id=TenantId.de(integracao.tenant_id),
            unidade_id=UnidadeId.de(integracao.unidade_id),
            correlation_id=CorrelationId.de(
                f"mkt-out-corr-{_hash_curto(idempotency_key)}"
            ),
            causation_id=CausationId.de(f"marketplace:{integracao.integracao_id}"),
            idempotency_key=IdempotencyKey.de(idempotency_key),
            occurred_at=self._clock.agora(),
            payload={
                "integracao_id": integracao.integracao_id,
                "plataforma": integracao.plataforma.value,
                "pedido_id_externo": pedido_id_externo,
                "acao": acao.value,
            },
        )
        registro = self._outbox.adicionar(mensagem)
        if registro.status is StatusOutbox.PUBLICADO:
            return ResultadoComandoMarketplace(idempotente=True, publicado=True)
        self._outbox.marcar_tentativa(event_id)
        executar()
        self._outbox.marcar_publicado(event_id)
        return ResultadoComandoMarketplace(
            idempotente=registro.tentativas > 1,
            publicado=True,
        )

    def confirmar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        pedido_id_externo: str,
        idempotency_key: str,
    ) -> ResultadoComandoMarketplace:
        integracao = self._integracao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
        )
        adapter = self._adapters.obter(integracao.plataforma)
        return self._executar_saida(
            integracao=integracao,
            pedido_id_externo=pedido_id_externo,
            acao=CapacidadeMarketplace.CONFIRMAR,
            idempotency_key=idempotency_key,
            executar=lambda: adapter.confirmar(
                integracao,
                pedido_id_externo,
                idempotency_key=idempotency_key,
            ),
        )

    def publicar_status(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        pedido_id_externo: str,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> ResultadoComandoMarketplace:
        integracao = self._integracao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
        )
        adapter = self._adapters.obter(integracao.plataforma)
        return self._executar_saida(
            integracao=integracao,
            pedido_id_externo=pedido_id_externo,
            acao=CapacidadeMarketplace.ATUALIZAR_STATUS,
            idempotency_key=idempotency_key,
            executar=lambda: adapter.atualizar_status(
                integracao,
                pedido_id_externo,
                status=status,
                idempotency_key=idempotency_key,
            ),
        )

    def cancelar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        pedido_id_externo: str,
        motivo: str,
        idempotency_key: str,
    ) -> ResultadoComandoMarketplace:
        integracao = self._integracao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            integracao_id=integracao_id,
        )
        adapter = self._adapters.obter(integracao.plataforma)
        return self._executar_saida(
            integracao=integracao,
            pedido_id_externo=pedido_id_externo,
            acao=CapacidadeMarketplace.CANCELAR,
            idempotency_key=idempotency_key,
            executar=lambda: adapter.cancelar(
                integracao,
                pedido_id_externo,
                motivo=motivo,
                idempotency_key=idempotency_key,
            ),
        )
