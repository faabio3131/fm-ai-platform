"""Transporte comercial WhatsApp para campanhas CRM consentidas."""

from __future__ import annotations

from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from infra.crm.contatos_sqlalchemy import EncryptedSQLAlchemyContactStore
from infra.integracoes import FabricaAdaptersExternos
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore


class EnvioWhatsAppMarketingComercial:
    """Resolve PII no boundary autorizado e exige integração Meta homologada."""

    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        campanha_ref: str,
        texto: str,
    ) -> None:
        if not campanha_ref.strip() or not texto.strip():
            raise ValueError("campanha_marketing_invalida")
        self._session = session
        self._contexto = contexto
        self._campanha_ref = campanha_ref
        self._texto = texto.strip()
        self.mensagem_id: str | None = None

    def enviar(
        self,
        *,
        referencia_contato: str,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None:
        if campanha_ref != self._campanha_ref:
            raise ValueError("campanha_marketing_divergente")

        contato = EncryptedSQLAlchemyContactStore(self._session).resolver(
            contexto=self._contexto,
            referencia=referencia_contato,
        )
        vault = EncryptedSQLAlchemySecretStore(self._session)
        adapter = FabricaAdaptersExternos(
            session=self._session,
            secret_store=vault,
        ).meta(
            contexto=self._contexto,
            configuracao_id="mensageria.whatsapp--meta",
        )
        mensagem_id = adapter.enviar_whatsapp(
            destinatario=contato.reveal(),
            texto=self._texto,
            idempotency_key=idempotency_key,
        )
        if not mensagem_id.strip():
            raise RuntimeError("envio_whatsapp_sem_confirmacao")
        self.mensagem_id = mensagem_id
