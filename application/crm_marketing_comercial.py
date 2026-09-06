"""Boundary comercial de campanhas CRM com consentimento canônico."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.orm import Session

from core.crm.adapters import PortaEnvioMarketing
from core.crm.erros import ErroCRM
from core.crm.modelos import CanalMarketing, FinalidadeMarketing
from core.crm.servicos import ServicoCRM
from core.seguranca.contexto import ContextoExecucao
from infra.crm.cliente_legado_sqlalchemy import LeitorClienteLegadoCRMSQLAlchemy
from infra.crm.clientes_sqlalchemy import LeitorClientesCRMSQLAlchemy
from infra.crm.consentimentos_marketing_sqlalchemy import (
    LeitorConsentimentosMarketingSQLAlchemy,
)
from infra.crm.marketing_whatsapp import EnvioWhatsAppMarketingComercial


class MarketingCRMComercialInvalido(ErroCRM):
    pass


@dataclass(frozen=True)
class ResultadoMarketingCRMComercial:
    cliente_id: str
    enviado: bool
    motivo: str
    mensagem_id: str | None = None


def despachar_resgate_whatsapp_legado(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    legacy_cliente_id: int,
    campanha_ref: str,
    texto: str,
    idempotency_key: str,
    envio: PortaEnvioMarketing | None = None,
) -> ResultadoMarketingCRMComercial:
    """Despacha somente após mapping CRM + consentimento WhatsApp/promoções vigente."""

    session = session_factory()
    try:
        vinculo = LeitorClienteLegadoCRMSQLAlchemy(session).resolver(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            legacy_cliente_id=legacy_cliente_id,
        )
        if vinculo is None:
            raise MarketingCRMComercialInvalido("cliente_legado_sem_mapping_crm")

        transporte = envio or EnvioWhatsAppMarketingComercial(
            session=session,
            contexto=contexto,
            campanha_ref=campanha_ref,
            texto=texto,
        )
        nao_usado = cast(Any, object())
        servico = ServicoCRM(
            clientes=cast(Any, LeitorClientesCRMSQLAlchemy(session)),
            marketplace_clientes=nao_usado,
            consentimentos=cast(
                Any, LeitorConsentimentosMarketingSQLAlchemy(session)
            ),
            funil=nao_usado,
            beneficios=nao_usado,
            hash_identidade=nao_usado,
            auditoria=None,
        )
        resultado = servico.despachar_marketing(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            cliente_id=vinculo.cliente_id,
            canal=CanalMarketing.WHATSAPP,
            finalidade=FinalidadeMarketing.PROMOCOES,
            campanha_ref=campanha_ref,
            idempotency_key=idempotency_key,
            envio=transporte,
        )
        mensagem_id = getattr(transporte, "mensagem_id", None)
        return ResultadoMarketingCRMComercial(
            cliente_id=vinculo.cliente_id,
            enviado=resultado.enviado,
            motivo=resultado.motivo,
            mensagem_id=mensagem_id if isinstance(mensagem_id, str) else None,
        )
    finally:
        session.rollback()
        session.close()
