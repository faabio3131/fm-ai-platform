"""Composição transacional única para Pedido, Pagamento, Estoque e efeitos.

`RecursosTransacionaisV1` permite reutilizar uma Session cuja transação já pertence
a outra composition root. `UnitOfWorkV1` continua dono da Session quando a operação
nasce diretamente na camada de aplicação.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from types import TracebackType
from typing import Literal, Self

from sqlalchemy.orm import Session

from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.eventos.modelos import EnvelopeMensagem
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.seguranca.auditoria import EventoAuditoria
from infra.eventos.adaptador_sqlalchemy import (
    RepositorioDLQSQLAlchemy,
    RepositorioInboxSQLAlchemy,
    RepositorioOutboxSQLAlchemy,
)
from infra.gerente_ia.persistencia_sqlalchemy import ConsumidorEventosCoreSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


class RecursosTransacionaisV1:
    """Repositories autoritativos ligados à mesma Session, sem assumir o commit."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.pedidos = RepositorioPedidosSQLAlchemy(session)
        self.pagamentos = RepositorioPagamentosSQLAlchemy(session)
        self.estoque = RepositorioLedgerSQLAlchemy(session)
        self.outbox = RepositorioOutboxSQLAlchemy(
            session, ao_adicionar=ConsumidorEventosCoreSQLAlchemy(session).consumir
        )
        self.inbox = RepositorioInboxSQLAlchemy(session)
        self.dlq = RepositorioDLQSQLAlchemy(session)
        self.auditoria = RepositorioAuditoriaSQLAlchemy(session)

    def registrar_efeitos(
        self,
        *,
        eventos: Iterable[EnvelopeMensagem] = (),
        auditorias: Iterable[EventoAuditoria] = (),
    ) -> None:
        for evento in eventos:
            self.outbox.adicionar(evento)
        for evento_auditoria in auditorias:
            self.auditoria.adicionar(evento_auditoria)


class UnitOfWorkV1:
    """Fronteira autoritativa que possui Session e commit/rollback da aplicação."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.committed = False
        self._recursos: RecursosTransacionaisV1 | None = None

    @classmethod
    def adotar_session(cls, session: Session) -> Self:
        """Faz a application boundary possuir commit/rollback de Session já aberta."""

        uow = cls(lambda: session)
        uow.session = session
        uow._recursos = RecursosTransacionaisV1(session)
        uow.pedidos = uow._recursos.pedidos
        uow.pagamentos = uow._recursos.pagamentos
        uow.estoque = uow._recursos.estoque
        uow.outbox = uow._recursos.outbox
        uow.inbox = uow._recursos.inbox
        uow.dlq = uow._recursos.dlq
        uow.auditoria = uow._recursos.auditoria
        uow.committed = False
        return uow

    @property
    def recursos(self) -> RecursosTransacionaisV1:
        if self._recursos is None:
            raise RuntimeError("UnitOfWorkV1 nao iniciado")
        return self._recursos

    def __enter__(self) -> Self:
        if self.session is not None:
            raise RuntimeError("UnitOfWorkV1 nao pode ser reutilizado enquanto aberto")
        self.session = self._session_factory()
        self._recursos = RecursosTransacionaisV1(self.session)
        self.pedidos = self._recursos.pedidos
        self.pagamentos = self._recursos.pagamentos
        self.estoque = self._recursos.estoque
        self.outbox = self._recursos.outbox
        self.inbox = self._recursos.inbox
        self.dlq = self._recursos.dlq
        self.auditoria = self._recursos.auditoria
        self.committed = False
        return self

    def registrar_efeitos(
        self,
        *,
        eventos: Iterable[EnvelopeMensagem] = (),
        auditorias: Iterable[EventoAuditoria] = (),
    ) -> None:
        self.recursos.registrar_efeitos(eventos=eventos, auditorias=auditorias)

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWorkV1 nao iniciado")
        self.session.commit()
        self.committed = True

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()
        self.committed = False

    def flush(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWorkV1 nao iniciado")
        self.session.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc, traceback
        if self.session is None:
            return False
        try:
            if exc_type is not None or not self.committed:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None
            self._recursos = None
        return False
