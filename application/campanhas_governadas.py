"""Fronteira transacional humana para campanhas governadas F4-G."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from core.gerente_ia.modelos import CampanhaAprovada, CampanhaPublicavel
from core.gerente_ia.servicos import ServicoGerenteIA
from core.seguranca.contexto import ContextoExecucao
from infra.gerente_ia.campanhas_governadas_sqlalchemy import (
    CampanhasGovernadasSQLAlchemy,
)
from infra.gerente_ia.consultas_sqlalchemy import ConsultasGerenciaisSQLAlchemy
from infra.gerente_ia.persistencia_sqlalchemy import (
    AcoesGerenciaisSQLAlchemy,
    RepositorioPreviewsSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


def _servico(session: Session) -> ServicoGerenteIA:
    return ServicoGerenteIA(
        consultas=ConsultasGerenciaisSQLAlchemy(session),
        acoes=AcoesGerenciaisSQLAlchemy(session),
        campanhas=CampanhasGovernadasSQLAlchemy(session),
        previews=RepositorioPreviewsSQLAlchemy(session),
        auditoria=RepositorioAuditoriaSQLAlchemy(session),
    )


def aprovar_campanha_v1(
    *,
    session_factory: Callable[[], Session],
    contexto_humano: ContextoExecucao,
    campanha_id: str,
    idempotency_key: str,
) -> CampanhaAprovada:
    """Aprova dentro de UoW; contexto já deve vir da autenticação canônica."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = _servico(_session_ativa(uow)).aprovar_campanha(
            contexto_humano=contexto_humano,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
        )
        uow.commit()
        return resultado


def publicar_campanha_v1(
    *,
    session_factory: Callable[[], Session],
    contexto_humano: ContextoExecucao,
    campanha_id: str,
    idempotency_key: str,
) -> CampanhaPublicavel:
    """Torna a campanha publicável; não executa envio externo."""

    with UnitOfWorkV1(session_factory) as uow:
        resultado = _servico(_session_ativa(uow)).publicar_campanha(
            contexto_humano=contexto_humano,
            campanha_id=campanha_id,
            idempotency_key=idempotency_key,
        )
        uow.commit()
        return resultado
