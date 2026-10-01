"""Application boundary da Central Web de Campanhas do Kordena V1."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from application.crm_marketing_comercial import despachar_campanha_whatsapp_cliente
from core.crm.modelos import (
    CanalMarketing,
    FinalidadeMarketing,
    StatusConsentimento,
)
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import ChamadaTool, ToolGerenteIA
from core.gerente_ia.servicos import ServicoGerenteIA
from core.seguranca.contexto import ContextoExecucao
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.crm.clientes_sqlalchemy import LeitorClientesCRMSQLAlchemy
from infra.crm.consentimentos_marketing_sqlalchemy import (
    LeitorConsentimentosMarketingSQLAlchemy,
)
from infra.gerente_ia.campanhas_web_sqlalchemy import CampanhasWebSQLAlchemy
from infra.gerente_ia.consultas_sqlalchemy import ConsultasGerenciaisSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import (
    AcoesGerenciaisSQLAlchemy,
    RepositorioPreviewsSQLAlchemy,
)
from infra.legacy_schema import clientes as clientes_legados
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class CampanhaWeb:
    campanha_id: str
    canal: str
    finalidade: str
    objetivo: str
    texto_base: str
    audiencia_elegivel: int
    criado_em: datetime
    criado_por: str
    status: str
    fingerprint: str
    campanha_ref: str | None = None


@dataclass(frozen=True)
class AudienciaCampanha:
    cliente_id: str
    nome: str
    canal_disponivel: bool
    consentimento: str
    selecionado: bool
    elegivel: bool


@dataclass(frozen=True)
class EventoCampanhaWeb:
    event_id: str
    event_type: str
    ocorrido_em: datetime
    payload: dict[str, Any]


def _session(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


def _service(session: Session) -> ServicoGerenteIA:
    return ServicoGerenteIA(
        consultas=ConsultasGerenciaisSQLAlchemy(session),
        acoes=AcoesGerenciaisSQLAlchemy(session),
        campanhas=CampanhasWebSQLAlchemy(session),
        previews=RepositorioPreviewsSQLAlchemy(session),
        auditoria=RepositorioAuditoriaSQLAlchemy(session),
    )


def _web(repo: CampanhasWebSQLAlchemy, row) -> CampanhaWeb:
    return CampanhaWeb(
        campanha_id=row.rascunho_id,
        canal=row.canal,
        finalidade=row.finalidade,
        objetivo=row.objetivo,
        texto_base=row.texto_base,
        audiencia_elegivel=row.audiencia_elegivel,
        criado_em=row.criado_em,
        criado_por=row.criado_por,
        status=row.status,
        fingerprint=repo.fingerprint(row),
        campanha_ref=repo.campanha_ref(
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            campanha_id=row.rascunho_id,
        ),
    )


def listar_campanhas_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
) -> tuple[CampanhaWeb, ...]:
    with session_factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        return tuple(
            _web(repo, row)
            for row in repo.listar(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
            )
        )


def obter_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
) -> CampanhaWeb:
    with session_factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        row = repo.obter_web(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
        )
        return _web(repo, row)


def criar_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    canal: str,
    finalidade: str,
    objetivo: str,
    texto_base: str,
    idempotency_key: str,
) -> CampanhaWeb:
    with UnitOfWorkV1(session_factory) as uow:
        session = _session(uow)
        resultado = _service(session).executar_tool(
            contexto=contexto,
            chamada=ChamadaTool.de_dict(
                ToolGerenteIA.PREPARAR_CAMPANHA,
                {
                    "canal": canal,
                    "finalidade": finalidade,
                    "objetivo": objetivo,
                    "texto_base": texto_base,
                    "idempotency_key": idempotency_key,
                },
            ),
        )
        if not hasattr(resultado, "rascunho_id"):
            raise ErroGerenteIA("campanha_rascunho_inconsistente")
        repo = CampanhasWebSQLAlchemy(session)
        row = repo.obter_web(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=str(resultado.rascunho_id),
        )
        out = _web(repo, row)
        uow.commit()
        return out


def atualizar_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
    canal: str,
    finalidade: str,
    objetivo: str,
    texto_base: str,
    idempotency_key: str,
) -> CampanhaWeb:
    with UnitOfWorkV1(session_factory) as uow:
        repo = CampanhasWebSQLAlchemy(_session(uow))
        row = repo.atualizar_rascunho(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
            canal=canal,
            finalidade=finalidade,
            objetivo=objetivo,
            texto_base=texto_base,
            usuario_id=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            idempotency_key=idempotency_key,
            agora=datetime.now(timezone.utc),
        )
        out = _web(repo, row)
        uow.commit()
        return out


def _nome_por_cliente(
    session: Session, *, tenant_id: str, unidade_id: str
) -> dict[str, str]:
    rows = session.execute(
        select(crm_cliente_legado_v1.c.cliente_id, clientes_legados.c.nome)
        .join(
            clientes_legados,
            clientes_legados.c.id == crm_cliente_legado_v1.c.legacy_cliente_id,
        )
        .where(
            crm_cliente_legado_v1.c.tenant_id == tenant_id,
            crm_cliente_legado_v1.c.unidade_id == unidade_id,
        )
    ).all()
    return {str(cliente_id): str(nome or "") for cliente_id, nome in rows}


def listar_audiencia_campanha(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
) -> tuple[AudienciaCampanha, ...]:
    with session_factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        row = repo.obter_web(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
        )
        try:
            canal = CanalMarketing(row.canal)
            finalidade = FinalidadeMarketing(row.finalidade)
        except ValueError as exc:
            raise ErroGerenteIA("campanha_canal_finalidade_nao_suportados") from exc
        clientes = LeitorClientesCRMSQLAlchemy(session).listar(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        nomes = _nome_por_cliente(
            session,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        consentimentos = LeitorConsentimentosMarketingSQLAlchemy(session)
        selecionados = set(
            repo.audiencia_ids(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                campanha_id=campanha_id,
            )
        )
        resultado: list[AudienciaCampanha] = []
        for cliente in clientes:
            consentimento = consentimentos.atual(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                cliente_id=cliente.cliente_id,
                canal=canal,
                finalidade=finalidade,
            )
            canal_disponivel = cliente.contato_para(canal) is not None
            concedido = (
                consentimento is not None
                and consentimento.status is StatusConsentimento.CONCEDIDO
            )
            resultado.append(
                AudienciaCampanha(
                    cliente_id=cliente.cliente_id,
                    nome=nomes.get(cliente.cliente_id) or cliente.cliente_id,
                    canal_disponivel=canal_disponivel,
                    consentimento=(
                        consentimento.status.value
                        if consentimento is not None
                        else "ausente"
                    ),
                    selecionado=cliente.cliente_id in selecionados,
                    elegivel=canal_disponivel and concedido,
                )
            )
        return tuple(resultado)


def definir_audiencia_campanha(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
    cliente_ids: tuple[str, ...],
    idempotency_key: str,
) -> CampanhaWeb:
    solicitados = tuple(dict.fromkeys(item.strip() for item in cliente_ids if item.strip()))
    if not solicitados:
        raise ErroGerenteIA("campanha_audiencia_obrigatoria")
    elegiveis = {
        item.cliente_id
        for item in listar_audiencia_campanha(
            session_factory=session_factory,
            contexto=contexto,
            campanha_id=campanha_id,
        )
        if item.elegivel
    }
    if any(item not in elegiveis for item in solicitados):
        raise ErroGerenteIA("campanha_audiencia_contem_cliente_inelegivel")
    with UnitOfWorkV1(session_factory) as uow:
        repo = CampanhasWebSQLAlchemy(_session(uow))
        row = repo.definir_audiencia(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
            cliente_ids=solicitados,
            usuario_id=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            idempotency_key=idempotency_key,
            agora=datetime.now(timezone.utc),
        )
        out = _web(repo, row)
        uow.commit()
        return out


def submeter_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
    idempotency_key: str,
) -> CampanhaWeb:
    audiencia = listar_audiencia_campanha(
        session_factory=session_factory,
        contexto=contexto,
        campanha_id=campanha_id,
    )
    selecionados = {item.cliente_id for item in audiencia if item.selecionado}
    elegiveis = {item.cliente_id for item in audiencia if item.elegivel}
    if not selecionados or not selecionados.issubset(elegiveis):
        raise ErroGerenteIA("campanha_audiencia_desatualizada")
    with UnitOfWorkV1(session_factory) as uow:
        repo = CampanhasWebSQLAlchemy(_session(uow))
        row = repo.submeter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
            usuario_id=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            idempotency_key=idempotency_key,
            agora=datetime.now(timezone.utc),
        )
        out = _web(repo, row)
        uow.commit()
        return out


def aprovar_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
    fingerprint: str,
    idempotency_key: str,
) -> CampanhaWeb:
    atual = obter_campanha_web(
        session_factory=session_factory,
        contexto=contexto,
        campanha_id=campanha_id,
    )
    if atual.status != "aguardando_aprovacao":
        raise ErroGerenteIA("campanha_nao_aguarda_aprovacao")
    if atual.fingerprint != fingerprint:
        raise ErroGerenteIA("fingerprint_divergente")
    with UnitOfWorkV1(session_factory) as uow:
        session = _session(uow)
        _service(session).aprovar_campanha(
            contexto_humano=contexto,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
        )
        repo = CampanhasWebSQLAlchemy(session)
        out = _web(
            repo,
            repo.obter_web(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                campanha_id=campanha_id,
            ),
        )
        uow.commit()
        return out


def publicar_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
    fingerprint: str,
    idempotency_key: str,
) -> CampanhaWeb:
    atual = obter_campanha_web(
        session_factory=session_factory,
        contexto=contexto,
        campanha_id=campanha_id,
    )
    if atual.status != "aprovada":
        raise ErroGerenteIA("campanha_nao_esta_aprovada")
    if atual.fingerprint != fingerprint:
        raise ErroGerenteIA("fingerprint_divergente")
    with UnitOfWorkV1(session_factory) as uow:
        session = _session(uow)
        _service(session).publicar_campanha(
            contexto_humano=contexto,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
        )
        repo = CampanhasWebSQLAlchemy(session)
        out = _web(
            repo,
            repo.obter_web(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                campanha_id=campanha_id,
            ),
        )
        uow.commit()
        return out


def historico_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
) -> tuple[EventoCampanhaWeb, ...]:
    with session_factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        return tuple(
            EventoCampanhaWeb(
                event_id=row.event_id,
                event_type=row.event_type,
                ocorrido_em=row.ocorrido_em,
                payload=dict(row.payload_seguro),
            )
            for row in repo.historico(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                campanha_id=campanha_id,
            )
        )


def despachar_campanha_web(
    *,
    session_factory: SessionFactory,
    contexto: ContextoExecucao,
    campanha_id: str,
    fingerprint: str,
    idempotency_key: str,
) -> dict[str, Any]:
    atual = obter_campanha_web(
        session_factory=session_factory,
        contexto=contexto,
        campanha_id=campanha_id,
    )
    if atual.status != "publicavel" or not atual.campanha_ref:
        raise ErroGerenteIA("campanha_nao_publicavel")
    if atual.fingerprint != fingerprint:
        raise ErroGerenteIA("fingerprint_divergente")
    with session_factory() as session:
        repo = CampanhasWebSQLAlchemy(session)
        selecionados = repo.audiencia_ids(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
        )
    if not selecionados:
        raise ErroGerenteIA("campanha_audiencia_obrigatoria")

    resultados: list[dict[str, Any]] = []
    for cliente_id in selecionados:
        try:
            resultado = despachar_campanha_whatsapp_cliente(
                session_factory=session_factory,
                contexto=contexto,
                cliente_id=cliente_id,
                campanha_ref=atual.campanha_ref,
                texto=atual.texto_base,
                idempotency_key=f"{idempotency_key}:{cliente_id}",
            )
            resultados.append(
                {
                    "cliente_id": cliente_id,
                    "enviado": resultado.enviado,
                    "motivo": resultado.motivo,
                    "mensagem_id": resultado.mensagem_id,
                }
            )
        except Exception as exc:  # noqa: BLE001 — preservar falha externa por destinatário
            resultados.append(
                {
                    "cliente_id": cliente_id,
                    "enviado": False,
                    "motivo": type(exc).__name__,
                    "mensagem_id": None,
                }
            )

    with UnitOfWorkV1(session_factory) as uow:
        repo = CampanhasWebSQLAlchemy(_session(uow))
        repo.registrar_despacho(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            campanha_id=campanha_id,
            resultados=tuple(resultados),
            usuario_id=contexto.usuario_id,
            correlation_id=contexto.correlation_id,
            idempotency_key=f"{idempotency_key}:summary",
            agora=datetime.now(timezone.utc),
        )
        uow.commit()
    return {
        "campanha_id": campanha_id,
        "total": len(resultados),
        "enviados": sum(bool(item["enviado"]) for item in resultados),
        "resultados": resultados,
    }
