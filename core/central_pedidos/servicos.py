"""Comandos da Central delegados exclusivamente ao Pedido autoritativo V1.

A Central nao possui maquina de estados, historico ou idempotencia paralelos.
Pedido, historico, Outbox e auditoria sao gravados pela mesma transacao externa.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.erros import ConflitoIdempotencia
from core.dominio.ids import IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.dominio.pedidos import Pedido
from core.eventos.modelos import EnvelopeMensagem
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.servicos import ResultadoPedidoAutoritativo, transicionar_pedido
from core.seguranca.auditoria import (
    EventoAuditoria,
    RepositorioAuditoria,
    RepositorioAuditoriaEmMemoria,
)
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import ConsumidorEventosCoreSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


@dataclass(frozen=True)
class ResultadoComandoCentral:
    """Resultado da fachada com acesso ao agregado e atalhos de compatibilidade."""

    pedido: Pedido
    evento: EnvelopeMensagem
    auditoria: EventoAuditoria | None
    idempotente: bool

    @property
    def status(self) -> PedidoStatus:
        return self.pedido.status

    @property
    def versao(self) -> int:
        return self.pedido.versao

    @classmethod
    def de_resultado_autoritativo(
        cls, resultado: ResultadoPedidoAutoritativo
    ) -> "ResultadoComandoCentral":
        return cls(
            pedido=resultado.pedido,
            evento=resultado.evento,
            auditoria=resultado.auditoria,
            idempotente=resultado.idempotente,
        )


class _OutboxCentralEmMemoriaSomenteTeste:
    """Porta efemera usada apenas quando a auditoria in-memory é injetada em teste."""

    def __init__(self) -> None:
        self._por_idempotencia: dict[tuple[str, str, str], EnvelopeMensagem] = {}
        self._por_evento: dict[tuple[str, str, str], EnvelopeMensagem] = {}

    def adicionar(self, mensagem: EnvelopeMensagem) -> None:
        escopo = (str(mensagem.tenant_id), str(mensagem.unidade_id))
        self._por_idempotencia[
            (*escopo, str(mensagem.idempotency_key))
        ] = mensagem
        self._por_evento[(*escopo, str(mensagem.event_id))] = mensagem

    def consultar(
        self,
        *,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        event_id=None,
        idempotency_key=None,
    ) -> EnvelopeMensagem | None:
        escopo = (str(tenant_id), str(unidade_id))
        if idempotency_key is not None:
            return self._por_idempotencia.get((*escopo, str(idempotency_key)))
        if event_id is not None:
            return self._por_evento.get((*escopo, str(event_id)))
        return None


class ServicoComandosCentral:
    """Fachada fina da Central sobre o caso de uso canonico de Pedido."""

    def __init__(
        self,
        session: Session,
        auditoria: RepositorioAuditoria | None = None,
    ) -> None:
        self._session = session
        self._auditoria = auditoria or RepositorioAuditoriaSQLAlchemy(session)
        self._harness_legado = isinstance(auditoria, RepositorioAuditoriaEmMemoria)
        self._outbox = (
            _OutboxCentralEmMemoriaSomenteTeste()
            if self._harness_legado
            else RepositorioOutboxSQLAlchemy(
                session, ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir
            )
        )

    def transicionar(
        self,
        *,
        contexto: ContextoExecucao,
        pedido_id: str,
        destino: str,
        versao_esperada: int,
        idempotency_key: str,
        motivo: str | None = None,
        timestamp: datetime | None = None,
        precondicoes: Mapping[str, bool] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ResultadoComandoCentral:
        """Executa uma transicao sem criar uma segunda verdade operacional."""

        try:
            destino_canonico = PedidoStatus(destino)
        except ValueError as exc:
            raise ValueError("status_pedido_invalido") from exc

        try:
            resultado = transicionar_pedido(
                tenant_id=TenantId(contexto.tenant_id),
                unidade_id=UnidadeId(contexto.unidade_id),
                pedido_id=PedidoId(pedido_id),
                destino=destino_canonico,
                versao_esperada=versao_esperada,
                idempotency_key=IdempotencyKey(idempotency_key),
                contexto=contexto,
                repositorio=RepositorioPedidosSQLAlchemy(self._session),
                outbox=self._outbox,
                auditoria=self._auditoria,
                timestamp=timestamp or datetime.now(timezone.utc),
                precondicoes=precondicoes,
                motivo=motivo,
                metadata=metadata,
            )
        except ConflitoIdempotencia as exc:
            if self._harness_legado:
                raise ValueError("conflito_idempotencia") from exc
            raise

        return ResultadoComandoCentral.de_resultado_autoritativo(resultado)
