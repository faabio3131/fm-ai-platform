"""Serviço de configuração sem dependência do nome escolhido pelo cliente."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.seguranca.auditoria import EventoAuditoria, RepositorioAuditoria
from core.seguranca.autorizacao import AutorizarAcao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

from .adapters import RepositorioIdentidadeAssistente
from .modelos import ConfiguracaoIdentidadeAssistente


class ServicoIdentidadeAssistente:
    def __init__(
        self,
        repositorio: RepositorioIdentidadeAssistente,
        auditoria: RepositorioAuditoria | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._auditoria = auditoria
        self._autorizador = AutorizarAcao()

    def obter(self, *, contexto: ContextoExecucao) -> ConfiguracaoIdentidadeAssistente:
        configuracao = self._repositorio.obter(
            tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id
        )
        return configuracao or ConfiguracaoIdentidadeAssistente.fallback(
            tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id
        )

    def configurar(
        self,
        *,
        contexto: ContextoExecucao,
        nome_publico: str,
        atributos: dict[str, Any] | None = None,
        versao_esperada: int | None = None,
    ) -> ConfiguracaoIdentidadeAssistente:
        decisao = self._autorizador.executar(
            contexto=contexto,
            permissao=Permissao.CONFIGURACAO_ALTERAR,
            recurso="identidade_assistente_atendimento",
            tenant_recurso=contexto.tenant_id,
            unidade_recurso=contexto.unidade_id,
        )
        if not decisao.autorizado:
            raise PermissionError(decisao.codigo)
        configuracao = self._repositorio.salvar(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            nome_publico=nome_publico,
            atributos=atributos or {},
            atualizado_por=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            versao_esperada=versao_esperada,
        )
        if self._auditoria is not None:
            papel = min(contexto.papeis, key=lambda item: item.value)
            self._auditoria.adicionar(
                EventoAuditoria(
                    audit_id=str(uuid4()),
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    usuario_id=contexto.usuario_id,
                    papel_efetivo=papel,
                    acao="assistente_atendimento.configurar_identidade",
                    recurso_tipo="identidade_assistente_atendimento",
                    recurso_id=f"{contexto.tenant_id}:{contexto.unidade_id}",
                    resultado="sucesso",
                    motivo="configuracao_explicita_cliente",
                    correlation_id=contexto.correlation_id,
                    timestamp=datetime.now(timezone.utc),
                    origem="assistente_atendimento_v1",
                    politica="configuracao_tenant_unidade_v1",
                    metadata=(("versao", configuracao.versao),),
                )
            )
        return configuracao
