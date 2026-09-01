"""Fronteiras transacionais do Gerente IA V1.

As composition roots de apresentação fornecem apenas dados validados de
transporte. Autenticação, runtime e mutações executam dentro de UnitOfWorkV1.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from application.gerente_ia_runtime import (
    PlanejadorLLM,
    compor_runtime_gerente_ia,
)
from core.gerente_ia.modelos import ChamadaTool
from core.seguranca.autenticacao import ServicoAutenticacao
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.adaptador_sqlalchemy import (
    RepositorioIdentidadesSQLAlchemy,
)
from infra.transacoes.uow import UnitOfWorkV1

PlanejadorLLMFactory = Callable[[Session], PlanejadorLLM]


def _session_ativa(uow: UnitOfWorkV1) -> Session:
    if uow.session is None:
        raise RuntimeError("UnitOfWorkV1 sem Session ativa")
    return uow.session


def _contexto_autenticado(
    session: Session,
    *,
    email: str,
    password: str,
    origem: str,
    correlation_id: str | None,
) -> ContextoExecucao:
    identidade = ServicoAutenticacao(
        RepositorioIdentidadesSQLAlchemy(session)
    ).autenticar(
        email=email,
        password=password,
    )

    return identidade.contexto(
        origem=origem,
        correlation_id=correlation_id,
    )


def executar_tool_gerente_ia_v1(
    *,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None,
    email: str,
    password: str,
    origem: str,
    correlation_id: str | None,
    chamada: ChamadaTool,
    planejador_llm_factory: PlanejadorLLMFactory | None = None,
) -> Any:
    with UnitOfWorkV1(session_factory) as uow:
        session = _session_ativa(uow)

        contexto = _contexto_autenticado(
            session,
            email=email,
            password=password,
            origem=origem,
            correlation_id=correlation_id,
        )

        runtime = compor_runtime_gerente_ia(
            session=session,
            secret_store=secret_store,
            planejador_llm=(
                planejador_llm_factory(session)
                if planejador_llm_factory
                else None
            ),
        )

        resultado = runtime.executar_tool(
            contexto=contexto,
            chamada=chamada,
        )

        uow.commit()
        return resultado


def confirmar_acao_gerente_ia_v1(
    *,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None,
    email: str,
    password: str,
    origem: str,
    correlation_id: str | None,
    preview_id: str,
    fingerprint: str,
    idempotency_key: str,
) -> Any:
    with UnitOfWorkV1(session_factory) as uow:
        session = _session_ativa(uow)

        contexto = _contexto_autenticado(
            session,
            email=email,
            password=password,
            origem=origem,
            correlation_id=correlation_id,
        )

        runtime = compor_runtime_gerente_ia(
            session=session,
            secret_store=secret_store,
        )

        resultado = runtime.confirmar_acao(
            contexto=contexto,
            preview_id=preview_id,
            fingerprint=fingerprint,
            idempotency_key=idempotency_key,
        )

        uow.commit()
        return resultado


def configurar_identidade_assistente_v1(
    *,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None,
    email: str,
    password: str,
    origem: str,
    correlation_id: str | None,
    nome_publico: str,
    atributos: dict[str, Any],
    versao_esperada: int | None,
) -> Any:
    with UnitOfWorkV1(session_factory) as uow:
        session = _session_ativa(uow)

        contexto = _contexto_autenticado(
            session,
            email=email,
            password=password,
            origem=origem,
            correlation_id=correlation_id,
        )

        runtime = compor_runtime_gerente_ia(
            session=session,
            secret_store=secret_store,
        )

        identidade = runtime.identidade_assistente.configurar(
            contexto=contexto,
            nome_publico=nome_publico,
            atributos=atributos,
            versao_esperada=versao_esperada,
        )

        uow.commit()
        return identidade


def perguntar_gerente_ia_v1(
    *,
    session_factory: Callable[[], Session],
    secret_store: SecretStore | None,
    email: str,
    password: str,
    origem: str,
    correlation_id: str | None,
    pergunta: str,
    planejador_llm_factory: PlanejadorLLMFactory | None = None,
) -> tuple[Any, ChamadaTool, Any]:
    with UnitOfWorkV1(session_factory) as uow:
        session = _session_ativa(uow)

        contexto = _contexto_autenticado(
            session,
            email=email,
            password=password,
            origem=origem,
            correlation_id=correlation_id,
        )

        runtime = compor_runtime_gerente_ia(
            session=session,
            secret_store=secret_store,
            planejador_llm=(
                planejador_llm_factory(session)
                if planejador_llm_factory
                else None
            ),
        )

        identidade, chamada, resultado = runtime.perguntar(
            contexto=contexto,
            pergunta=pergunta,
        )

        uow.commit()
        return identidade, chamada, resultado
