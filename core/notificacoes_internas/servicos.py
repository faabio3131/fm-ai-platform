"""Serviço determinístico de configuração do diretório interno."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from core.seguranca.auditoria import (
    EventoAuditoria,
    RepositorioAuditoria,
    sanitizar_metadata,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from core.seguranca.segredos import SecretValue

from .adapters import PortaDiretorioNotificacoesInternas
from .modelos import CanalNotificacaoInterna, DestinatarioNotificacaoInterna


def _audit_id(acao: str, recurso_id: str, correlation_id: str) -> str:
    digest = hashlib.sha256(
        f"{acao}:{recurso_id}:{correlation_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"audit_notif_{digest}"


class ServicoNotificacoesInternas:
    def __init__(
        self,
        *,
        diretorio: PortaDiretorioNotificacoesInternas,
        auditoria: RepositorioAuditoria | None = None,
    ) -> None:
        self._diretorio = diretorio
        self._auditoria = auditoria

    @staticmethod
    def _autorizar(contexto: ContextoExecucao) -> None:
        if Permissao.NOTIFICACAO_INTERNA_GERENCIAR not in contexto.permissoes:
            raise PermissionError("notificacao_interna.gerenciar obrigatoria")

    def _auditar(
        self,
        *,
        contexto: ContextoExecucao,
        acao: str,
        destinatario: DestinatarioNotificacaoInterna,
    ) -> None:
        if self._auditoria is None:
            return
        self._auditoria.adicionar(
            EventoAuditoria(
                audit_id=_audit_id(
                    acao,
                    destinatario.destinatario_id,
                    contexto.correlation_id,
                ),
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                usuario_id=contexto.usuario_id,
                papel_efetivo=next(iter(contexto.papeis), None),
                acao=acao,
                recurso_tipo="DestinatarioNotificacaoInterna",
                recurso_id=destinatario.destinatario_id,
                resultado="sucesso",
                motivo="configuracao_notificacao_interna",
                correlation_id=contexto.correlation_id,
                timestamp=datetime.now(timezone.utc),
                origem="notificacoes_internas_v1",
                politica="sd_adr_006",
                metadata=sanitizar_metadata(
                    {
                        "canal": destinatario.canal.value,
                        "ativo": destinatario.ativo,
                        "receber_alertas_estoque": (
                            destinatario.receber_alertas_estoque
                        ),
                    },
                    rejeitar=True,
                ),
            )
        )

    def configurar_destinatario(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        nome_exibicao: str,
        cargo: str | None,
        canal: CanalNotificacaoInterna,
        contato: SecretValue,
        receber_alertas_estoque: bool = True,
        ativo: bool = True,
    ) -> DestinatarioNotificacaoInterna:
        self._autorizar(contexto)
        destinatario = self._diretorio.configurar(
            contexto=contexto,
            destinatario_id=destinatario_id,
            nome_exibicao=nome_exibicao,
            cargo=cargo,
            canal=canal,
            contato=contato,
            receber_alertas_estoque=receber_alertas_estoque,
            ativo=ativo,
        )
        self._auditar(
            contexto=contexto,
            acao="notificacao_interna.destinatario_configurar",
            destinatario=destinatario,
        )
        return destinatario

    def atualizar_preferencias(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna:
        self._autorizar(contexto)
        destinatario = self._diretorio.atualizar_preferencias(
            contexto=contexto,
            destinatario_id=destinatario_id,
            receber_alertas_estoque=receber_alertas_estoque,
            ativo=ativo,
        )
        self._auditar(
            contexto=contexto,
            acao="notificacao_interna.destinatario_atualizar",
            destinatario=destinatario,
        )
        return destinatario

    def listar_alertas_estoque(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> tuple[DestinatarioNotificacaoInterna, ...]:
        return self._diretorio.listar_alertas_estoque(contexto=contexto)
