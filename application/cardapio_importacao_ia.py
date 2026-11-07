"""Composicao do cardapio via IA governada para o frontend Web.

A aplicacao, nao o HTTP, controla a transacao de roteamento/auditoria.
A importacao/persistencia de produtos continua na aplicacao de cardapio
existente; o resultado gerado por IA nao recebe autoridade de escrita.
"""
from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from core.ai_router import CapabilityIA, SolicitacaoIA
from core.seguranca.contexto import ContextoExecucao
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore
from infra.transacoes.uow import UnitOfWorkV1


def gerar_cardapio_ia_governada(
    *,
    contexto: ContextoExecucao,
    contents: Any,
    session_factory: Callable[[], Session],
) -> Any:
    """Usa a rota Gemini homologada no Control Plane, sem sessao Streamlit."""
    with UnitOfWorkV1(session_factory) as uow:
        session = uow.session
        if session is None:
            raise RuntimeError("catalogo.ia_uow_indisponivel")
        router = construir_ai_model_router(
            session=session,
            contexto=contexto,
            secret_store=EncryptedSQLAlchemySecretStore(session),
        )
        resposta = router.executar(
            SolicitacaoIA(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                request_id=str(uuid4()),
                correlation_id=contexto.correlation_id or str(uuid4()),
                capability=CapabilityIA.CARDAPIO_IMPORTACAO,
                conteudo=contents,
            )
        )
        uow.commit()
        return SimpleNamespace(text=str(resposta.conteudo))
