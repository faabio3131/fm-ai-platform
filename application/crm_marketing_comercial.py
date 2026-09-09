"""Boundary comercial de campanhas CRM com consentimento canônico."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.crm.adapters import PortaEnvioMarketing
from core.crm.erros import ErroCRM
from core.crm.modelos import CanalMarketing, FinalidadeMarketing
from core.crm.servicos import ServicoCRM
from core.seguranca.contexto import ContextoExecucao
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.crm.cliente_legado_sqlalchemy import LeitorClienteLegadoCRMSQLAlchemy
from infra.crm.clientes_sqlalchemy import LeitorClientesCRMSQLAlchemy
from infra.crm.consentimentos_marketing_sqlalchemy import (
    LeitorConsentimentosMarketingSQLAlchemy,
)
from infra.crm.marketing_whatsapp import EnvioWhatsAppMarketingComercial
from infra.legacy_schema import clientes as clientes_legados


class MarketingCRMComercialInvalido(ErroCRM):
    pass


@dataclass(frozen=True)
class ResultadoMarketingCRMComercial:
    cliente_id: str
    enviado: bool
    motivo: str
    mensagem_id: str | None = None


@dataclass(frozen=True)
class OportunidadeResgateCRM:
    legacy_cliente_id: int
    cliente_id: str
    nome: str
    whatsapp: str
    ultima_compra: datetime | None
    total_gasto: float
    status: str
    mensagem_sugerida: str


def _mensagem_padrao_resgate(nome: str) -> str:
    return (
        f"Olá {nome}! Sentimos sua falta. Preparamos um cupom "
        "exclusivo de 15% de desconto para você voltar hoje!"
    )


def _prompt_gemini_resgate(nome: str) -> str:
    return (
        "Escreva uma mensagem curta, carinhosa e persuasiva de "
        f"WhatsApp para resgatar o cliente '{nome}'. Ofereça "
        "15% de desconto com o cupom VOLTA15. Sem clichês em excesso."
    )


def _compor_mensagem_resgate(
    *,
    nome: str,
    genai_disponivel: bool,
    generate_content: Callable[..., Any],
) -> str:
    mensagem = _mensagem_padrao_resgate(nome)
    if genai_disponivel:
        try:
            resposta = generate_content(contents=_prompt_gemini_resgate(nome))
            texto = str(getattr(resposta, "text", "") or "").strip()
            if texto:
                mensagem = texto
        except Exception:  # noqa: BLE001,S110 - fallback legado intencional
            pass
    return mensagem


def preparar_resgates_clientes_inativos(
    *,
    session_factory: Callable[[], Session],
    tenant_id: str,
    unidade_id: str,
    genai_disponivel: bool,
    generate_content: Callable[..., Any],
) -> tuple[OportunidadeResgateCRM, ...]:
    """Extrai sem alteração a seleção e a sugestão de resgate do legado."""

    data_corte_inativos = datetime.now() - timedelta(days=15)  # noqa: DTZ005
    session = session_factory()
    try:
        rows = session.execute(
            select(
                crm_cliente_legado_v1.c.legacy_cliente_id,
                crm_cliente_legado_v1.c.cliente_id,
                clientes_legados.c.nome,
                clientes_legados.c.whatsapp,
                clientes_legados.c.ultima_compra,
                clientes_legados.c.total_gasto,
                clientes_legados.c.status,
            )
            .join(
                clientes_legados,
                clientes_legados.c.id
                == crm_cliente_legado_v1.c.legacy_cliente_id,
            )
            .where(
                crm_cliente_legado_v1.c.tenant_id == tenant_id,
                crm_cliente_legado_v1.c.unidade_id == unidade_id,
                or_(
                    clientes_legados.c.ultima_compra <= data_corte_inativos,
                    clientes_legados.c.status == "Inativo",
                ),
            )
            .order_by(crm_cliente_legado_v1.c.legacy_cliente_id)
        ).mappings()
        return tuple(
            OportunidadeResgateCRM(
                legacy_cliente_id=int(row["legacy_cliente_id"]),
                cliente_id=str(row["cliente_id"]),
                nome=str(row["nome"] or ""),
                whatsapp=str(row["whatsapp"] or ""),
                ultima_compra=cast(datetime | None, row["ultima_compra"]),
                total_gasto=float(row["total_gasto"] or 0.0),
                status=str(row["status"] or ""),
                mensagem_sugerida=_compor_mensagem_resgate(
                    nome=str(row["nome"] or ""),
                    genai_disponivel=genai_disponivel,
                    generate_content=generate_content,
                ),
            )
            for row in rows
        )
    finally:
        session.close()


def despachar_resgate_cliente_inativo(
    *,
    session_factory: Callable[[], Session],
    contexto: ContextoExecucao,
    legacy_cliente_id: int,
    texto: str,
    envio: PortaEnvioMarketing | None = None,
) -> ResultadoMarketingCRMComercial:
    """Preserva os identificadores diários e delega ao despacho consentido."""

    data_atual = date.today().isoformat()  # noqa: DTZ011
    return despachar_resgate_whatsapp_legado(
        session_factory=session_factory,
        contexto=contexto,
        legacy_cliente_id=legacy_cliente_id,
        campanha_ref=f"resgate-{data_atual}",
        texto=texto,
        idempotency_key=f"crm-resgate-{legacy_cliente_id}-{data_atual}",
        envio=envio,
    )


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
        session.close()
