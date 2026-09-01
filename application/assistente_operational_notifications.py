"""Notificação best-effort de mudanças operacionais para o canal do Assistente.

A operação canônica sempre confirma primeiro. Falha de WhatsApp jamais reverte
Pagamento, KDS ou Entrega; o cliente continua podendo consultar o estado real em
um inbound posterior.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from application.assistente_channel_runtime import RuntimeCanalWhatsAppV1
from core.integracoes.modelos import ErroConfiguracaoServico
from core.integracoes.provedores import ErroProvedorExterno
from core.seguranca.contexto import ContextoExecucao
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

SessionFactory = Callable[[], Session]


def notificar_status_assistente_best_effort(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    pedido_id: str,
) -> int:
    """Notifica somente se canal real estiver configurado e o snapshot mudou."""

    if not pedido_id.strip():
        return 0
    try:
        with session_factory() as session:
            adapter = FabricaAdaptersExternos(
                session=session,
                secret_store=EncryptedSQLAlchemySecretStore(session),
            ).meta(
                contexto=contexto,
                configuracao_id="mensageria.whatsapp--meta",
            )
        return RuntimeCanalWhatsAppV1(session_factory).notificar_status_pedido(
            contexto=contexto,
            pedido_id=pedido_id,
            adapter=adapter,
        )
    except (
        ErroConfiguracaoServico,
        ErroProvedorExterno,
        LookupError,
        RuntimeError,
    ):
        return 0
