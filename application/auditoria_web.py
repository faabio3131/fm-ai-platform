"""Consulta Web read-only da auditoria canônica."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy

SessionFactory = Callable[[], Session]


class AplicacaoAuditoriaWebV1:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def listar(
        self,
        *,
        contexto: ContextoExecucao,
        pagina: int,
        tamanho: int,
        acao: str | None = None,
        resultado: str | None = None,
        usuario_id: str | None = None,
        recurso_tipo: str | None = None,
    ) -> tuple[tuple[EventoAuditoria, ...], bool]:
        if Permissao.ADMIN_ACESSAR not in contexto.permissoes:
            raise PermissionError("seguranca.admin_acesso_exigido")
        if Permissao.AUDITORIA_VISUALIZAR not in contexto.permissoes:
            raise PermissionError("seguranca.auditoria_visualizar_exigido")

        pagina_segura = max(1, pagina)
        tamanho_seguro = max(1, min(tamanho, 100))
        janela = min(1000, pagina_segura * tamanho_seguro + 1)

        with self._session_factory() as session:
            eventos = RepositorioAuditoriaSQLAlchemy(session).listar(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                limite=janela,
            )

        filtrados = tuple(
            evento
            for evento in eventos
            if (acao is None or evento.acao == acao)
            and (resultado is None or evento.resultado == resultado)
            and (usuario_id is None or evento.usuario_id == usuario_id)
            and (recurso_tipo is None or evento.recurso_tipo == recurso_tipo)
        )
        inicio = (pagina_segura - 1) * tamanho_seguro
        fim = inicio + tamanho_seguro
        pagina_eventos = filtrados[inicio:fim]
        tem_mais = len(filtrados) > fim
        return pagina_eventos, tem_mais
