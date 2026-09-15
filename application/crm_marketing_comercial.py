"""Boundary comercial de campanhas CRM com consentimento canônico."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import inspect, or_, select
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
    """Extrai sem alteração a seleção e a sugestão de resgate do legado.

    Um banco legado de desenvolvimento/sandbox sem ledger de migrations pode ainda
    não possuir a ponte CRM. Nesse estado não há vínculo governado a consultar e a
    leitura retorna vazia. Se o ledger oficial já existe, a ausência da ponte indica
    schema inconsistente e falha fechado.
    """

    data_corte_inativos = datetime.now() - timedelta(days=15)  # noqa: DTZ005
    session = session_factory()
    try:
        bind = session.get_bind()
        tabelas = set(inspect(bind).get_table_names())
        if "crm_cliente_legado_v1" not in tabelas:
            if "fm_schema_migrations" in tabelas:
                raise MarketingCRMComercialInvalido(
                    "crm.schema_inconsistente: crm_cliente_legado_v1 ausente"
                )
            return ()

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
    """Valida ownership + consentimento antes de qualquer envio externo."""

    mensagem = texto.strip()
    if not mensagem:
        raise MarketingCRMComercialInvalido("Mensagem de resgate vazia.")

    session = session_factory()
    try:
        leitor_mapping = LeitorClienteLegadoCRMSQLAlchemy(session)
        mapping = leitor_mapping.obter_por_legado(
            contexto.tenant_id,
            contexto.unidade_id,
            int(legacy_cliente_id),
        )
        if mapping is None:
            raise MarketingCRMComercialInvalido(
                "Cliente legado ainda não possui vínculo CRM governado."
            )

        cliente = LeitorClientesCRMSQLAlchemy(session).obter_por_id(
            contexto.tenant_id,
            mapping.cliente_id,
        )
        if cliente is None:
            raise MarketingCRMComercialInvalido("Cliente CRM vinculado não encontrado.")

        contatos = [contato for contato in cliente.contatos if contato.canal == "whatsapp"]
        if len(contatos) != 1:
            raise MarketingCRMComercialInvalido(
                "Cliente CRM precisa de exatamente um WhatsApp canônico para marketing."
            )
        contato = contatos[0]

        hoje = date.today()
        leitor_consentimento = LeitorConsentimentosMarketingSQLAlchemy(session)
        consentimentos = leitor_consentimento.listar_por_cliente(
            contexto.tenant_id,
            mapping.cliente_id,
        )
        vigente = next(
            (
                consentimento
                for consentimento in consentimentos
                if consentimento.canal is CanalMarketing.WHATSAPP
                and consentimento.finalidade is FinalidadeMarketing.PROMOCOES
                and consentimento.permitido
                and consentimento.vigente_em(hoje)
            ),
            None,
        )
        if vigente is None:
            raise MarketingCRMComercialInvalido(
                "Envio bloqueado: consentimento WhatsApp/promocoes ausente ou não vigente."
            )

        adapter = envio or EnvioWhatsAppMarketingComercial()
        servico = ServicoCRM(
            clientes=LeitorClientesCRMSQLAlchemy(session),
            consentimentos=leitor_consentimento,
            envio_marketing=adapter,
        )
        mensagem_id = servico.enviar_marketing(
            contexto,
            cliente_id=mapping.cliente_id,
            contato_id=contato.contato_id,
            canal=CanalMarketing.WHATSAPP,
            finalidade=FinalidadeMarketing.PROMOCOES,
            mensagem=mensagem,
            data_referencia=hoje,
        )
        return ResultadoMarketingCRMComercial(
            cliente_id=mapping.cliente_id,
            enviado=True,
            motivo="enviado",
            mensagem_id=mensagem_id,
        )
    finally:
        session.close()
