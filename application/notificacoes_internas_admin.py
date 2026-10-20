"""Fronteira administrativa Web para o diretório canônico de notificações internas."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from core.notificacoes_internas.modelos import (
    CanalNotificacaoInterna,
    DestinatarioNotificacaoInterna,
)
from core.notificacoes_internas.servicos import ServicoNotificacoesInternas
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretValue
from infra.notificacoes_internas.admin_sqlalchemy import (
    RepositorioNotificacoesInternasAdminSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


class AplicacaoNotificacoesInternasAdminV1:
    """Reutiliza serviço/diretório existentes e mantém commit no UoW canônico."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        master_key: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._master_key = master_key

    def _repo(
        self,
        session: Session,
    ) -> RepositorioNotificacoesInternasAdminSQLAlchemy:
        return RepositorioNotificacoesInternasAdminSQLAlchemy(
            session,
            master_key=self._master_key,
        )

    def _servico(
        self,
        session: Session,
    ) -> ServicoNotificacoesInternas:
        return ServicoNotificacoesInternas(
            diretorio=self._repo(session),
            auditoria=RepositorioAuditoriaSQLAlchemy(session),
        )

    def listar(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> tuple[DestinatarioNotificacaoInterna, ...]:
        if "notificacao_interna.gerenciar" not in {
            permissao.value for permissao in contexto.permissoes
        }:
            raise PermissionError("notificacao_interna.gerenciar obrigatoria")
        with self._session_factory() as session:
            return self._repo(session).listar(contexto=contexto)

    def configurar(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        nome_exibicao: str,
        cargo: str | None,
        contato: str,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna:
        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)
            resultado = self._servico(session).configurar_destinatario(
                contexto=contexto,
                destinatario_id=destinatario_id,
                nome_exibicao=nome_exibicao,
                cargo=cargo,
                canal=CanalNotificacaoInterna.WHATSAPP,
                contato=SecretValue(contato.strip()),
                receber_alertas_estoque=receber_alertas_estoque,
                ativo=ativo,
            )
            uow.commit()
            return resultado

    def atualizar_preferencias(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna:
        with UnitOfWorkV1(self._session_factory) as uow:
            session = _session_ativa(uow)
            resultado = self._servico(session).atualizar_preferencias(
                contexto=contexto,
                destinatario_id=destinatario_id,
                receber_alertas_estoque=receber_alertas_estoque,
                ativo=ativo,
            )
            uow.commit()
            return resultado
