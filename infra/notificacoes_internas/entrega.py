"""Boundary de entrega das notificações internas via Meta/WhatsApp."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from core.notificacoes_internas.adapters import (
    PortaDiretorioNotificacoesInternas,
)
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes import FabricaAdaptersExternos
from infra.seguranca.segredos_sqlalchemy import (
    EncryptedSQLAlchemySecretStore,
)


class EntregaWhatsAppNotificacaoInterna:
    def __init__(
        self,
        *,
        session: Session,
        diretorio: PortaDiretorioNotificacoesInternas,
        sender: Callable[[str, str, str], str] | None = None,
    ) -> None:
        self._session = session
        self._diretorio = diretorio
        self._sender = sender

    def enviar(
        self,
        *,
        contexto: ContextoExecucao,
        referencia_contato: str,
        texto: str,
        idempotency_key: str,
    ) -> str:
        contato = self._diretorio.resolver_contato(
            contexto=contexto,
            referencia_contato=referencia_contato,
        )
        if self._sender is not None:
            return self._sender(
                contato.reveal(),
                texto,
                idempotency_key,
            )
        vault = EncryptedSQLAlchemySecretStore(self._session)
        adapter = FabricaAdaptersExternos(
            session=self._session,
            secret_store=vault,
        ).meta(
            contexto=contexto,
            configuracao_id="mensageria.whatsapp--meta",
        )
        return adapter.enviar_whatsapp(
            destinatario=contato.reveal(),
            texto=texto,
            idempotency_key=idempotency_key,
        )
