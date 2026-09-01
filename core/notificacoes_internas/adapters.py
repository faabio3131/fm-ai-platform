"""Portas da autoridade de notificações internas."""

from __future__ import annotations

from typing import Protocol

from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretValue

from .modelos import CanalNotificacaoInterna, DestinatarioNotificacaoInterna


class PortaDiretorioNotificacoesInternas(Protocol):
    def configurar(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        nome_exibicao: str,
        cargo: str | None,
        canal: CanalNotificacaoInterna,
        contato: SecretValue,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna: ...

    def atualizar_preferencias(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna: ...

    def obter(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
    ) -> DestinatarioNotificacaoInterna | None: ...

    def listar_alertas_estoque(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> tuple[DestinatarioNotificacaoInterna, ...]: ...

    def resolver_contato(
        self,
        *,
        contexto: ContextoExecucao,
        referencia_contato: str,
    ) -> SecretValue: ...


class PortaEntregaNotificacaoInterna(Protocol):
    def enviar(
        self,
        *,
        contexto: ContextoExecucao,
        referencia_contato: str,
        texto: str,
        idempotency_key: str,
    ) -> str: ...
